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
- Schema version: 5
- Tests: 50 passing (`pytest tests/` in Sable_Cult_Grader)

### Round 3 — SableTracking ✅ COMPLETE (2026-03-23)
Implemented in SableTracking (not in this repo directly):
- `app/platform_sync.py`: async `sync_to_platform(org_id)` → entities, handles, tags, content_items (contributors with `identity_status='matched'` → entities; `top_contributor` tag at 5+ reviewed posts; processed content_log rows → content_items UPSERT)
- `app/platform_sync_runner.py`: local CLI runner (`python -m app.platform_sync_runner tig`)
- `tests/platform_sync/`: 36 unit tests (conftest, contributors, tags, content_items, infrastructure)
- `SABLE_CLIENT_ORG_MAP` env var: JSON string mapping client names → org_ids
- Schema version remains 3

---

## Phase 2 — FastAPI Backend (consumed by SableWeb)

**Target: Expose vault and pulse data to SableWeb's `/ops` surface via a read API**

SableWeb (Next.js, separate repo) is the single web UI for both operators and clients. Slopper Phase 2 does not produce its own frontend — it produces a FastAPI backend that SableWeb calls. This avoids two auth systems, two deployment models, and duplicated reads from the same databases.

**What `sable serve` provides:**
- `sable/serve/app.py` — FastAPI app factory
- `sable/serve/routes/vault.py` — vault inventory, content browser, search, assign
- `sable/serve/routes/pulse.py` — posting log, pulse snapshots, format performance
- `sable/serve/routes/meta.py` — topic signals, watchlist, format baselines
- `sable/serve/auth.py` — token auth middleware (SableWeb authenticates users; this layer validates service-to-service tokens)
- `sable/vault/permissions.py` — role check implementation (currently stub; roles defined in `docs/ROLES.md`)

**What moves to SableWeb `/ops` (not built here):**
- Content browser — vault inventory per client: produced, posted, unused
- Search — frontmatter filter + Claude ranking results displayed in portal
- Posting log — Sable vs. organic attribution, format performance vs. niche baselines
- Stale/unused asset flags

**What stays CLI-only for now:**
- `sable vault suggest` — reply suggestion is generative/interactive; does not fit a read-only portal. Revisit when SableWeb becomes action-capable.
- `sable vault assign`, `sable vault gaps`, `sable vault export` — operator workflows that are fast enough in CLI

**Deployment:** Cloudflare Tunnel belongs to SableWeb's deployment story, not this repo. `sable serve` runs as a local or Railway service; SableWeb proxies to it.

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
