"""Replicate API face swap with model fallback chain."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

from sable import config as cfg

_MODEL_CHAIN = [
    "cdingspub/facefusion:latest",
    "yan-ops/faceswap:latest",
    "omniedge/faceswap:latest",
]

_MODEL_NAMES = ["facefusion", "yan-ops/faceswap", "omniedge/faceswap"]


def _get_replicate():
    import replicate
    api_key = cfg.require_key("replicate_api_key")
    import os
    os.environ["REPLICATE_API_TOKEN"] = api_key
    return replicate


def swap_image(
    source_path: str | Path,
    reference_path: str | Path,
    output_path: str | Path,
    model_index: int = 0,
) -> tuple[str, str]:
    """
    Swap face in source_path with face from reference_path.
    Returns (output_path_str, model_used).
    Falls back through model chain on failure.
    """
    source_path = Path(source_path)
    reference_path = Path(reference_path)
    output_path = Path(output_path)

    replicate = _get_replicate()
    errors = []

    for i in range(model_index, len(_MODEL_CHAIN)):
        model = _MODEL_CHAIN[i]
        model_name = _MODEL_NAMES[i]
        try:
            result = _call_model(replicate, model, source_path, reference_path)
            _save_result(result, output_path)
            return str(output_path), model_name
        except Exception as e:
            errors.append(f"{model_name}: {e}")
            continue

    raise RuntimeError(
        f"All face swap models failed:\n" + "\n".join(errors)
    )


def _call_model(replicate, model: str, source: Path, reference: Path):
    with open(source, "rb") as sf, open(reference, "rb") as rf:
        output = replicate.run(
            model,
            input={
                "source_image": sf,
                "target_image": rf,
            },
        )
    return output


def _save_result(result, output_path: Path) -> None:
    """Save Replicate output (URL or bytes-like) to file."""
    import urllib.request

    output_path.parent.mkdir(parents=True, exist_ok=True)

    if hasattr(result, "read"):
        with open(output_path, "wb") as f:
            f.write(result.read())
    elif isinstance(result, str) and result.startswith("http"):
        urllib.request.urlretrieve(result, str(output_path))
    elif isinstance(result, (list, tuple)) and result:
        _save_result(result[0], output_path)
    else:
        raise RuntimeError(f"Unexpected Replicate output type: {type(result)}")
