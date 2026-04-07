#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
# Sable VPS Setup — Hetzner (Debian/Ubuntu)
#
# Run as root on a fresh CX22 (2 vCPU, 4 GB RAM, €4.5/mo).
# Sets up: sable user, Python venv, systemd services,
#          cloudflared tunnel, and optionally Postgres.
#
# Usage:
#   scp -r deploy/ root@YOUR_VPS_IP:/tmp/sable-deploy/
#   ssh root@YOUR_VPS_IP
#   bash /tmp/sable-deploy/setup-vps.sh
# ──────────────────────────────────────────────────────────────
set -euo pipefail

SABLE_USER="sable"
SABLE_HOME="/opt/sable"
REPO_URL="https://github.com/sieggyby/Sable_Slopper.git"
PYTHON_VERSION="3.12"

echo "=== 1/8: System packages ==="
apt-get update -qq
apt-get install -y -qq \
    python${PYTHON_VERSION} python${PYTHON_VERSION}-venv python${PYTHON_VERSION}-dev \
    git ffmpeg curl gnupg2 lsb-release

echo "=== 2/8: Create sable user ==="
if ! id "$SABLE_USER" &>/dev/null; then
    useradd --system --create-home --home-dir "$SABLE_HOME" --shell /bin/bash "$SABLE_USER"
fi

echo "=== 3/8: Clone repo + venv ==="
sudo -u "$SABLE_USER" bash -c "
set -euo pipefail
cd /opt/sable

# Clone or update
if [ -d repo ]; then
    cd repo && git pull --ff-only
else
    git clone ${REPO_URL} repo
    cd repo
fi

# Python venv
python3.12 -m venv /opt/sable/venv
/opt/sable/venv/bin/pip install --upgrade pip wheel
/opt/sable/venv/bin/pip install -e '/opt/sable/repo[serve]'
/opt/sable/venv/bin/pip install yt-dlp

# Create data dirs
mkdir -p /opt/sable/data /opt/sable/data/pulse /opt/sable/workspace /opt/sable/vault /opt/sable/data/logs
"

echo "=== 4/8: Environment file ==="
if [ ! -f "$SABLE_HOME/.env" ]; then
    cp /tmp/sable-deploy/.env.example "$SABLE_HOME/.env"
    chown "$SABLE_USER:$SABLE_USER" "$SABLE_HOME/.env"
    chmod 600 "$SABLE_HOME/.env"
    echo "  → Fill in API keys: nano $SABLE_HOME/.env"
fi

echo "=== 5/8: Install systemd units ==="
cp /tmp/sable-deploy/sable-serve.service /etc/systemd/system/
cp /tmp/sable-deploy/sable-weekly.service /etc/systemd/system/
cp /tmp/sable-deploy/sable-weekly.timer /etc/systemd/system/
systemctl daemon-reload

echo "=== 6/9: Log rotation ==="
mkdir -p /var/log/sable
chown "$SABLE_USER:$SABLE_USER" /var/log/sable
if [ -f /tmp/sable-deploy/logrotate.d/sable-serve ]; then
    cp /tmp/sable-deploy/logrotate.d/sable-serve /etc/logrotate.d/sable-serve
fi

echo "=== 7/9: Install cloudflared ==="
if ! command -v cloudflared &>/dev/null; then
    curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | gpg --dearmor -o /usr/share/keyrings/cloudflare-main.gpg
    echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared $(lsb_release -cs) main" \
        > /etc/apt/sources.list.d/cloudflared.list
    apt-get update -qq
    apt-get install -y -qq cloudflared
fi

echo "=== 8/9: Install Postgres (optional — skip if not ready) ==="
if ! command -v psql &>/dev/null; then
    apt-get install -y -qq postgresql postgresql-contrib
    systemctl enable --now postgresql

    # Create sable DB + user
    sudo -u postgres psql -c "CREATE USER sable WITH PASSWORD 'changeme';" 2>/dev/null || true
    sudo -u postgres psql -c "CREATE DATABASE sable OWNER sable;" 2>/dev/null || true
    sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE sable TO sable;" 2>/dev/null || true
    echo "  → Postgres ready. Change the password: sudo -u postgres psql -c \"ALTER USER sable PASSWORD 'your-real-password';\""
    echo "  → Then set SABLE_DB_URL in $SABLE_HOME/.env"
fi

echo "=== 9/9: Summary ==="
cat <<SUMMARY

  ┌───────────────────────────────────────────────────────┐
  │  Sable VPS Setup Complete                             │
  ├───────────────────────────────────────────────────────┤
  │                                                       │
  │  1. Fill in API keys:                                 │
  │     nano /opt/sable/.env                              │
  │                                                       │
  │  2. Copy data from Mac:                               │
  │     See deploy/DEPLOY.md § "Migrate data"             │
  │                                                       │
  │  3. Copy config.yaml:                                 │
  │     scp ~/.sable/config.yaml                          │
  │         sable@VPS:/opt/sable/data/config.yaml         │
  │                                                       │
  │  4. Set up Cloudflare tunnel:                         │
  │     cloudflared tunnel login                          │
  │     cloudflared tunnel create sable-serve             │
  │     # Then configure DNS — see DEPLOY.md              │
  │                                                       │
  │  5. Start services:                                   │
  │     systemctl enable --now sable-serve                │
  │     systemctl enable --now sable-weekly.timer         │
  │                                                       │
  │  6. Verify:                                           │
  │     curl http://localhost:8420/health                  │
  │     journalctl -u sable-serve -f                      │
  │                                                       │
  └───────────────────────────────────────────────────────┘

SUMMARY
