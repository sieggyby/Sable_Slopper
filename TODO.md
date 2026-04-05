# TODO

---

## Validation Snapshot

- `./.venv/bin/python -m pytest -q` → `1046 passed`
- `./.venv/bin/ruff check .` → 0
- `./.venv/bin/mypy sable` → 0

---

## Open Items

### SS-2: Expose `sable serve` for SableWeb [M]

**Current:** `sable serve` (FastAPI, 7 endpoints + /health, bearer token auth) is production-ready. Quick tunnel validated 2026-04-04 via `cloudflared tunnel --url http://localhost:8420`. Remaining: stable production URL.

**Plan (phased):**

1. **Dev/testing (free, no domain) — VALIDATED:** `cloudflared tunnel --url http://localhost:8420` gives a temporary `https://xxxx.trycloudflare.com` URL. Good enough to validate the SableWeb → Slopper wiring end-to-end. URL changes on every restart — not for production.

2. **Production (free Cloudflare account + ~$10/yr domain):** Register a cheap domain via Cloudflare Registrar, create a named tunnel (`cloudflared tunnel create sable-serve`), point a subdomain (e.g., `slopper.yourdomain.com`) at `localhost:8420`. Stable URL, HTTPS, free tier covers everything. Existing bearer token auth (`serve.tokens.sableweb`) provides service-to-service security.

3. **Hosting:** Runs on local Mac for now. `sable serve` must be running + `cloudflared tunnel run` must be running. For persistence: `cloudflared service install` registers a launchd service. Move to VPS in Phase 3.

**Prerequisites:** `brew install cloudflared` (done), free Cloudflare account. Domain purchase only needed for step 2.

**Consumer:** SableWeb content_performance, format_analysis, topic_trends, content_pipeline, vault sections. SableWeb itself deploys to Vercel free tier — see SableWeb TODO § SW-DEPLOY.

**Coordinates with:** SableWeb SW-SLOPPER (wiring the fetch layer) and SW-DEPLOY (Vercel deployment).

---

## Phase 2+ (Deferred)

### Phase 2 remaining

- `sable/vault/permissions.py` — RBAC implementation (currently a stub; see `docs/ROLES.md`)

### Phase 3 — VPS

- Docker + systemd, Postgres backend, multi-org S3 vault storage
- Webhook receivers for pulse data push + tweet notifications
- Scheduled sync via cron

### Phase 4 — Scale

- Multi-tenant auth, vault-as-API, real-time enrichment queue (Celery/Redis)
- Automated gap-fill suggestions triggered by pulse performance data
- Client portal with read-only dashboard + export access

---

## Convention Notes for Future Feature Work

### Command registration

- Top-level commands in `sable/cli.py`; nested subcommands in owning group file
- Handle-scoped commands call `require_account()` first; default `--org` from roster
- `build_account_context()` takes an `Account` object, not a bare handle string

### DB schema awareness

- `pulse.db` uses `posts.id` and `snapshots.id` (not `post_id`/`snapshot_id`)
- `posts.sable_content_type` is a coarse hint, not a format taxonomy — map to
  pulse-meta format buckets explicitly
- `meta.db.format_baselines` stores baseline aggregates only (no `current_lift`,
  `status`, `momentum`, `confidence_grade`)
- `meta.db.scan_checkpoints` stores per-author completion state for resume support
- `load_all_notes()` returns frontmatter dicts with `_note_path`; scans
  `vault/content/**/*.md` only
- Vault note lifecycle: `posted_by` and `suggested_for` — no `status='posted'` field
- Content note freshness: `assembled_at` (no `created_at` on synced content notes)
- Config access: `sable.config.get(...)` / `require_key(...)` (no `get_config()`)
- `search_vault(query, vault_path, org, filters=SearchFilters(...), config=...)`

### Shared patterns

- Claude calls via `call_claude()` / `call_claude_json()` from `sable/shared/api.py`
- All Claude calls pass `org_id` + `call_type` for cost observability; content
  generators use `budget_check=False` (log cost, skip budget gate)
- SocialData costs logged to `sable.db cost_events` with `model="socialdata"` and
  call_type `socialdata_meta_scan` or `socialdata_pulse_track`
- Brainrot `pick()` supports `tags` param for theme matching; falls back to untagged
  if no theme match found. Theme tags are extracted by Claude in clip selector.
- File writes via `atomic_write()` from `sable/shared/files.py`
- All `except Exception` blocks must `logger.warning(...)` — no silent swallows
- New modules follow: `__init__.py`, main logic file, CLI command, tests in `tests/{module}/`
- `meta.db` table definitions go in `sable/pulse/meta/db.py`'s `_SCHEMA` string (not
  migration files), even when a different module owns the read/write logic. The owning
  module imports `meta_db_path()` and connects directly.

### Validation checklist

```bash
./.venv/bin/python -m pytest -q
./.venv/bin/ruff check .
./.venv/bin/mypy sable
```

---

## Completed Work Reference

All completed features, audit remediation, and hardening passes are documented in:
- `docs/AUDIT_HISTORY.md` — Chronological audit and QA record
- `docs/IMPLEMENTATION_LOG.md` — Dated feature delivery records
