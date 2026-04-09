# Sable VPS Deployment — Hetzner

Deploy `sable serve` + `sable weekly` to a Hetzner VPS with Cloudflare tunnel and optional Postgres migration.

---

## VPS Sizing

**CX22** (€4.51/mo) is plenty:
- 2 vCPU (Intel), 4 GB RAM, 40 GB NVMe
- Postgres + FastAPI + cloudflared all fit comfortably
- SQLite DBs are <100 MB total; Postgres overhead is ~50 MB RAM idle

No additional cost for Postgres — it runs on the same box.

---

## Quick Start

```bash
# From your Mac
scp -r deploy/ root@YOUR_VPS_IP:/tmp/sable-deploy/
ssh root@YOUR_VPS_IP
bash /tmp/sable-deploy/setup-vps.sh
```

The script installs Python 3.12, ffmpeg, yt-dlp, cloudflared, Postgres, creates the `sable` user, clones the repo, builds a venv, installs systemd units, and configures log rotation.

After the script finishes, follow the printed checklist.

### Smoke Test

After setup and data migration, verify the deployment:

```bash
sudo -u sable bash /opt/sable/repo/deploy/smoke-test.sh
```

Checks: CLI importable, health endpoint, SQLite DBs readable, ffmpeg + yt-dlp available.

---

## File Layout on VPS

```
/opt/sable/
├── repo/                    ← git clone of Sable_Slopper
├── venv/                    ← Python venv (pip install -e repo[serve])
├── .env                     ← API keys (chmod 600, never in git)
├── data/                    ← SABLE_HOME
│   ├── config.yaml          ← serve tokens, rate limit, etc.
│   ├── roster.yaml
│   ├── profiles/
│   ├── pulse.db             ← SQLite (active)
│   ├── pulse/meta.db        ← SQLite (active)
│   ├── sable.db             ← SQLite backup (Postgres is primary since 2026-04-09)
│   ├── brainrot/
│   └── logs/
├── workspace/               ← SABLE_WORKSPACE (output, transcripts)
└── vault/                   ← sable-vault (vault_base_path in config)

/var/log/sable/              ← log rotation target (logrotate.d/sable-serve)
/etc/logrotate.d/sable-serve ← weekly rotation, 4 weeks retained, compressed
```

---

## Migrate Data from Mac

```bash
# On your Mac — one-shot rsync
VPS=root@YOUR_VPS_IP

# SQLite databases
scp ~/.sable/pulse.db              $VPS:/opt/sable/data/
scp ~/.sable/pulse/meta.db         $VPS:/opt/sable/data/pulse/
scp ~/.sable/sable.db              $VPS:/opt/sable/data/

# Config + roster + profiles
scp ~/.sable/config.yaml           $VPS:/opt/sable/data/
scp ~/.sable/roster.yaml           $VPS:/opt/sable/data/
rsync -az ~/.sable/profiles/       $VPS:/opt/sable/data/profiles/

# Vault
rsync -az ~/sable-vault/           $VPS:/opt/sable/vault/

# Workspace (optional — large, only if you need clip output history)
# rsync -az ~/sable-workspace/     $VPS:/opt/sable/workspace/

# Fix ownership
ssh $VPS "chown -R sable:sable /opt/sable/data /opt/sable/vault /opt/sable/workspace"
```

Update `/opt/sable/data/config.yaml` on the VPS:
```yaml
vault_base_path: /opt/sable/vault
```

---

## Cloudflare Tunnel Setup

You already own `api.sable.tools` on Cloudflare. Move the tunnel from your Mac to the VPS:

```bash
# On your Mac — remove old tunnel
launchctl unload ~/Library/LaunchAgents/com.cloudflare.cloudflared.plist 2>/dev/null
# (or: launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/...)

# On the VPS
cloudflared tunnel login          # opens browser, authorize sable.tools domain
cloudflared tunnel create sable-serve
```

