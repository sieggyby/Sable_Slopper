# TODO

---

## Validation Snapshot

- `./.venv/bin/python -m pytest -q` → `899 passed`
- `./.venv/bin/ruff check .` → 0
- `./.venv/bin/mypy sable` → 0

---

## Open Items

### Brainrot theme matching

Clip pipeline improvement: match brainrot overlay content to clip topic/vibe.
Currently brainrot is selected by duration + energy only.

**Status:** Proposed, not started. Low priority.

### SocialData known gaps (non-blocking)

From the 2026-04-02 hardening pass. These are improvement opportunities, not bugs:
- No per-phase cost breakdown in `pulse meta` scan reports
- No cost tracking in `tracker.py` / `trends.py` / `suggest.py` (these read SocialData, not Claude)
- No cursor cycling for accounts with >3200 tweets
- No checkpoint/resume for interrupted scans

---

## Phase 2+ (Deferred)

### Phase 2 remaining

- Cloudflare Tunnel deployment (belongs to SableWeb's deployment story)
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
