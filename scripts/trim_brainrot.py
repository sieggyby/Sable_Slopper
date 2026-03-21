#!/usr/bin/env python3
"""Slice named segments from a long video and register them in the brainrot library.

Usage:
  python scripts/trim_brainrot.py <video> --segment START END ENERGY TAGS [...]
  python scripts/trim_brainrot.py <video> --from-yaml segments.yaml
  python scripts/trim_brainrot.py <video> --segment 0 30 high "test" --dry-run
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml


def parse_time(t: str) -> float:
    """Accept seconds (float) or MM:SS / H:MM:SS strings."""
    if ":" not in t:
        return float(t)
    parts = t.split(":")
    if len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    raise ValueError(f"Cannot parse time: {t!r}")


def resolve_output_name(dest_dir: Path, stem: str, index: int) -> Path:
    """Return a collision-free path: stem_01.mp4, stem_01_v2.mp4, etc."""
    base = f"{stem}_{index:02d}.mp4"
    candidate = dest_dir / base
    if not candidate.exists():
        return candidate
    version = 2
    while True:
        candidate = dest_dir / f"{stem}_{index:02d}_v{version}.mp4"
        if not candidate.exists():
            return candidate
        version += 1


def load_segments_from_yaml(path: str) -> list[dict]:
    with open(path) as f:
        data = yaml.safe_load(f)
    if not isinstance(data, list):
        raise ValueError(f"YAML must be a list of segment dicts: {path}")
    return data


def parse_segments_from_args(raw: list[list[str]]) -> list[dict]:
    segments = []
    for group in raw:
        if len(group) != 4:
            sys.exit(f"--segment requires exactly 4 values: START END ENERGY TAGS, got: {group}")
        start_s, end_s, energy, tags_s = group
        segments.append({
            "start": start_s,
            "end": end_s,
            "energy": energy,
            "tags": [t.strip() for t in tags_s.split(",") if t.strip()],
        })
    return segments


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Slice segments from a long video and register in brainrot library."
    )
    parser.add_argument("video", help="Source video file path")
    parser.add_argument(
        "--segment",
        nargs=4,
        metavar=("START", "END", "ENERGY", "TAGS"),
        action="append",
        dest="segments",
        help="Define a segment (repeatable). TAGS is comma-separated.",
    )
    parser.add_argument("--from-yaml", metavar="FILE", help="Load segments from YAML file")
    parser.add_argument("--dry-run", action="store_true", help="Print plan, don't write files")
    parser.add_argument(
        "--output-name",
        metavar="PREFIX",
        help="Prefix for output filenames (default: source stem)",
    )
    args = parser.parse_args()

    if not args.segments and not args.from_yaml:
        parser.error("Provide at least one --segment or --from-yaml")

    source = Path(args.video).expanduser().resolve()
    if not source.exists():
        sys.exit(f"Source video not found: {source}")

    if args.from_yaml:
        raw_segments = load_segments_from_yaml(args.from_yaml)
    else:
        raw_segments = parse_segments_from_args(args.segments)

    # Validate and normalise each segment
    from sable.clip.brainrot import ENERGY_LEVELS
    from sable.shared.paths import brainrot_dir

    dest_dir = brainrot_dir()
    stem = args.output_name or source.stem

    segments = []
    for seg in raw_segments:
        energy = seg.get("energy", "medium")
        if energy not in ENERGY_LEVELS:
            sys.exit(f"Invalid energy {energy!r}. Must be one of {ENERGY_LEVELS}")
        tags = seg.get("tags", [])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]
        segments.append({
            "start": parse_time(str(seg["start"])),
            "end": parse_time(str(seg["end"])),
            "energy": energy,
            "tags": tags,
        })

    # Print plan
    print(f"Source : {source}")
    print(f"Output : {dest_dir}")
    print(f"Stem   : {stem}")
    print(f"Segments ({len(segments)}):")
    for i, seg in enumerate(segments, 1):
        duration = seg["end"] - seg["start"]
        out_path = resolve_output_name(dest_dir, stem, i)
        print(
            f"  [{i:02d}] {seg['start']:.1f}s → {seg['end']:.1f}s  "
            f"({duration:.1f}s)  energy={seg['energy']}  "
            f"tags={seg['tags']}  → {out_path.name}"
        )

    if args.dry_run:
        print("\n[dry-run] No files written.")
        return

    from sable.shared.ffmpeg import extract_clip
    from sable.clip.brainrot import add_video

    for i, seg in enumerate(segments, 1):
        out_path = resolve_output_name(dest_dir, stem, i)
        print(f"\n[{i}/{len(segments)}] Extracting {out_path.name} ...")
        extract_clip(source, out_path, seg["start"], seg["end"])
        entry = add_video(out_path, energy=seg["energy"], tags=seg["tags"], copy=False)
        print(f"  Registered: duration={entry['duration']}s  energy={entry['energy']}  tags={entry['tags']}")

    print(f"\nDone. {len(segments)} clip(s) added to brainrot library.")


if __name__ == "__main__":
    main()
