# TODO

## Platform Layer — Upcoming Rounds

### Round 2 — Cult Doctor (community health grader)
- Read `sable.db` entities/tags per org to produce health scores
- Write `diagnostic_runs` rows + `artifacts` (playbook, strategy brief)
- Gate all Claude calls through `check_budget()` + model ladder
- CLI: `sable cult-doctor run <org_id>`

### Round 3 — SableTracking integration
- Bridge SableTracking Discord data → `sable.db` entities + handles
- Write `sync_runs` rows per ingest
- Trigger `mark_artifacts_stale()` on new data arrival
- CLI: `sable tracking sync <org_id>`

---

## Vault — Non-MVP Features (Phase 2+)

Extracted from vault spec. Not implemented in Phase 1 CLI.

- **Phase 2 — Web UI (`sable serve`)**
  - FastAPI app in `sable/serve/app.py` wrapping all vault functions
  - Cloudflare Tunnel for team/client access
  - Role-based access control via `sable/vault/permissions.py` (currently stub)
  - Token auth middleware + `~/.sable/vault_users.yaml` user store
  - Web views: dashboard, content browser, search, reply suggest, posting log
  - See `docs/ROLES.md` for permission matrix, `docs/ROADMAP.md` for architecture

- **Phase 3 — VPS**
  - Docker + systemd, Postgres backend, multi-org S3 vault storage
  - Webhook receivers for pulse data push + tweet notifications
  - Scheduled sync via cron

- **Phase 4 — Scale**
  - Multi-tenant auth, vault-as-API, real-time enrichment queue (Celery/Redis)
  - Automated gap-fill suggestions triggered by pulse performance data
  - Client portal with read-only dashboard + export access
