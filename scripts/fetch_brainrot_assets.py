"""Download OBrainRot gameplay videos into the Sable brainrot library."""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

# Ensure project is on path when run directly
sys.path.insert(0, str(Path(__file__).parent.parent))

from sable.shared.paths import brainrot_dir
from sable.clip.brainrot import add_video

ASSETS = [
    {
        "url": "https://github.com/harvestingmoon/OBrainRot/raw/master/assets/subway.mp4",
        "filename": "subway.mp4",
        "energy": "medium",
        "tags": ["subway", "gameplay"],
    },
    {
        "url": "https://github.com/harvestingmoon/OBrainRot/raw/master/assets/parkour_test.mp4",
        "filename": "parkour.mp4",
        "energy": "high",
        "tags": ["parkour", "gameplay"],
    },
]


def fetch(url: str, dest: Path) -> None:
    print(f"  Downloading {dest.name}...")
    urllib.request.urlretrieve(url, dest)
    size_mb = dest.stat().st_size / 1_048_576
    print(f"  {dest.name}: {size_mb:.1f} MB")


def main() -> None:
    lib = brainrot_dir()
    lib.mkdir(parents=True, exist_ok=True)

    for asset in ASSETS:
        dest = lib / asset["filename"]
        if dest.exists():
            print(f"  Skipping {asset['filename']} (already exists)")
        else:
            fetch(asset["url"], dest)

        print(f"  Registering {asset['filename']} (energy={asset['energy']})...")
        entry = add_video(dest, energy=asset["energy"], tags=asset["tags"], copy=False)
        print(f"  ✓ {entry['filename']}  {entry['duration']:.1f}s  {entry['energy']}")

    print("\nDone. Run 'sable clip brainrot list' to verify.")


if __name__ == "__main__":
    main()
