"""YouTube/URL download helper via yt-dlp."""
from __future__ import annotations

import hashlib
from pathlib import Path


def _is_url(s: str) -> bool:
    return s.startswith("http://") or s.startswith("https://")


def maybe_download(src: str) -> Path:
    """
    If src is a URL, download it with yt-dlp and return the local path.
    If src is already a local path, return it as-is.
    Downloads are cached in workspace/downloads/ keyed by URL hash.
    """
    if not _is_url(src):
        p = Path(src)
        if not p.exists():
            raise FileNotFoundError(f"Video file not found: {src}")
        return p

    from sable.shared.paths import downloads_dir
    try:
        import yt_dlp
    except ImportError:
        raise RuntimeError(
            "yt-dlp is required to download URLs. Install it: pip install yt-dlp"
        )

    url_hash = hashlib.sha256(src.encode()).hexdigest()[:12]
    dest_dir = downloads_dir() / url_hash
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Check if already downloaded
    existing = list(dest_dir.glob("*.mp4")) + list(dest_dir.glob("*.mkv")) + list(dest_dir.glob("*.webm"))
    if existing:
        return existing[0]

    ydl_opts = {
        "format": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best[height<=720]/best",
        "merge_output_format": "mp4",
        "outtmpl": str(dest_dir / "%(title)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([src])

    downloaded = list(dest_dir.glob("*.mp4")) + list(dest_dir.glob("*.mkv")) + list(dest_dir.glob("*.webm"))
    if not downloaded:
        raise RuntimeError(f"yt-dlp ran but no output file found in {dest_dir}")

    return downloaded[0]
