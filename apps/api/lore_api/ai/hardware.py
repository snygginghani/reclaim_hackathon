"""Host hardware probe — feeds the local-model recommendation calculator."""

from __future__ import annotations

import platform
import shutil
from dataclasses import dataclass, field

import psutil


@dataclass
class GpuInfo:
    vendor: str  # "nvidia" | "amd" | "intel" | "unknown"
    name: str
    vram_gb: float | None  # None when the platform can't report it reliably


@dataclass
class HardwareInfo:
    os: str
    cpu: str
    cores: int
    ram_total_gb: float
    ram_available_gb: float
    disk_free_gb: float
    gpus: list[GpuInfo] = field(default_factory=list)


def _probe_nvidia() -> list[GpuInfo]:
    try:
        import pynvml

        pynvml.nvmlInit()
        gpus = []
        for i in range(pynvml.nvmlDeviceGetCount()):
            handle = pynvml.nvmlDeviceGetHandleByIndex(i)
            name = pynvml.nvmlDeviceGetName(handle)
            if isinstance(name, bytes):
                name = name.decode()
            mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
            gpus.append(GpuInfo(vendor="nvidia", name=name, vram_gb=round(mem.total / 1024**3, 1)))
        pynvml.nvmlShutdown()
        return gpus
    except Exception:
        return []


def _probe_other_gpus() -> list[GpuInfo]:
    """Best-effort non-NVIDIA detection. VRAM is left unknown rather than
    guessed: Windows' AdapterRAM lies for iGPUs and >4GB cards, and a wrong
    number would poison the fit calculator."""
    gpus: list[GpuInfo] = []
    if platform.system() == "Windows":
        try:
            import subprocess

            out = subprocess.run(
                ["wmic", "path", "win32_VideoController", "get", "Name"],
                capture_output=True, text=True, timeout=10,
            ).stdout
            for line in out.splitlines()[1:]:
                name = line.strip()
                if not name or "nvidia" in name.lower():
                    continue
                vendor = (
                    "amd" if any(k in name.lower() for k in ("amd", "radeon"))
                    else "intel" if "intel" in name.lower()
                    else "unknown"
                )
                gpus.append(GpuInfo(vendor=vendor, name=name, vram_gb=None))
        except Exception:
            pass
    elif platform.system() == "Darwin":
        # Apple Silicon: unified memory serves as VRAM; treat as GPU with ~65% of RAM.
        machine = platform.machine()
        if machine == "arm64":
            total = psutil.virtual_memory().total / 1024**3
            gpus.append(
                GpuInfo(vendor="apple", name=f"Apple Silicon ({machine})", vram_gb=round(total * 0.65, 1))
            )
    return gpus


_cache: HardwareInfo | None = None


def probe_hardware(refresh: bool = False) -> HardwareInfo:
    global _cache
    if _cache is not None and not refresh:
        # RAM availability drifts; refresh the cheap parts on every call.
        _cache.ram_available_gb = round(psutil.virtual_memory().available / 1024**3, 1)
        return _cache
    vm = psutil.virtual_memory()
    _cache = HardwareInfo(
        os=f"{platform.system()} {platform.release()}",
        cpu=platform.processor() or platform.machine(),
        cores=psutil.cpu_count(logical=True) or 1,
        ram_total_gb=round(vm.total / 1024**3, 1),
        ram_available_gb=round(vm.available / 1024**3, 1),
        disk_free_gb=round(shutil.disk_usage("/").free / 1024**3, 1),
        gpus=_probe_nvidia() + _probe_other_gpus(),
    )
    return _cache
