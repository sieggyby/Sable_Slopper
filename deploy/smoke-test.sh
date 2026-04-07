#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
# Sable VPS Smoke Test
#
# Run after setup-vps.sh to verify the deployment is healthy.
# Usage:  sudo -u sable bash /opt/sable/repo/deploy/smoke-test.sh
# ──────────────────────────────────────────────────────────────
set -uo pipefail

SABLE_BIN="/opt/sable/venv/bin/sable"
DATA_DIR="/opt/sable/data"
HEALTH_URL="http://localhost:8420/health"
PASS=0
FAIL=0

check() {
    local label="$1"
    shift
    if "$@" &>/dev/null; then
        echo "  PASS  $label"
        ((PASS++))
    else
        echo "  FAIL  $label"
        ((FAIL++))
    fi
}

echo "=== Sable Smoke Test ==="
echo

# 1. CLI
check "sable --version" "$SABLE_BIN" --version

# 2. Health endpoint (sable serve must be running)
check "sable serve /health" curl -sf "$HEALTH_URL"

# 3. SQLite databases exist and are readable
for db in "$DATA_DIR/sable.db" "$DATA_DIR/pulse/pulse.db" "$DATA_DIR/pulse/meta.db"; do
    check "DB readable: $(basename "$db")" test -r "$db"
done

# 4. ffmpeg
check "ffmpeg available" ffmpeg -version

# 5. yt-dlp
check "yt-dlp available" /opt/sable/venv/bin/yt-dlp --version

echo
echo "── Results: $PASS passed, $FAIL failed ──"

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
