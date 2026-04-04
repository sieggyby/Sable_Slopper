# TODO

---

## Validation Snapshot

- `./.venv/bin/python -m pytest -q` → `921 passed`
- `./.venv/bin/ruff check .` → 0
- `./.venv/bin/mypy sable` → 0

---

## Open Items

### TRACK-METADATA: SableTracking metadata_json schema contract

SableTracking writes 17 fields to `content_items.metadata_json` as an unversioned JSON blob. Slopper reads it in stage1.py via `meta.get("source_tool") == "sable_tracking"` with no schema validation. If SableTracking adds, renames, or removes a field, Slopper breaks silently.

**Upstream plan (SableTracking P7-1):** SablePlatform will publish a `TrackingMetadata(BaseModel)` contract in `sable_platform/contracts/tracking.py` with `schema_version: int`. SableTracking will use it to build metadata_json.

**Slopper action when contract lands:**
1. Import `TrackingMetadata` from `sable_platform.contracts.tracking`
2. In stage1.py where metadata_json is parsed (~line 276), validate against the contract: `TrackingMetadata.model_validate(meta)`
3. Log warning (not error) for unknown `schema_version` — graceful forward compatibility
4. Replace bare `meta.get("key")` calls with typed field access

**Current 17 fields:** source_tool, url, canonical_author_handle, quality_score, audience_annotation, timing_annotation, grok_status, engagement_score, lexicon_adoption, emotional_valence, subsquad_signal, format_type, intent_type, topic_tags, review_status, outcome_type, is_reusable_template.

**Status:** Waiting on SablePlatform to publish the contract. No action until then.

---

## Production Infrastructure (from 2026-04-04 suite audit)

### SS-1: CI/CD pipeline [S]

**File:** New `.github/workflows/ci.yml`

**Change:** GitHub Actions on PR and push to main: `pip install -e ".[dev]"` → `ruff check .` → `mypy sable` → `pytest -q`. Cache pip deps. 921 tests, currently manual-only.

### SS-2: Cloudflare Tunnel deployment for `sable serve` [L]

**Current:** `sable serve` (FastAPI, 7 endpoints + /health, bearer token auth) is production-ready code with no deployment story. This is THE critical blocker for SableWeb content pipeline — content performance, format intelligence, topic signals, and vault inventory sections all return null when `SLOPPER_URL` is not configured.

**Change:** Set up Cloudflare Tunnel to expose `sable serve`. Configure service-to-service token auth at the Cloudflare level (on top of existing bearer token). Document the `SLOPPER_URL` and `SLOPPER_TOKEN` that SableWeb needs.

**Consumer:** SableWeb content_performance, format_analysis, topic_trends, content_pipeline, vault sections.

### SS-3: API contract documentation [S]

**File:** New `docs/API_REFERENCE.md`

**Current:** `sable serve` has 7 endpoints but no documented response shapes. SableWeb needs exact paths, params, and JSON response types to build the fetch layer.

**Change:** Document each endpoint: path, HTTP method, query params, request body (if any), response JSON shape with field types. Include `/health` response shape so SableWeb's health endpoint can verify Slopper availability.

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
