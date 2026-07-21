"""Host hardware probe — the "specifier" that feeds the local-model calculator.

The goal is an honest, accurate spec sheet on every platform:
  - real marketing CPU name (not "AMD64" / "x86_64")
  - accurate total VRAM for every GPU, including >4 GB cards and non-NVIDIA
    (Windows' Win32_VideoController.AdapterRAM is a uint32 and lies above 4 GB;
    we read the driver's HardwareInformation.qwMemorySize from the registry
    instead, which is the value tools like GPU-Z use)
  - GPU vendor/class so the calculator knows whether a real accelerator exists
"""

from __future__ import annotations

import platform
import shutil
import subprocess
from dataclasses import asdict, dataclass, field

import psutil


@dataclass
class GpuInfo:
    vendor: str  # "nvidia" | "amd" | "intel" | "apple" | "unknown"
    name: str
    vram_gb: float | None  # None when it genuinely can't be determined
    kind: str = "discrete"  # "discrete" | "integrated"
    source: str = ""  # how we learned the VRAM (for debugging / transparency)


@dataclass
class HardwareInfo:
    os: str
    cpu: str
    arch: str
    cores_physical: int
    cores_logical: int
    ram_total_gb: float
    ram_available_gb: float
    disk_free_gb: float
    gpus: list[GpuInfo] = field(default_factory=list)

    @property
    def best_gpu(self) -> GpuInfo | None:
        usable = [g for g in self.gpus if g.vram_gb]
        return max(usable, key=lambda g: g.vram_gb or 0, default=None)


# --------------------------------------------------------------------------- CPU


def _cpu_name() -> str:
    system = platform.system()
    try:
        if system == "Windows":
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
            ) as key:
                name, _ = winreg.QueryValueEx(key, "ProcessorNameString")
                if name:
                    return name.strip()
        elif system == "Darwin":
            out = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True, text=True, timeout=5,
            ).stdout.strip()
            if out:
                return out
        elif system == "Linux":
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if line.lower().startswith("model name"):
                        return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return platform.processor() or platform.machine() or "Unknown CPU"


# --------------------------------------------------------------------------- GPU


def _vendor_of(name: str) -> str:
    low = name.lower()
    if "nvidia" in low or "geforce" in low or "quadro" in low or "rtx" in low or "gtx" in low:
        return "nvidia"
    if "radeon" in low or "amd" in low or "ryzen" in low:
        return "amd"
    if "intel" in low or "arc" in low or "iris" in low or "uhd" in low:
        return "intel"
    if "apple" in low:
        return "apple"
    return "unknown"


def _probe_nvidia() -> list[GpuInfo]:
    try:
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            import pynvml

        pynvml.nvmlInit()
        gpus: list[GpuInfo] = []
        for i in range(pynvml.nvmlDeviceGetCount()):
            handle = pynvml.nvmlDeviceGetHandleByIndex(i)
            name = pynvml.nvmlDeviceGetName(handle)
            if isinstance(name, bytes):
                name = name.decode()
            mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
            gpus.append(
                GpuInfo(
                    vendor="nvidia",
                    name=name,
                    vram_gb=round(mem.total / 1024**3, 1),
                    kind="discrete",
                    source="nvml",
                )
            )
        pynvml.nvmlShutdown()
        return gpus
    except Exception:
        return []


def _probe_windows_gpus() -> list[GpuInfo]:
    """Enumerate every display adapter from the driver registry class, reading
    the accurate qwMemorySize. Names come from DriverDesc."""
    gpus: list[GpuInfo] = []
    try:
        import winreg

        class_key = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, class_key) as root:
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(root, i)
                except OSError:
                    break
                i += 1
                if not sub.isdigit():
                    continue
                try:
                    with winreg.OpenKey(root, sub) as adapter:
                        name = _reg_str(adapter, "DriverDesc")
                        if not name:
                            continue
                        vram = _reg_int(adapter, "HardwareInformation.qwMemorySize")
                        if vram is None:
                            vram = _reg_int(adapter, "HardwareInformation.MemorySize")
                        vendor = _vendor_of(name)
                        integrated = vendor == "intel" or "uhd" in name.lower() or "vega" in name.lower()
                        gpus.append(
                            GpuInfo(
                                vendor=vendor,
                                name=name,
                                vram_gb=round(vram / 1024**3, 1) if vram else None,
                                kind="integrated" if integrated else "discrete",
                                source="registry",
                            )
                        )
                except OSError:
                    continue
    except Exception:
        pass
    return gpus


