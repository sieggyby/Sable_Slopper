"""faster-whisper transcription backend with transcript caching."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from sable.shared.paths import transcript_cache_dir


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


_CACHE_VERSION = "v4"


def _cache_path(video_path: Path, model: str) -> Path:
    key = _file_hash(video_path)
    return transcript_cache_dir() / f"{key}-{model}-{_CACHE_VERSION}.json"


# AR5-26: module-level cache so WhisperModel is only loaded once per process per model size
_MODEL_CACHE: dict = {}  # str → WhisperModel instance


def _get_model(model: str):
    """Return a cached WhisperModel, loading it on first use."""
    if model not in _MODEL_CACHE:
        from faster_whisper import WhisperModel
        _MODEL_CACHE[model] = WhisperModel(model, device="auto", compute_type="int8")
    return _MODEL_CACHE[model]


def _load_model(model: str):
    """Deprecated: use _get_model() for caching. Kept for backward compatibility."""
    return _get_model(model)


def transcribe(
    video_path: str | Path,
    model: str = "base.en",
    force: bool = False,
) -> dict:
    """
    Transcribe a video file. Returns a dict with:
      - text: full transcript string
      - segments: list of {start, end, text} dicts (phrase-level)
      - words: list of {start, end, text} dicts (word-level)

    Results are cached by file hash.
    """
    video_path = Path(video_path)
    cache = _cache_path(video_path, model)

    if cache.exists() and not force:
        with open(cache) as f:
            return json.load(f)

    wm = _get_model(model)
    segments_iter, _info = wm.transcribe(
        str(video_path),
        word_timestamps=True,
        language="en" if model.endswith(".en") else None,
        condition_on_previous_text=False,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
    )

    transcript = _normalize_faster_whisper(segments_iter)

    with open(cache, "w") as f:
        json.dump(transcript, f)

    return transcript


def _normalize_faster_whisper(segments_iter) -> dict:
    phrase_segments = []
    word_segments = []

    for seg in segments_iter:
        text = seg.text.strip()
        if not text:
            continue
        phrase_segments.append({"start": seg.start, "end": seg.end, "text": text})
        for w in (seg.words or []):
            word_text = w.word.strip()
            if word_text:
                word_segments.append({"start": w.start, "end": w.end, "text": word_text})

    word_segments = _fix_word_timing(word_segments)

    full_text = " ".join(s["text"] for s in phrase_segments).strip()
    return {"text": full_text, "segments": phrase_segments, "words": word_segments}


_MIN_WORD_MS = 100    # words shorter than this get extended
_MICRO_GAP_MS = 0.08  # gaps under 80ms get filled (seconds)


def _fix_word_timing(words: list[dict]) -> list[dict]:
    """Overlap removal, micro-gap fill, minimum duration enforcement."""
    if not words:
        return words
    words = [w.copy() for w in words]

    for i in range(len(words) - 1):
        cur, nxt = words[i], words[i + 1]
        if cur["end"] > nxt["start"]:
            mid = (cur["end"] + nxt["start"]) / 2
            cur["end"] = mid
            nxt["start"] = mid
        elif nxt["start"] - cur["end"] < _MICRO_GAP_MS:
            cur["end"] = nxt["start"]

    for i, w in enumerate(words):
        min_dur = _MIN_WORD_MS / 1000
        if w["end"] - w["start"] < min_dur:
            new_end = w["start"] + min_dur
            if i + 1 < len(words) and new_end > words[i + 1]["start"]:
                new_end = words[i + 1]["start"]
            w["end"] = new_end

    return words
