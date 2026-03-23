# Sable Vault — Phased Roadmap

## Phase 1 — CLI (Current)

**Status: Complete**

- `sable vault init` — vault directory creation, seed topics + voice profiles
- `sable vault sync` — scan `*_meta.json` / `*.meta.json`, create/update content notes
- `sable vault search` — frontmatter filter + Claude ranking
- `sable vault suggest` — reply suggestion engine with draft generation
- `sable vault log` — posting log + pulse DB sync
- `sable vault assign` — content → account queue, tweet_bank integration
- `sable vault gaps` — coverage gap analysis per topic
- `sable vault export` — client handoff zip
- `sable vault status` — vault inventory dashboard
- `sable vault topic` — topic hub CRUD
- `sable pulse meta` — content shape intelligence: format trend analysis, topic signals, watchlist management, Claude recommendations (see `docs/PULSE_META.md`)
- `sable platform` layer — `sable.db` with 15-table schema, `sable/platform/` helpers, migration runner, 5 new CLI commands (`sable org`, `sable entity`, `sable job`, `sable db`, `sable resume`), 54 tests

**Storage:** Local filesystem, Obsidian-compatible markdown vault at `~/sable-vault/`

---

## Platform Rounds (cross-tool integrations writing to sable.db)

### Round 2 — Cult Doctor ✅ COMPLETE (2026-03-23)
Implemented in Sable_Cult_Grader (not in this repo directly):
- `platform_sync.py`: post-run entity graph sync → sable.db (cultist candidates, bridge nodes, team members, diagnostic_runs, artifacts, sync_runs)
- `playbook/`: two-stage Discord engagement playbook generator ($0.15 cap, weekly cache, budget degradation)
- `bot/`: operator Discord bot with 6 slash commands (`/entity search`, `/merge`, `/run status`, `/playbook latest`)
- `sable_org` field on ProspectConfig: gates sync
- DB migrations 002+003: extended `sync_runs` + `diagnostic_runs` schemas
- Schema version: 3
- Tests: 50 passing (`pytest tests/` in Sable_Cult_Grader)

### Round 3 — SableTracking
Bridges Discord community data into sable.db entity/handle records. Writes sync_runs.
Marks dependent artifacts stale on new data arrival.

---

## Phase 2 — Local Web UI

**Target: Team + client access without CLI**

- `sable serve` — FastAPI server (`sable/serve/`) wrapping the same vault functions
- Cloudflare Tunnel for external access
- Role-based access control (see `docs/ROLES.md`)
- Roles: admin, creator, operator
- Web views: dashboard, content browser, search, reply suggest, posting log
- Auth: simple token-based (no OAuth in Phase 2)
- Local SQLite session store

**New files:**
- `sable/serve/app.py` — FastAPI app factory
- `sable/serve/routes/` — route modules per feature
- `sable/serve/auth.py` — token auth middleware
- `sable/vault/permissions.py` — role check implementation (currently stub)

---

## Phase 3 — VPS Deployment

**Target: Multi-client, always-on**

- Docker container + systemd service
- Postgres backend (replace local SQLite for pulse + vault index)
- Multi-org vault storage (S3 or NFS)
- Webhook receivers: pulse data push, tweet notification triggers
- Scheduled sync: cron-triggered `vault sync` per org
- Email/Slack notifications for gap alerts

---

## Phase 4 — Scale

**Target: Multiple clients, self-serve onboarding**

- Multi-tenant auth (per-client API keys)
- Vault-as-a-service API for external integrations
- Real-time enrichment queue (Celery/Redis)
- Analytics: vault utilization, content effectiveness scoring
- Automated gap-fill suggestions triggered by pulse performance data
- Client portal: read-only dashboard with export access
