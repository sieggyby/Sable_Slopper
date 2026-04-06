# TODO

---

## Validation Snapshot (2026-04-06)

- `./.venv/bin/python -m pytest -q` → `1213 passed`
- `./.venv/bin/ruff check .` → 0
- `./.venv/bin/mypy sable` → 0

---

## Full Repo Audit (2026-04-05) — COMPLETED

All 19 unblocked items (T1-1 through T3-10) implemented, QA-gated, and closed.
See `docs/AUDIT_HISTORY.md` § "Full Repo Audit Remediation" for details.

### Resolved Items (T1-1 through T3-10)

All 19 items below were implemented, QA-gated, and closed 2026-04-05.
Full details in `docs/AUDIT_HISTORY.md` § "Full Repo Audit Remediation."

**Tier 1 (Critical/High):**
- ~~T1-1: Replicate API key env leak — `replicate.Client(api_token=...)` replaces `os.environ` set~~
- ~~T1-2: Strategy brief sample size disclosure — 4 sites patched + stage2 contract rule~~
- ~~T1-3: Account format report confidence grade — `account_confidence` field (A/B/C/D)~~

**Tier 2 (High/Medium):**
- ~~T2-1: pulse/meta/db.py tests — 14 tests in `tests/pulse/meta/test_meta_db.py`~~
- ~~T2-2: pulse/meta/scanner.py tests — 8 tests in `tests/pulse/meta/test_scanner.py`~~
- ~~T2-3: pulse/meta/cli.py tests — 5 tests in `tests/pulse/meta/test_meta_cli.py`~~
- ~~T2-4: ElevenLabs key via `require_key()` — removed `os.environ.get`~~
- ~~T2-5: Vault notes TTL cache — 5-min TTL, invalidation on write~~
- ~~T2-6: face/optimize.py exception logging — 4 sites now log `logger.debug`~~

**Tier 3 (Medium/Low):**
- ~~T3-1: calendar/planner.py tests — 6 tests in `tests/calendar_planner/test_planner.py`~~
- ~~T3-2: shared/ffmpeg.py tests — 6 tests in `tests/shared/test_ffmpeg.py`~~
- ~~T3-3: onboard/orchestrator.py tests — 3 tests in `tests/onboard/test_orchestrator.py`~~
- ~~T3-4: vault/cli.py tests — 3 tests in `tests/vault/test_vault_cli.py`~~
- ~~T3-5: platform/cli.py tests — 3 tests in `tests/platform/test_platform_cli.py`~~
- ~~T3-6: Rate limiter LRU eviction — `min()` by last-request time~~
- ~~T3-7: Global exception handler — `@app.exception_handler(Exception)` on serve~~
- ~~T3-8: Write generator anatomy sample count — `{len(patterns)} posts` in prompt~~
- ~~T3-9: Narrative velocity min sample guard — `unique_authors >= 3`, `days_since >= 2`~~
- ~~T3-10: Lexicon scanner metadata return — `tuple[list[dict], dict]` with corpus stats~~

---

### Codit Audit Remediation (2026-04-05) — COMPLETED

All critical, high, and medium findings from `codit.md` (2026-03-23 audit) resolved:

**Critical (5/5 closed):**
- ~~CRIT-1: vault/platform_sync.py partial-sync window — pulse report staging moved before Phase B renames~~
- ~~CRIT-2: roster/manager.py concurrent writes — fcntl lock + atomic_write~~
- ~~CRIT-3: vault/notes.py non-atomic writes — atomic_write()~~
- ~~CRIT-4: shared/paths.py vault_dir path traversal — org slug regex~~
- ~~CRIT-5: platform/merge.py NoneType crash — SableError guard~~

**High (7/7 closed):**
- ~~HIGH-1: Failed scan rows under-report cost/novelty — Scanner instance attrs~~
- ~~HIGH-2: Claude calls bypass budget/cost — centralized in shared/api.py~~
- ~~HIGH-3: Failed author fetches silently excluded — tracked + reported~~
- ~~HIGH-4: String max() on tweet IDs — integer comparison~~
- ~~HIGH-5: Deep-mode outsider tweets ephemeral — CLI help + console transient marker~~
- ~~HIGH-6: FFmpeg subtitle path injection — _validate_subtitle_path()~~
- ~~HIGH-7: Migration failure partial schema — transactional migrations in SablePlatform~~

**Medium (10 fixed, 2 partial):**
- ~~MED-1: Analysis phase cost guard — max_analysis_cost cap~~
- ~~MED-2: Fallback analysis not marked — degraded frontmatter field~~
- ~~MED-3: Whisper model caching — _MODEL_CACHE~~
- ~~MED-4: Broad exception swallowing — now logs which source failed (partial: still degrades)~~
- ~~MED-5: Claude search fallback silent — SearchResult.degraded flag~~
- ~~MED-6: Corrupted cache rows — stale marking on bad artifacts~~
- ~~MED-7: Clip selector JSON parse — logging + retry~~
- ~~MED-8: Naive UTC datetime — timezone-aware in SablePlatform~~
- ~~MED-9: Lookback string comparison — _parse_twitter_date returns None~~
- ~~MED-10: Format baselines duplicate rows — insert_format_baseline + same-second dedup~~
- ~~MED-11: Entity set no size guard — paginated LIMIT 500 OFFSET~~
- ~~MED-12: Hardcoded pricing — centralized in shared/pricing.py~~

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

### ~~SS-3: Weekly Automation & Operator Streamlining~~ — SHIPPED 2026-04-06

- `sable weekly run --org ORG` — orchestrates pulse track → meta scan → advise → calendar → vault sync
- `sable weekly run --all` — discovers all rostered orgs, runs weekly cycle for each
- `--dry-run` and `--cost-estimate` flags for planning without execution
- `sable weekly cron install` — launchd plist generator (Monday 06:00)
- `sable clip review --org ORG` — interactive triage: approve/skip/delete unreviewed clips
- `GET /api/v1/cost/org/{org_id}/cost-forecast` — cost forecast + budget status endpoint
- 34 new tests (16 runner + 7 CLI + 7 clip review + 4 cost routes)

### ~~SS-2: Expose `sable serve` for SableWeb~~ — SHIPPED 2026-04-06

**Production URL:** `https://api.sable.tools` → `localhost:8420` via Cloudflare named tunnel `sable-serve`.

Both services run as persistent launchd daemons (survive reboots):
- `com.cloudflare.cloudflared` — system daemon, `/Library/LaunchDaemons/`
- `com.sable.serve` — user agent, `~/Library/LaunchAgents/`

**Consumer:** SableWeb content_performance, format_analysis, topic_trends, content_pipeline, vault sections.

---

## Phase 2+ (Deferred)

### Phase 2 remaining

- ~~`sable/vault/permissions.py` — RBAC implementation~~ **SHIPPED 2026-04-05**
- ~~Org-scoping in serve routes — token-to-org binding~~ **SHIPPED 2026-04-05**

> All serve routes now enforce per-token role + org scoping. See `docs/ROLES.md`.

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