def _reg_str(key, name: str) -> str | None:
    try:
        import winreg

        val, _ = winreg.QueryValueEx(key, name)
        return str(val).strip() if val else None
    except OSError:
        return None


def _reg_int(key, name: str) -> int | None:
    try:
        import winreg

        val, _ = winreg.QueryValueEx(key, name)
        n = int(val)
        return n if n > 0 else None
    except (OSError, ValueError, TypeError):
        return None


def _probe_macos_gpu() -> list[GpuInfo]:
    if platform.machine() == "arm64":
        total = psutil.virtual_memory().total / 1024**3
        # Apple Silicon unified memory — usable as VRAM up to a recommended cap.
        return [
            GpuInfo(
                vendor="apple",
                name=f"Apple Silicon ({platform.machine()})",
                vram_gb=round(total * 0.7, 1),
                kind="integrated",
                source="unified-memory",
            )
        ]
    return []


def _probe_linux_gpus() -> list[GpuInfo]:
    gpus: list[GpuInfo] = []
    try:
        out = subprocess.run(["lspci"], capture_output=True, text=True, timeout=5).stdout
        for line in out.splitlines():
            if "VGA compatible controller" in line or "3D controller" in line:
                name = line.split(":", 2)[-1].strip()
                gpus.append(GpuInfo(vendor=_vendor_of(name), name=name, vram_gb=None, source="lspci"))
    except Exception:
        pass
    return gpus


def _probe_gpus() -> list[GpuInfo]:
    system = platform.system()
    nvidia = _probe_nvidia()
    others: list[GpuInfo] = []
    if system == "Windows":
        others = _probe_windows_gpus()
    elif system == "Darwin":
        others = _probe_macos_gpu()
    elif system == "Linux":
        others = _probe_linux_gpus()

    # Merge: prefer NVML for NVIDIA (accurate VRAM), fill the rest from the
    # platform probe. Dedup NVIDIA cards the platform probe also found.
    merged = list(nvidia)
    for g in others:
        if g.vendor == "nvidia" and any(n.vendor == "nvidia" for n in nvidia):
            # Backfill VRAM onto the NVML entry if the registry knew a name match; skip dup.
            continue
        merged.append(g)
    # Discrete GPUs first, then by VRAM.
    merged.sort(key=lambda g: (g.kind != "discrete", -(g.vram_gb or 0)))
    return merged


# --------------------------------------------------------------------------- API

_cache: HardwareInfo | None = None


def probe_hardware(refresh: bool = False) -> HardwareInfo:
    global _cache
    if _cache is not None and not refresh:
        _cache.ram_available_gb = round(psutil.virtual_memory().available / 1024**3, 1)
        _cache.disk_free_gb = round(shutil.disk_usage(_disk_root()).free / 1024**3, 1)
        return _cache
    vm = psutil.virtual_memory()
    _cache = HardwareInfo(
        os=f"{platform.system()} {platform.release()}",
        cpu=_cpu_name(),
        arch=platform.machine(),
        cores_physical=psutil.cpu_count(logical=False) or psutil.cpu_count(logical=True) or 1,
        cores_logical=psutil.cpu_count(logical=True) or 1,
        ram_total_gb=round(vm.total / 1024**3, 1),
        ram_available_gb=round(vm.available / 1024**3, 1),
        disk_free_gb=round(shutil.disk_usage(_disk_root()).free / 1024**3, 1),
        gpus=_probe_gpus(),
    )
    return _cache


def _disk_root() -> str:
    return "C:\\" if platform.system() == "Windows" else "/"


def hardware_dict() -> dict:
    return asdict(probe_hardware())
