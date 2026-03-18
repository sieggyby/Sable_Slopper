#!/usr/bin/env bash
# setup_brainrot.sh — helper script for setting up brainrot video library
# Usage: bash scripts/setup_brainrot.sh [directory_of_videos]

set -e

SABLE_HOME="${SABLE_HOME:-$HOME/.sable}"
BRAINROT_DIR="$SABLE_HOME/brainrot"

mkdir -p "$BRAINROT_DIR"

echo "Brainrot library directory: $BRAINROT_DIR"
echo ""

if [ -n "$1" ] && [ -d "$1" ]; then
    VIDEO_DIR="$1"
    echo "Scanning $VIDEO_DIR for video files..."
    count=0
    for f in "$VIDEO_DIR"/*.{mp4,mov,avi,webm,mkv} 2>/dev/null; do
        [ -f "$f" ] || continue
        echo "  Adding: $(basename "$f")"
        sable clip brainrot add "$f" --energy medium --no-copy
        count=$((count + 1))
    done
    echo ""
    echo "Added $count videos to brainrot library."
else
    echo "Usage: bash scripts/setup_brainrot.sh <directory>"
    echo ""
    echo "Or add videos manually:"
    echo "  sable clip brainrot add <video.mp4> --energy low|medium|high"
    echo ""
    echo "Recommended brainrot sources:"
    echo "  - Subway Surfers gameplay (medium energy)"
    echo "  - Minecraft parkour (medium energy)"
    echo "  - Satisfying sand cutting (low energy)"
    echo "  - POV driving / FPV (high energy)"
fi

echo ""
echo "Current library:"
sable clip brainrot list 2>/dev/null || echo "  (install sable first: pip install -e .)"
