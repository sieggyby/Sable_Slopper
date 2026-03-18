"""Whisper-cpp integration with audio extraction and transcript caching."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from sable.shared.ffmpeg import extract_audio
from sable.shared.paths import transcript_cache_dir


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _cache_path(video_path: Path) -> Path:
    key = _file_hash(video_path)
    return transcript_cache_dir() / f"{key}.json"


def require_whisper() -> str:
    """Find whisper-cpp binary."""
    for name in ("whisper-cli", "whisper-cpp", "whisper", "main"):
        path = shutil.which(name)
        if path:
            return path
    raise RuntimeError(
        "whisper-cpp not found. Install it: brew install whisper-cpp  "
        "or build from https://github.com/ggerganov/whisper.cpp"
    )


def transcribe(
    video_path: str | Path,
    model: str = "base.en",
    force: bool = False,
) -> dict:
    """
    Transcribe a video file. Returns a dict with:
      - text: full transcript string
      - segments: list of {start, end, text} dicts (word-level if available)

    Results are cached by file hash.
    """
    video_path = Path(video_path)
    cache = _cache_path(video_path)

    if cache.exists() and not force:
        with open(cache) as f:
            return json.load(f)

    whisper = require_whisper()

    with tempfile.TemporaryDirectory() as tmp:
        audio = Path(tmp) / "audio.wav"
        extract_audio(video_path, audio)

        output_json = Path(tmp) / "transcript"
        result = subprocess.run(
            [
                whisper,
                "-m", _find_model(model),
                "-f", str(audio),
                "--output-json",
                "--output-file", str(output_json),
                "--word-thold", "0.01",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Whisper failed:\n{result.stderr}\n\n"
                "Make sure whisper-cpp is installed and the model file exists.\n"
                "Download models: bash scripts/setup_whisper.sh"
            )

        json_file = Path(tmp) / "transcript.json"
        if not json_file.exists():
            # Fallback: parse text output
            transcript = {"text": result.stdout.strip(), "segments": []}
        else:
            with open(json_file) as f:
                raw = json.load(f)
            transcript = _normalize_whisper_output(raw)

    # Cache it
    with open(cache, "w") as f:
        json.dump(transcript, f)

    return transcript


def _find_model(model: str) -> str:
    """Locate a whisper model file."""
    import os
    search_dirs = [
        Path.home() / ".sable" / "models",
        Path("/opt/homebrew/share/whisper-cpp"),   # brew install whisper-cpp
        Path("/opt/homebrew/share/whisper-cpp/models"),
        Path("/usr/local/share/whisper"),
        Path.home() / "Library" / "Application Support" / "whisper.cpp",
    ]
    model_filename = f"ggml-{model}.bin"
    for d in search_dirs:
        candidate = d / model_filename
        if candidate.exists():
            return str(candidate)

    # Try as-is (user might pass full path)
    if Path(model).exists():
        return model

    raise RuntimeError(
        f"Whisper model '{model}' not found.\n"
        f"Download: whisper-cpp --download-model {model}\n"
        f"Or place ggml-{model}.bin in ~/.sable/models/"
    )


def _normalize_whisper_output(raw: dict) -> dict:
    """Normalize whisper.cpp JSON output to standard format."""
    segments = []
    for seg in raw.get("transcription", []):
        tokens = seg.get("tokens", [])
        if tokens:
            for tok in tokens:
                if tok.get("text", "").strip():
                    segments.append({
                        "start": tok.get("offsets", {}).get("from", 0) / 1000.0,
                        "end": tok.get("offsets", {}).get("to", 0) / 1000.0,
                        "text": tok["text"],
                    })
        else:
            segments.append({
                "start": seg.get("offsets", {}).get("from", 0) / 1000.0,
                "end": seg.get("offsets", {}).get("to", 0) / 1000.0,
                "text": seg.get("text", ""),
            })

    full_text = " ".join(s["text"] for s in segments).strip()
    return {"text": full_text, "segments": segments}
