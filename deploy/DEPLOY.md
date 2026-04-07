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
│   ├── pulse.db             ← (kept until Postgres migration)
│   ├── pulse/meta.db        ← (kept until Postgres migration)
│   ├── sable.db             ← (kept until Postgres migration)
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

Postgres runs on the same CX22 — no additional cost. The migration converts `sable.db` (the cross-tool platform store) first, since it's the most valuable for concurrent access and SableWeb queries. `pulse.db` and `meta.db` can follow later or stay SQLite.

### Why Postgres

| Concern | SQLite | Postgres |
|---------|--------|----------|
| Concurrent writes | Single-writer lock (busy_timeout 5s) | MVCC, no lock contention |
| Backup | Online backup API (already implemented) | `pg_dump`, streaming replication |
| Remote access | File must be local | TCP connections from SableWeb/other services |
| Size limit | Practical limit ~10 GB | Effectively unlimited |
| JSON queries | Limited `json_extract` | Full `jsonb` operators, indexes |

At current scale SQLite is fine. Postgres becomes worth it when:
- Multiple services write concurrently (SableWeb mutations, weekly automation, manual CLI)
- You want SableWeb to query the DB directly instead of through the REST API
- You add a second VPS or container

### Phase 1: sable.db → Postgres

This is the only DB that SablePlatform manages with versioned migrations. The other two (pulse.db, meta.db) use `CREATE TABLE IF NOT EXISTS` schemas embedded in Python.

**Step 1: Schema translation**

SablePlatform's 30 migrations are SQLite DDL. Create a Postgres-compatible `init.sql`:

```sql
-- deploy/postgres/init.sql
-- Translated from sable_platform/db/migrations/*.sql

CREATE TABLE IF NOT EXISTS orgs (
    org_id TEXT PRIMARY KEY,
    display_name TEXT,
    discord_server_id TEXT,
    twitter_handle TEXT,
    config_json JSONB,            -- JSONB instead of TEXT
    status TEXT DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS entities (
    entity_id TEXT PRIMARY KEY,
    org_id TEXT REFERENCES orgs(org_id),
    display_name TEXT,
    entity_type TEXT,
    status TEXT DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ... (all 15+ tables from sable.db)
-- Full schema derived from: sable_platform/db/migrations/
```

**Step 2: Code changes (sable_platform)**

The connection factory in `sable_platform/db/connection.py` currently returns a `sqlite3.Connection`. Add a Postgres path:

```python
# sable_platform/db/connection.py — sketch
import os

def get_db():
    db_url = os.environ.get("SABLE_DB_URL")
    if db_url and db_url.startswith("postgresql://"):
        return _get_pg_connection(db_url)
    return _get_sqlite_connection()

def _get_pg_connection(url: str):
    import psycopg2
    import psycopg2.extras
    conn = psycopg2.connect(url)
    conn.autocommit = False
    # Return a wrapper that matches the sqlite3.Row interface
    # or use psycopg2.extras.RealDictCursor
    return conn

def _get_sqlite_connection():
    # ... existing code ...
```

**Key SQL differences to handle:**

| SQLite | Postgres | Where |
|--------|----------|-------|
| `datetime('now')` | `now()` | Defaults, WHERE clauses |
| `datetime('now', '-7 days')` | `now() - interval '7 days'` | Cost queries, freshness |
| `json_extract(col, '$.key')` | `col->>'key'` | config_json queries |
| `INTEGER PRIMARY KEY AUTOINCREMENT` | `SERIAL PRIMARY KEY` | All tables |
| `?` parameter | `%s` parameter | All queries |
| `GROUP_CONCAT` | `string_agg` | A few reports |
| `conn.row_factory = sqlite3.Row` | `RealDictCursor` | Connection setup |

**Approach: dialect adapter**

Rather than rewriting every query, create a thin adapter:

```python
# sable_platform/db/dialect.py
class SQLDialect:
    """Abstract query differences between SQLite and Postgres."""
    def __init__(self, backend: str):  # "sqlite" or "postgres"
        self.backend = backend

    def now(self) -> str:
        return "datetime('now')" if self.backend == "sqlite" else "now()"

    def interval(self, days: int) -> str:
        if self.backend == "sqlite":
            return f"datetime('now', '-{days} days')"
        return f"now() - interval '{days} days'"

    def param(self) -> str:
        return "?" if self.backend == "sqlite" else "%s"

    def json_extract(self, col: str, key: str) -> str:
        if self.backend == "sqlite":
            return f"json_extract({col}, '$.{key}')"
        return f"{col}->>'{key}'"
```

Thread the dialect through query-building functions. Most queries are simple SELECTs/INSERTs that need only the parameter style changed.

**Step 3: Data migration**

```bash
# On the VPS — one-shot SQLite → Postgres dump
pip install pgloader  # or use the apt package

pgloader sqlite:///opt/sable/data/sable.db \
         postgresql://sable:changeme@localhost/sable
```

Or manual:
```bash
# Dump SQLite as SQL inserts
sqlite3 /opt/sable/data/sable.db .dump > /tmp/sable_dump.sql

# Clean up SQLite-isms (BEGIN TRANSACTION, etc.), then:
psql -U sable -d sable -f /tmp/sable_dump.sql
```

**Step 4: Switch over**

```bash
# In /opt/sable/.env, uncomment:
SABLE_DB_URL=postgresql://sable:changeme@localhost:5432/sable

# Restart
systemctl restart sable-serve
curl https://api.sable.tools/health
```

**Step 5: Add psycopg2 to dependencies**

```toml
# pyproject.toml
[project.optional-dependencies]
postgres = ["psycopg2-binary>=2.9"]
serve = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
]
```

Install: `pip install -e ".[serve,postgres]"`

### Phase 2: pulse.db + meta.db → Postgres (later)

These two are harder because:
- Schemas are embedded `_SCHEMA` strings, not migration files
- Each module opens its own `sqlite3.connect()` directly — no shared factory
- `pulse.db` is read-heavy from serve routes; `meta.db` is write-heavy during scans

When you're ready:
1. Create Postgres schemas matching `sable/pulse/db.py:_SCHEMA` and `sable/pulse/meta/db.py:_SCHEMA`
2. Refactor `pulse/db.py` and `pulse/meta/db.py` to use a connection factory that respects `PULSE_DB_URL` / `META_DB_URL` env vars
3. Migrate data with `pgloader`
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

# Postgres stats (after migration)
sudo -u postgres psql -c "SELECT pg_database_size('sable');"
```
