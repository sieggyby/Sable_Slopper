"""Cost estimation and budget enforcement for face swaps."""
from __future__ import annotations

from typing import Optional


# Rough cost estimates per Replicate prediction (USD)
_MODEL_COSTS = {
    "facefusion": 0.012,       # per image
    "yan-ops/faceswap": 0.008,
    "omniedge/faceswap": 0.006,
}

_VIDEO_FRAME_COST_MULTIPLIER = 1.0  # cost × frames


def estimate_image_cost(model: str = "facefusion") -> float:
    return _MODEL_COSTS.get(model, 0.01)


def estimate_video_cost(
    duration_seconds: float,
    fps: float = 30.0,
    strategy: str = "frame-by-frame",
    model: str = "facefusion",
) -> dict:
    """Estimate cost for a video face swap."""
    if strategy == "native":
        # Native video model — flat cost estimate
        cost = estimate_image_cost(model) * 5  # rough multiplier
        frames = 0
    else:
        frames = int(duration_seconds * fps)
        cost = frames * estimate_image_cost(model) * 0.8  # batch discount

    return {
        "strategy": strategy,
        "duration_seconds": duration_seconds,
        "estimated_frames": frames,
        "cost_usd": round(cost, 4),
        "model": model,
    }


def check_budget(estimated_cost: float, max_cost: Optional[float]) -> None:
    """Raise if estimated cost exceeds budget."""
    if max_cost is not None and estimated_cost > max_cost:
        raise RuntimeError(
            f"Estimated cost ${estimated_cost:.4f} exceeds budget ${max_cost:.4f}. "
            "Increase --max-cost or use --dry-run to preview."
        )


def format_cost_estimate(estimate: dict) -> str:
    lines = [
        f"Strategy     : {estimate['strategy']}",
        f"Duration     : {estimate.get('duration_seconds', 0):.1f}s",
        f"Model        : {estimate['model']}",
    ]
    if estimate.get("estimated_frames"):
        lines.append(f"Frames       : {estimate['estimated_frames']}")
    lines.append(f"Estimated    : ${estimate['cost_usd']:.4f}")
    return "\n".join(lines)
