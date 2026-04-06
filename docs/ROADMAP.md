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
- `sable weekly` — automated weekly cycle: pulse track → meta scan → advise → calendar → vault sync. `--all`, `--dry-run`, `--cost-estimate` flags. `sable weekly cron install` for launchd scheduling (Monday 06:00).
- `sable clip review` — interactive clip triage queue: approve/skip/delete unreviewed clips, auto vault sync after approvals.

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

**Status: Complete** — `sable serve` + all Phase 2 CLI and hardening features shipped (SS-1 through SS-21, 1213 tests). Production URL live at `https://api.sable.tools` via Cloudflare named tunnel. RBAC shipped with 3 roles (admin/creator/operator). Cost forecast endpoint added 2026-04-06.

**Target: Expose vault and pulse data to SableWeb's `/ops` surface via a read API**

SableWeb (Next.js, separate repo) is the single web UI for both operators and clients. Slopper Phase 2 does not produce its own frontend — it produces a FastAPI backend that SableWeb calls. This avoids two auth systems, two deployment models, and duplicated reads from the same databases.

**What `sable serve` provides:**
- `sable/serve/app.py` — FastAPI app factory
- `sable/serve/routes/vault.py` — vault inventory, content browser, search, assign
- `sable/serve/routes/pulse.py` — posting log, pulse snapshots, format performance
- `sable/serve/routes/meta.py` — topic signals, watchlist, format baselines
- `sable/serve/auth.py` — named token auth with audit trail (SS-17); SableWeb authenticates users, this layer validates service-to-service tokens
- `sable/serve/rate_limit.py` — sliding-window rate limiter, 60 RPM default (SS-15)
- `sable/vault/permissions.py` — role check implementation (currently stub; roles defined in `docs/ROLES.md`)

**What moves to SableWeb `/ops` (not built here):**
- Content browser — vault inventory per client: produced, posted, unused
- Search — frontmatter filter + Claude ranking results displayed in portal
- Posting log — Sable vs. organic attribution, format performance vs. niche baselines
- Stale/unused asset flags

**What stays CLI-only for now:**
- `sable vault suggest` — reply suggestion is generative/interactive; does not fit a read-only portal. Revisit when SableWeb becomes action-capable.
- `sable vault assign`, `sable vault gaps`, `sable vault export` — operator workflows that are fast enough in CLI

**Additional Phase 2 CLI features (delivered alongside `sable serve`):**
- `sable pulse outcomes --org --handle` — content performance outcomes: groups posts by `sable_content_type`, computes engagement rates, writes to `sable.db outcomes` table with delta tracking (P2-4)
- Content artifact registration — `sable/platform/artifacts.py` writes clip and meme production artifacts to `sable.db artifacts` for stale detection and SableWeb content library (P2-6)
- Cost logging decoupled from budget gating — `budget_check=False` parameter on `call_claude_with_usage()` lets write/score/clip log costs without triggering budget hard gates (P1-2)
- Pulse freshness sync to `sync_runs` — pulse track/meta/recommend record sync metadata for SableWeb freshness display (P1-3)

**Deployment:** Hetzner CX21 VPS (178.156.204.125) deployed 2026-04-06. `sable-serve.service` + `cloudflared.service` + `sable-weekly.timer` running as systemd units. `api.sable.tools` via Cloudflare named tunnel. Previous Mac launchd services decommissioned. See `deploy/DEPLOY.md` for full setup and Postgres transition plan.

---

## Phase 3 — VPS Deployment

**Status: Partially complete** — Hetzner CX21 deployed 2026-04-06. Postgres installed, awaiting migration.

**Completed:**
- Hetzner CX21 VPS (178.156.204.125, €4.51/mo)
- systemd services: `sable-serve.service`, `sable-weekly.timer`, `cloudflared.service`
- Data migrated from Mac (3 SQLite DBs, config, roster, profiles, vault)
- Cloudflare tunnel moved from Mac to VPS
- Postgres installed on same box (no additional cost)

**Remaining:**
- `sable.db` → Postgres migration (dialect adapter in `sable_platform/db/`, data migration via `pgloader`). See `deploy/DEPLOY.md` § Postgres Transition.
- `pulse.db` + `meta.db` → Postgres (lower priority — embedded schemas, serve is read-only)
- Docker container (deferred — systemd sufficient at current scale)
- Multi-org vault storage (S3 or NFS)
- Webhook receivers: pulse data push, tweet notification triggers
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
