# TODO

---

## Validation Snapshot (2026-04-08)

- `./.venv/bin/python -m pytest -q` → `1117 passed, 96 failed`
- `./.venv/bin/ruff check .` → 0
- `./.venv/bin/mypy sable` → 0

**96 failures are upstream:** SablePlatform's SQLAlchemy Core migration wraps SQL in `text()`, which raises `TypeError: execute() argument 1 must be str, not TextClause` when called against Slopper test fixtures using raw `sqlite3.Connection`. Affected test files: `tests/advise/`, `tests/onboard/`, `tests/org_status/`, `tests/platform/`, `tests/pulse/test_outcomes.py`, `tests/pulse/test_sync_runs.py`. Fix requires updating Slopper test fixtures to use SablePlatform's `CompatConnection` or aligning on raw sqlite3 connections in the shared modules.

---

### Deferred / Blocked (carried forward)

#### AQ-31: Add clip/thumbnail tests [MEDIUM priority, HIGH effort]
- **Module:** `sable/clip/thumbnail.py` — 581 LOC, highest complexity score in codebase, zero tests.
- **Tests needed:**
  - Mock ffmpeg frame extraction → verify candidate frame selection
  - Mock face_recognition → verify face crop with bbox expansion
  - No faces found → fallback to contrast scoring
- **File:** `tests/clip/test_thumbnail.py`
- **Deferred:** Requires mocking Playwright + face_recognition; high effort relative to risk.

#### AQ-33: Add migration for diagnostic_runs language columns [LOW priority, BLOCKED]
- **Context:** `sable/advise/stage1.py:467-472` queries `language_arc_phase`, `emergent_cultural_terms_json`, `mantra_candidates_json` from `diagnostic_runs`. No migration adds them. Code has defensive `except` that logs debug and returns "".
- **Status:** BENIGN (code is defensive). Blocked on `--community-voice` feature stabilization.
- **Fix (when ready):** Add migration 023 to SablePlatform adding the 3 TEXT columns to `diagnostic_runs`.

---

## Open Items

### SS-COMPAT: Fix 96 test failures from SablePlatform SQLAlchemy migration [HIGH priority, BLOCKED]

- **Root cause:** SablePlatform Phases 0–7 converted `sable/platform/` modules to use `text()` wrapped SQL via SQLAlchemy Core. Slopper test fixtures still pass raw `sqlite3.Connection` objects, which choke on `TextClause` arguments.
- **Affected:** `tests/advise/`, `tests/onboard/`, `tests/org_status/`, `tests/platform/`, `tests/pulse/test_outcomes.py`, `tests/pulse/test_sync_runs.py` (96 tests total)
- **Fix options:** (a) Update Slopper test fixtures to use SablePlatform's `CompatConnection`, or (b) have SablePlatform modules detect raw sqlite3 connections and unwrap `text()`.
- **Blocked on:** Decision on which side owns the fix (Slopper fixtures vs SablePlatform compat layer).

---

## Phase 3+ (Deferred)

### Phase 3 — VPS (partially complete)

- Postgres migration for `sable.db` — **Upstream ready (2026-04-08).** SablePlatform Phases 0–7 complete: SQLAlchemy Core + Alembic + `SABLE_DATABASE_URL` support. Slopper's `sable/platform/` re-export facades work unchanged through CompatConnection. To activate: set `SABLE_DATABASE_URL=postgresql://...` on VPS, run `alembic upgrade head` in SablePlatform, migrate data.
- Postgres migration for `pulse.db` / `meta.db` — separate concern (Slopper's own databases, not SablePlatform). Dialect adapter needed. See `deploy/DEPLOY.md`.
- Docker container (deferred — systemd is sufficient at current scale)
- Multi-org S3 vault storage (deferred)
- Webhook receivers for pulse data push + tweet notifications

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
  call_type `socialdata_meta_scan`, `socialdata_pulse_track`, or `socialdata_suggest`
- Brainrot `pick()` supports `tags` param for theme matching; falls back to untagged
  if no theme match found. Theme tags are extracted by Claude in clip selector.
- File writes via `atomic_write()` from `sable/shared/files.py`
- All `except Exception` blocks must `logger.warning(...)` — no silent swallows
- Scanner uses `bulk_upsert_tweets()` + checkpoint in a single transaction for atomicity
- Anthropic pricing centralized in `sable/shared/pricing.py` — do not hardcode rates elsewhere
- `meta.db.format_baselines` is a history table — use `insert_format_baseline()`, not upsert.
  Same-second dedup prevents retry bloat. Use `prune_format_baselines()` for retention.
- `vault/search.py SearchResult.degraded` signals keyword-fallback results to callers
- Vault sync uses two-phase writes: all temp files staged in Phase A, all renames in Phase B.
  `_cleanup_temps()` handles rollback. `_PARTIAL_SYNC` sentinel flags post-rename DB failures.
- Org slugs validated by `_ORG_SLUG` regex in `shared/paths.py` — no path traversal via org IDs
- FFmpeg subtitle paths validated by `_validate_subtitle_path()` — rejects `;:[]= ` chars
- New modules follow: `__init__.py`, main logic file, CLI command, tests in `tests/{module}/`
- `meta.db` table definitions go in `sable/pulse/meta/db.py`'s `_SCHEMA` string (not
  migration files), even when a different module owns the read/write logic. The owning
  module imports `meta_db_path()` and connects directly.
- `sable.db` queries via `get_db()` use `:named` params with dict args (not `?` with tuples).
  `pulse.db` and `meta.db` queries via direct `sqlite3.connect()` still use `?`-positional.

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
