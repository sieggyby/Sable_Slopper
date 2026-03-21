#!/usr/bin/env python3
"""Automatically score a long source video and populate the brainrot library.

Reads existing library to compute per-tier need scores, slides windows across the
video's combined audio+motion signal, and registers the best non-overlapping clips.

Usage:
  python scripts/score_brainrot.py <video> [options]

Examples:
  python scripts/score_brainrot.py ~/Downloads/orbital.mp4 --tags "parkour,gameplay" --dry-run
  python scripts/score_brainrot.py ~/Downloads/orbital.mp4 --tags "gameplay" --skip-end 90
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Duration tier definitions
# ---------------------------------------------------------------------------
TIERS = [
    {"label": "15s", "duration": 15,  "target": 8,  "bucket": (10,  22)},
    {"label": "30s", "duration": 30,  "target": 15, "bucket": (23,  37)},
    {"label": "45s", "duration": 45,  "target": 8,  "bucket": (38,  52)},
    {"label": "60s", "duration": 60,  "target": 15, "bucket": (53,  75)},
    {"label": "90s", "duration": 90,  "target": 8,  "bucket": (76,  105)},
    {"label": "2m",  "duration": 120, "target": 6,  "bucket": (106, 150)},
    {"label": "5m",  "duration": 300, "target": 4,  "bucket": (151, 360)},
]


# ---------------------------------------------------------------------------
# Output naming
# ---------------------------------------------------------------------------

def resolve_output_name(dest_dir: Path, stem: str, label: str, index: int) -> Path:
    """Return collision-free path: stem_30s_01.mp4, stem_30s_01_v2.mp4, etc."""
    base = f"{stem}_{label}_{index:02d}.mp4"
    candidate = dest_dir / base
    if not candidate.exists():
        return candidate
    version = 2
    while True:
        candidate = dest_dir / f"{stem}_{label}_{index:02d}_v{version}.mp4"
        if not candidate.exists():
            return candidate
        version += 1


# ---------------------------------------------------------------------------
# Signal extraction
# ---------------------------------------------------------------------------

def extract_audio_signal(source: Path, total_duration: float) -> Optional[list[float]]:
    """Return per-second audio energy normalised to [0,1], or None on failure."""
    try:
        import librosa
        import numpy as np
        from sable.shared.ffmpeg import extract_audio

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            wav_path = Path(tmp.name)
        try:
            extract_audio(source, wav_path)
            y, sr = librosa.load(str(wav_path), sr=16000, mono=True)
        finally:
            wav_path.unlink(missing_ok=True)

        rms = librosa.feature.rms(y=y, hop_length=512)[0]
        frame_times = librosa.frames_to_time(range(len(rms)), sr=sr, hop_length=512)

        n_secs = int(total_duration) + 1
        per_sec = np.zeros(n_secs)
        counts = np.zeros(n_secs)
        for t, val in zip(frame_times, rms):
            s = int(t)
            if s < n_secs:
                per_sec[s] += val
                counts[s] += 1

        mask = counts > 0
        per_sec[mask] /= counts[mask]

        mx = per_sec.max()
        if mx > 0:
            per_sec /= mx
        return per_sec.tolist()

    except ImportError:
        print("  [warn] librosa not installed. Cannot compute audio signal.")
        return None
    except Exception as e:
        print(f"  [warn] Audio signal extraction failed: {e}")
        return None


def extract_motion_signal(source: Path, total_duration: float) -> Optional[list[float]]:
    """Return per-second motion density normalised to [0,1], or None on failure."""
    try:
        import cv2
        import numpy as np

        cap = cv2.VideoCapture(str(source))
        if not cap.isOpened():
            print(f"  [warn] OpenCV could not open video: {source}")
            return None

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        # Sample at 2fps
        sample_interval = max(1, int(fps / 2))

        n_secs = int(total_duration) + 1
        per_sec = np.zeros(n_secs)
        counts = np.zeros(n_secs)

        prev_gray = None
        frame_idx = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            if frame_idx % sample_interval == 0:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
                if prev_gray is not None:
                    motion = float(np.abs(gray - prev_gray).mean())
                    t = int(frame_idx / fps)
                    if t < n_secs:
                        per_sec[t] += motion
                        counts[t] += 1
                prev_gray = gray
            frame_idx += 1
        cap.release()

        mask = counts > 0
        per_sec[mask] /= counts[mask]

        if per_sec.max() == 0:
            print("  [warn] All motion scores are zero (static screen). Falling back to audio-only.")
            return None

        per_sec /= per_sec.max()
        return per_sec.tolist()

    except ImportError:
        print("  [warn] OpenCV (cv2) not installed. Falling back to audio-only scoring.")
        return None
    except Exception as e:
        print(f"  [warn] Motion signal extraction failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Signal combination & smoothing
# ---------------------------------------------------------------------------

def build_signal(
    audio: Optional[list[float]],
    motion: Optional[list[float]],
    n: int,
) -> list[float]:
    """Combine audio + motion into a composite signal array of length n."""
    import numpy as np

    def to_arr(sig: Optional[list[float]]) -> "np.ndarray":
        if sig is None:
            return np.zeros(n)
        arr = np.array(sig[:n], dtype=float)
        if len(arr) < n:
            arr = np.pad(arr, (0, n - len(arr)))
        return arr

    if audio is not None and motion is not None:
        sig = 0.55 * to_arr(audio) + 0.45 * to_arr(motion)
    elif audio is not None:
        sig = to_arr(audio)
    elif motion is not None:
        sig = to_arr(motion)
    else:
        return [0.5] * n  # flat fallback — no signal available

    return sig.tolist()


def smooth(signal: list[float], window: int = 3) -> list[float]:
    """Apply a rolling mean of `window` seconds."""
    import numpy as np
    arr = np.array(signal)
    kernel = np.ones(window) / window
    smoothed = np.convolve(arr, kernel, mode="same")
    return smoothed.tolist()


# ---------------------------------------------------------------------------
# Library helpers
# ---------------------------------------------------------------------------

def has_audio_stream(source: Path) -> bool:
    from sable.shared.ffmpeg import probe
    info = probe(source)
    return any(s.get("codec_type") == "audio" for s in info.get("streams", []))


def compute_need_scores(existing: list[dict]) -> dict[str, float]:
    """Compute need score per tier: target / (current_count + 1)."""
    counts: dict[str, int] = {t["label"]: 0 for t in TIERS}
    for entry in existing:
        dur = entry.get("duration", 0)
        for tier in TIERS:
            lo, hi = tier["bucket"]
            if lo <= dur <= hi:
                counts[tier["label"]] += 1
                break
    return {
        tier["label"]: tier["target"] / (counts[tier["label"]] + 1)
        for tier in TIERS
    }


# ---------------------------------------------------------------------------
# Window scoring & selection
# ---------------------------------------------------------------------------

def score_windows(
    signal: list[float],
    tier_duration: int,
    scorable_end: int,
    quality_pct: int,
) -> list[dict]:
    """Return windows passing quality threshold, sorted by score descending."""
    import numpy as np

    arr = np.array(signal)
    windows = []
    for start in range(0, scorable_end - tier_duration + 1):
        w_score = float(arr[start : start + tier_duration].mean())
        windows.append({"start": start, "score": w_score})

    if not windows:
        return []

    threshold = float(np.percentile([w["score"] for w in windows], quality_pct))
    passing = [w for w in windows if w["score"] >= threshold]
    passing.sort(key=lambda x: x["score"], reverse=True)
    return passing


def select_non_overlapping(
    windows: list[dict],
    tier_duration: int,
    max_count: int,
) -> list[dict]:
    """Greedy non-overlapping selection from score-sorted window list."""
    selected: list[dict] = []
    occupied: list[tuple[int, int]] = []

    for w in windows:
        start = w["start"]
        end = start + tier_duration
        if any(s < end and start < e for s, e in occupied):
            continue
        selected.append(w)
        occupied.append((start, end))
        if len(selected) >= max_count:
            break

    return selected


def classify_energy(score: float) -> str:
    """Classify a window score into low / medium / high relative to [0,1] range."""
    if score >= 0.65:
        return "high"
    elif score >= 0.35:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Score a source video and auto-populate the brainrot library."
    )
    parser.add_argument("video", help="Source video file path")
    parser.add_argument(
        "--tags",
        default="",
        help="Comma-separated tags applied to all clips (e.g. 'parkour,gameplay')",
    )
    parser.add_argument(
        "--skip-end",
        type=float,
        default=120.0,
        metavar="SECONDS",
        help="Seconds to ignore at end of video (default: 120)",
    )
    parser.add_argument(
        "--quality",
        type=int,
        default=50,
        metavar="N",
        help="Quality threshold: minimum percentile of window scores to accept (default: 50)",
    )
    parser.add_argument(
        "--output-name",
        metavar="PREFIX",
        help="Prefix for output filenames (default: source video stem)",
    )
    parser.add_argument(
        "--no-audio",
        action="store_true",
        help="Ignore audio stream even if present (motion-only scoring)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print extraction plan, no files written",
    )
    args = parser.parse_args()

    source = Path(args.video).expanduser().resolve()
    if not source.exists():
        sys.exit(f"Source video not found: {source}")

    tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    stem = args.output_name or source.stem

    # --- Probe ---
    from sable.shared.ffmpeg import get_duration
    from sable.shared.paths import brainrot_dir
    from sable.clip.brainrot import load_index, add_video

    print(f"Probing {source.name} ...")
    try:
        total_duration = get_duration(source)
    except Exception as e:
        sys.exit(f"Cannot read video (corrupt or unreadable): {e}")

    if total_duration <= 0:
        sys.exit("Video has zero duration — cannot process.")

    print(f"  Duration   : {total_duration:.1f}s")
    scorable_end = max(0, int(total_duration) - int(args.skip_end))
    print(f"  Scorable   : 0 → {scorable_end}s  (skip_end={args.skip_end}s)")

    # --- Signal extraction ---
    has_audio = has_audio_stream(source) and not args.no_audio
    if args.no_audio:
        print("  [--no-audio] Skipping audio signal.")
    elif not has_audio:
        print("  [warn] No audio stream detected. Using motion-only scoring.")

    audio_sig: Optional[list[float]] = None
    motion_sig: Optional[list[float]] = None

    if has_audio:
        print("Extracting audio signal ...")
        audio_sig = extract_audio_signal(source, total_duration)
        if audio_sig is None:
            print("  [warn] Falling back without audio signal.")

    print("Extracting motion signal ...")
    motion_sig = extract_motion_signal(source, total_duration)

    if audio_sig is None and motion_sig is None:
        sys.exit(
            "Cannot compute signal: both audio and motion extraction failed.\n"
            "Install missing deps: pip install librosa opencv-python numpy"
        )

    if audio_sig is None:
        print("  Signal: motion-only (weight 1.0)")
    elif motion_sig is None:
        print("  Signal: audio-only (weight 1.0)")
    else:
        print("  Signal: combined (audio 0.55, motion 0.45)")

    n_secs = int(total_duration) + 1
    raw_signal = build_signal(audio_sig, motion_sig, n_secs)
    signal = smooth(raw_signal, window=3)

    # --- Need scores ---
    existing = load_index()
    needs = compute_need_scores(existing)

    # Process tiers in highest-need-first order
    tiers_sorted = sorted(TIERS, key=lambda t: needs[t["label"]], reverse=True)

    # --- Window scoring ---
    dest_dir = brainrot_dir()
    plan: list[dict] = []

    print(
        f"\nScoring windows  "
        f"(quality ≥ {args.quality}th percentile per tier, "
        f"tiers ordered by need) ..."
    )

    for tier in tiers_sorted:
        label = tier["label"]
        dur = tier["duration"]
        target = tier["target"]

        if dur > scorable_end:
            print(
                f"  [{label}] Skip — scorable range ({scorable_end}s) "
                f"< tier duration ({dur}s)"
            )
            continue

        windows = score_windows(signal, dur, scorable_end, args.quality)
        if not windows:
            print(f"  [{label}] 0 clips — quality threshold eliminated all candidates")
            continue

        selected = select_non_overlapping(windows, dur, target)
        print(
            f"  [{label}] {len(selected)} clip(s)  "
            f"(need={needs[label]:.2f}, passing={len(windows)})"
        )

        for i, w in enumerate(selected, 1):
            out_path = resolve_output_name(dest_dir, stem, label, i)
            plan.append({
                "tier": label,
                "duration": dur,
                "start": w["start"],
                "end": w["start"] + dur,
                "score": w["score"],
                "energy": classify_energy(w["score"]),
                "out_path": out_path,
                "index": i,
            })

    # --- Print plan table ---
    print(f"\nExtraction plan — {len(plan)} clip(s):")
    if plan:
        print(f"  {'Tier':<6}  {'Start':>6}  {'End':>6}  {'Score':>6}  {'Energy':<8}  Output")
        print(f"  {'-'*6}  {'-'*6}  {'-'*6}  {'-'*6}  {'-'*8}  {'-'*32}")
        for item in sorted(plan, key=lambda x: (x["tier"], x["index"])):
            print(
                f"  {item['tier']:<6}  {item['start']:>5}s  {item['end']:>5}s  "
                f"{item['score']:>6.3f}  {item['energy']:<8}  {item['out_path'].name}"
            )

    if args.dry_run:
        print(f"\n[dry-run] No files written. Would extract {len(plan)} clip(s).")
        return

    if not plan:
        print("\nNo clips to extract.")
        return

    # --- Execute ---
    from sable.shared.ffmpeg import extract_clip

    print(f"\nExtracting to {dest_dir} ...")
    for i, item in enumerate(plan, 1):
        out_path = item["out_path"]
        print(f"  [{i}/{len(plan)}] {item['tier']} @ {item['start']}s → {out_path.name} ...")
        extract_clip(source, out_path, item["start"], item["end"])
        entry = add_video(out_path, energy=item["energy"], tags=tags, copy=False)
        print(
            f"    Registered: duration={entry['duration']}s  "
            f"energy={entry['energy']}  tags={entry['tags']}"
        )

    print(f"\nDone. {len(plan)} clip(s) added to brainrot library.")


if __name__ == "__main__":
    main()
