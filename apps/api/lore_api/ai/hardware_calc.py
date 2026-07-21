"""The local-model recommendation calculator. Pure functions, no I/O — the
numbers below are the whole contract, and the unit tests pin them.

Memory model (Q4_K_M quantization, the Ollama default for most tags):
  weight footprint ≈ params_B × 0.55 GB
  KV cache + runtime overhead ≈ 1.5 GB at 8k context
  budget = VRAM × 0.9 when a GPU with known VRAM exists, else available RAM × 0.6
"""

from __future__ import annotations

from dataclasses import dataclass

from .hardware import HardwareInfo

GB_PER_B_PARAMS_Q4 = 0.55
KV_OVERHEAD_GB = 1.5
GPU_BUDGET_FACTOR = 0.9
CPU_BUDGET_FACTOR = 0.6


@dataclass(frozen=True)
class CandidateModel:
    tag: str  # ollama pull tag
    label: str
    params_b: float
    quality: int  # 1 (small helper) … 5 (frontier-class open model)
    disk_gb: float
    note: str


# Curated ladder of current open models, small to large. Quality is a coarse
# editorial tier for ranking within a memory budget, not a benchmark score.
MODEL_LADDER: list[CandidateModel] = [
    CandidateModel("qwen3:0.6b", "Qwen3 0.6B", 0.6, 1, 0.5, "tiny and instant; good for autocomplete only"),
    CandidateModel("gemma3:1b", "Gemma 3 1B", 1.0, 1, 0.8, "very fast helper for tagging and titles"),
    CandidateModel("qwen3:1.7b", "Qwen3 1.7B", 1.7, 2, 1.4, "small but coherent; fine for short summaries"),
    CandidateModel("gemma3:4b", "Gemma 3 4B", 4.0, 2, 3.3, "solid small all-rounder with vision"),
    CandidateModel("qwen3:4b", "Qwen3 4B", 4.0, 2, 2.6, "strong reasoning for its size"),
    CandidateModel("llama3.1:8b", "Llama 3.1 8B", 8.0, 3, 4.9, "the classic dependable mid-size assistant"),
    CandidateModel("qwen3:8b", "Qwen3 8B", 8.0, 3, 5.2, "great chat + tool use at mid size"),
    CandidateModel("gemma3:12b", "Gemma 3 12B", 12.0, 3, 8.1, "noticeably richer writing than 8B models"),
    CandidateModel("qwen3:14b", "Qwen3 14B", 14.0, 4, 9.3, "excellent quality/speed balance on 12GB+ GPUs"),
    CandidateModel("phi4:14b", "Phi-4 14B", 14.0, 4, 9.1, "strong reasoning, compact context"),
    CandidateModel("mistral-small3.2:24b", "Mistral Small 3.2 24B", 24.0, 4, 15.0, "near-frontier quality; wants 24GB VRAM"),
    CandidateModel("qwen3:32b", "Qwen3 32B", 32.0, 5, 20.2, "top open quality most 24GB GPUs can still fit"),
    CandidateModel("llama3.3:70b", "Llama 3.3 70B", 70.0, 5, 42.5, "frontier-class; needs 48GB+ VRAM or lots of patience"),
]


def model_footprint_gb(params_b: float) -> float:
    return round(params_b * GB_PER_B_PARAMS_Q4 + KV_OVERHEAD_GB, 1)


@dataclass
class Budget:
    gpu_gb: float | None
    cpu_gb: float
    gpu_name: str | None


def compute_budget(hw: HardwareInfo) -> Budget:
    usable_gpus = [g for g in hw.gpus if g.vram_gb]
    best = max(usable_gpus, key=lambda g: g.vram_gb or 0, default=None)
    return Budget(
        gpu_gb=round(best.vram_gb * GPU_BUDGET_FACTOR, 1) if best and best.vram_gb else None,
        cpu_gb=round(hw.ram_available_gb * CPU_BUDGET_FACTOR, 1),
        gpu_name=best.name if best else None,
    )


@dataclass
class Fit:
    model: CandidateModel
    footprint_gb: float
    fits_gpu: bool
    fits_cpu: bool
    fits_disk: bool
    speed: str  # "fast" | "ok" | "slow" | "no"


def fit_check(model: CandidateModel, hw: HardwareInfo) -> Fit:
    budget = compute_budget(hw)
    footprint = model_footprint_gb(model.params_b)
    fits_gpu = budget.gpu_gb is not None and footprint <= budget.gpu_gb
    fits_cpu = footprint <= budget.cpu_gb
    fits_disk = model.disk_gb <= hw.disk_free_gb
    if not fits_disk or (not fits_gpu and not fits_cpu):
        speed = "no"
    elif fits_gpu:
        speed = "fast"
    elif model.params_b <= 8:
        speed = "ok"  # small models are tolerable on CPU
    else:
        speed = "slow"
    return Fit(model, footprint, fits_gpu, fits_cpu, fits_disk, speed)


@dataclass
class Recommendation:
    model: CandidateModel
    fit: Fit
    reasoning: str


def _reasoning(fit: Fit, budget: Budget) -> str:
    m = fit.model
    if fit.fits_gpu and budget.gpu_name:
        return (
            f"Your {budget.gpu_name} has {budget.gpu_gb} GB of usable VRAM — {m.label} needs about "
            f"{fit.footprint_gb} GB at 4-bit with 8k context, so it runs fully on the GPU. {m.note.capitalize()}."
        )
    if fit.fits_cpu:
        pace = "at a comfortable pace" if fit.speed == "ok" else "slowly — fine for background jobs"
        return (
            f"{m.label} needs about {fit.footprint_gb} GB; it fits your available RAM "
            f"(budgeted {budget.cpu_gb} GB) and runs on the CPU {pace}. {m.note.capitalize()}."
        )
    return f"{m.label} needs about {fit.footprint_gb} GB — more than this machine can offer right now."


def recommend(hw: HardwareInfo, top_n: int = 3) -> list[Recommendation]:
    """Top picks: best quality that fits, preferring GPU-resident models, plus
    one fast small model for background tasks (autocomplete/tagging)."""
    budget = compute_budget(hw)
    fits = [fit_check(m, hw) for m in MODEL_LADDER]
    runnable = [f for f in fits if f.speed != "no"]
    if not runnable:
        return []
    # Rank: GPU-fit first, then quality, then smaller (faster) among equals.
    ranked = sorted(
        runnable, key=lambda f: (f.fits_gpu, f.model.quality, -f.model.params_b), reverse=True
    )
    picks: list[Fit] = []
    for f in ranked:
        if len(picks) >= top_n - 1:
            break
        if all(p.model.tag != f.model.tag for p in picks):
            picks.append(f)
    # Always include the best tiny model as the background workhorse.
    small = next(
        (f for f in ranked if f.model.params_b <= 4 and all(p.model.tag != f.model.tag for p in picks)),
        None,
    )
    if small:
        picks.append(small)
    return [Recommendation(f.model, f, _reasoning(f, budget)) for f in picks[:top_n]]