Create `/etc/cloudflared/config.yml`:
```yaml
tunnel: <TUNNEL_ID>
credentials-file: /root/.cloudflared/<TUNNEL_ID>.json

ingress:
  - hostname: api.sable.tools
    service: http://127.0.0.1:8420
  - service: http_status:404
```

Point DNS:
```bash
cloudflared tunnel route dns sable-serve api.sable.tools
```

Install as systemd service:
```bash
cloudflared service install
systemctl enable --now cloudflared
```

Verify: `curl https://api.sable.tools/health`

---

## Start Services

```bash
# API server (persistent)
systemctl enable --now sable-serve

# Weekly timer (Monday 06:00 UTC)
systemctl enable --now sable-weekly.timer

# Verify
systemctl status sable-serve
systemctl list-timers sable-weekly.timer
curl http://localhost:8420/health
journalctl -u sable-serve -f
```

---

## Updating

```bash
ssh sable@YOUR_VPS_IP
cd /opt/sable/repo
git pull --ff-only
/opt/sable/venv/bin/pip install -e ".[serve]"

# Restart serve (weekly picks up changes on next run)
sudo systemctl restart sable-serve
```

---

## Postgres Transition

Postgres runs on the same CX22 — no additional cost.

### Why Postgres

| Concern | SQLite | Postgres |
|---------|--------|----------|
| Concurrent writes | Single-writer lock (busy_timeout 5s) | MVCC, no lock contention |
| Backup | Online backup API (already implemented) | `pg_dump`, streaming replication |
| Remote access | File must be local | TCP connections from SableWeb/other services |
| Size limit | Practical limit ~10 GB | Effectively unlimited |
| JSON queries | Limited `json_extract` | Full `jsonb` operators, indexes |

### Phase 1: sable.db → Postgres — COMPLETE (2026-04-09)

All 36 tables migrated. Both `sable-serve` and `sable-weekly` systemd services now use Postgres.

- **Migration tool:** `sable-platform migrate to-postgres` (handles Alembic schema creation, data copy, sequence reset, and validation)
- **SablePlatform location:** `/opt/sable/platform`
- **Connection string:** `SABLE_DATABASE_URL=postgresql://sable:...@127.0.0.1:5432/sable?sslmode=disable` in `/opt/sable/.env`
- **Superuser:** Temporarily granted to `sable` role for migration, then revoked
- **SQLite backup:** Original `sable.db` retained on disk at `/opt/sable/data/sable.db`

### Phase 2: pulse.db + meta.db → Postgres (deferred)

These two are harder because:
- Schemas are embedded `_SCHEMA` strings, not migration files
- Each module opens its own `sqlite3.connect()` directly — no shared factory
- `pulse.db` is read-heavy from serve routes; `meta.db` is write-heavy during scans

When you're ready:
1. Create Postgres schemas matching `sable/pulse/db.py:_SCHEMA` and `sable/pulse/meta/db.py:_SCHEMA`
2. Refactor `pulse/db.py` and `pulse/meta/db.py` to use a connection factory that respects `PULSE_DB_URL` / `META_DB_URL` env vars
3. Migrate data (the `sable-platform migrate to-postgres` pattern may be adaptable)
4. All three databases can share one Postgres instance (different schemas or just different table prefixes)

This is lower priority — SQLite handles the pulse/meta read patterns well, and the serve API is read-only.

---

## Cost Summary

| Item | Monthly |
|------|---------|
| Hetzner CX22 | €4.51 |
| Cloudflare tunnel | Free |
| Postgres (same box) | Free |
| Domain (api.sable.tools) | Already owned |
| **Total** | **€4.51/mo** |

---

## Monitoring

```bash
# Serve logs
journalctl -u sable-serve -f

# Weekly run logs
journalctl -u sable-weekly --since "1 hour ago"

# Next weekly run
systemctl list-timers sable-weekly.timer

# Health check (add to uptime monitor)
curl -s https://api.sable.tools/health | jq .

# Disk usage
du -sh /opt/sable/data/ /opt/sable/vault/ /opt/sable/workspace/

# Postgres stats
sudo -u postgres psql -c "SELECT pg_database_size('sable');"
```
