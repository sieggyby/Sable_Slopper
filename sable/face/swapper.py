"""Replicate API face swap with model fallback chain."""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

from sable import config as cfg

logger = logging.getLogger(__name__)

_TIMEOUT_S = 300.0
_MAX_RETRIES = 3
_INITIAL_BACKOFF = 2.0
_RETRYABLE_STATUS = {429, 502, 503}

_MODEL_CHAIN = [
    "cdingspub/facefusion:latest",
    "yan-ops/faceswap:latest",
    "omniedge/faceswap:latest",
]

_MODEL_NAMES = ["facefusion", "yan-ops/faceswap", "omniedge/faceswap"]


def _get_replicate():
    import replicate
    api_key = cfg.require_key("replicate_api_key")
    return replicate.Client(api_token=api_key)


def swap_image(
    source_path: str | Path,
    reference_path: str | Path,
    output_path: str | Path,
    model_index: int = 0,
    org_id: str | None = None,
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
            _log_replicate_cost(org_id, "replicate_face_swap_image", 0.01)
            return str(output_path), model_name
        except Exception as e:
            errors.append(f"{model_name}: {e}")
            continue

    raise RuntimeError(
        "All face swap models failed:\n" + "\n".join(errors)
    )


def _log_replicate_cost(
    org_id: str | None, call_type: str, estimated_cost: float
) -> None:
    """Log Replicate cost to sable.db. Non-fatal."""
    if not org_id:
        return
    try:
        from sable.platform.db import get_db
        from sable.platform.cost import log_cost
        conn = get_db()
        try:
            log_cost(conn, org_id, call_type, estimated_cost, model="replicate")
        finally:
            conn.close()
    except Exception as e:
        logger.warning("Failed to log Replicate cost for org %s: %s", org_id, e)


def _call_model(replicate, model: str, source: Path, reference: Path):
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            with open(source, "rb") as sf, open(reference, "rb") as rf:
                prediction = replicate.predictions.create(
                    model=model,
                    input={
                        "source_image": sf,
                        "target_image": rf,
                    },
                )
            logger.info("Replicate prediction %s created", prediction.id)
            # Poll with timeout
            deadline = time.monotonic() + _TIMEOUT_S
            while prediction.status not in ("succeeded", "failed", "canceled"):
                if time.monotonic() > deadline:
                    raise TimeoutError(
                        f"Replicate prediction {prediction.id} timed out after {_TIMEOUT_S}s"
                    )
                time.sleep(2.0)
                prediction.reload()

            if prediction.status == "failed":
                raise RuntimeError(
                    f"Replicate prediction {prediction.id} failed: {prediction.error}"
                )
            if prediction.status == "canceled":
                raise RuntimeError(
                    f"Replicate prediction {prediction.id} was canceled"
                )
            return prediction.output
        except Exception as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status in _RETRYABLE_STATUS and attempt < _MAX_RETRIES - 1:
                delay = _INITIAL_BACKOFF * (2 ** attempt)
                logger.warning(
                    "Replicate %s (attempt %d/%d), retrying in %.1fs",
                    status, attempt + 1, _MAX_RETRIES, delay,
                )
                time.sleep(delay)
                last_exc = e
                continue
            raise
    raise last_exc  # type: ignore[misc]


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
