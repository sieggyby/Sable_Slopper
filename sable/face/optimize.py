"""Face detection pre-filter and perceptual hash dedup."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional


def has_face(image_path: str | Path) -> bool:
    """Return True if the image contains at least one face (HOG detector)."""
    try:
        import face_recognition
        import numpy as np
        from PIL import Image

        img = Image.open(str(image_path)).convert("RGB")
        arr = np.array(img)
        locations = face_recognition.face_locations(arr, model="hog")
        return len(locations) > 0
    except ImportError:
        # face_recognition not installed — skip pre-filter
        return True
    except Exception:
        return True


def phash(image_path: str | Path) -> Optional[str]:
    """Compute perceptual hash of an image."""
    try:
        import imagehash
        from PIL import Image
        img = Image.open(str(image_path))
        return str(imagehash.phash(img))
    except ImportError:
        return None
    except Exception:
        return None


def dedup_frames(frame_paths: list[Path], threshold: int = 10) -> list[Path]:
    """
    Remove near-duplicate frames using perceptual hashing.
    threshold: max hamming distance to consider duplicate (lower = stricter)
    Returns deduplicated list (preserving order).
    """
    try:
        import imagehash
        from PIL import Image
    except ImportError:
        return frame_paths

    seen_hashes: list[Any] = []
    result = []

    for path in frame_paths:
        try:
            h = imagehash.phash(Image.open(str(path)))
        except Exception:
            result.append(path)
            continue

        if not any(abs(h - prev) <= threshold for prev in seen_hashes):
            seen_hashes.append(h)
            result.append(path)

    return result


def filter_frames_with_faces(frame_paths: list[Path]) -> list[Path]:
    """Return only frames that contain at least one face."""
    try:
        import face_recognition
        import numpy as np
        from PIL import Image
    except ImportError:
        return frame_paths

    result = []
    for path in frame_paths:
        try:
            img = Image.open(str(path)).convert("RGB")
            arr = np.array(img)
            locs = face_recognition.face_locations(arr, model="hog")
            if locs:
                result.append(path)
        except Exception:
            result.append(path)  # include on error

    return result
