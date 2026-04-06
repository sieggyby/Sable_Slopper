# Implementation Log — Vault Niche-Gaps + Watchlist Win Wire

## Slice 1 — `get_top_topic_signals` (2026-03-26)

Added `get_top_topic_signals(org, limit=20, min_unique_authors=1, conn=None)` to
`sable/pulse/meta/db.py`. Uses `get_conn()` pattern when conn=None. SQL joins
`topic_signals` to the latest successful (non-FAILED) `scan_runs` row. Results sorted
by `avg_lift * acceleration * unique_authors` descending.

Tests: `tests/pulse/meta/test_db_top_signals.py` — 6 tests, all pass.

## Slice 2 — `compute_signal_gaps` + `render_signal_gaps` (2026-03-26)

Added to `sable/vault/gaps.py`:
- `VaultSignalGap` dataclass with term, signal_score, avg_lift, acceleration,
  unique_authors, recommended_type fields.
- `compute_signal_gaps(org, vault_path, meta_db, top_n, min_unique_authors)` — builds
  covered_terms from vault notes (topics, keywords, topic, caption fields), fetches
  top signals, returns uncovered terms sorted by signal_score descending.
- `render_signal_gaps(gaps, org)` — plain-text table with Rich markup for empty state.

Lazy import of `get_top_topic_signals` inside function body to avoid circular imports.
When meta_db=None and no meta.db file exists on disk, returns [] safely.

Tests: `tests/vault/test_gaps_niche.py` — 8 tests, all pass.

## Slice 3 — `vault niche-gaps` CLI (2026-03-26)

Added `vault_niche_gaps` command to `sable/vault/cli.py` after `vault_gaps`. Options:
`--org`, `--vault`, `--top` (default 10), `--min-authors` (default 2), `--json`.

Verified: `sable vault niche-gaps --org psy` runs without error.

## Slice 4 — `watchlist_wire` in generator (2026-03-26)

Added `watchlist_wire: bool = False` parameter to `generate_tweet_variants` in
`sable/write/generator.py`. When True and conn is available, calls
`get_top_topic_signals(resolved_org, limit=3, min_unique_authors=1, conn=conn)` and
injects a "Trending niche topics to consider: ..." line after `vault_block`. Zero
behavior change when False. Errors are swallowed via try/except with a warning log.

Tests: `tests/write/test_generator_wire.py` — 3 tests, all pass.
Full write test suite: 37 tests, all pass.

## Slice 5 — `--watchlist-wire` CLI flag (2026-03-26)

Added `--watchlist-wire` flag to `write_command` in `sable/commands/write.py`.
Passes `watchlist_wire=watchlist_wire` to `generate_tweet_variants`.

Verified: `sable write --help` shows `--watchlist-wire`.

## Slice 6 — Docs (2026-03-26)

Created `docs/IMPLEMENTATION_QUEUE.md`, `docs/IMPLEMENTATION_LOG.md`,
`docs/IMPLEMENTATION_REPORT.md`.

---

# Implementation Log — F1: Diagnose→Action Pipeline (2026-03-26)

## Slice 1 — Extend `Finding` dataclass

Added `suggested_command: str | None = None` to `Finding` in `sable/diagnose/runner.py`.
Backward compatible — defaults to None.

## Slice 2 — `_map_finding_to_command` + `_attach_suggested_commands`

Added two functions to `sable/diagnose/runner.py`:
- `_map_finding_to_command(finding, handle, org)` — regex-matches `finding.message` to return
  a runnable `sable` command string, or None. Covers 10 finding patterns (8 WARNING, 2 INFO).
- `_attach_suggested_commands(findings, handle, org)` — mutates findings in place; called from
  `run_diagnosis` after all audit functions run. No changes to any audit function signatures.

Note: `Niche surging format unused by account:` pattern regex uses `unused(?:\s+by\s+account)?:`
to match the actual message format in `_audit_format_portfolio`.

## Slice 3 — Update `render_diagnosis`

Two additions:
- Inline `→ Run: <cmd>` line after each finding that has a `suggested_command`.
- `Quick Actions:` numbered block at the bottom — WARNING findings with commands only.
  INFO findings with commands appear inline but not in Quick Actions.

## Slice 4 — Add `diagnosis_to_json`

Added `diagnosis_to_json(report)` to `sable/diagnose/runner.py`. Serializes to dict
including `suggested_command` per finding. Function did not previously exist.

## Slice 5 — Tests

Added 7 tests to `tests/diagnose/test_runner.py` (tests 13–19):
- `test_suggested_command_over_indexed`
- `test_suggested_command_stale_inventory`
- `test_suggested_command_hot_topic`
- `test_suggested_command_topic_gap`
- `test_suggested_command_niche_format`
- `test_render_diagnosis_shows_action_line`
- `test_render_diagnosis_quick_actions_block`

All 12 existing tests still pass unchanged.

---

# Audit Remediation (2026-04-01 to 2026-04-02)

Full remediation of 8 AUDIT items identified by maintainer review + Codex line-level
analysis. Each phase gated by adversarial QA subagent (trained on AGENTS.md +
docs/QA_WORKFLOW.md + docs/THREAT_MODEL.md). 5 QA rounds total.

## Phase 1 — AUDIT-8: Migration test version (35ec0be)

Changed `tests/platform/test_migration.py` to derive expected version from
`_MIGRATIONS[-1][1]` instead of hardcoded `14`.

## Phase 2 — AUDIT-1: Secret handling + CLI error redaction (35ec0be)

- `SECRET_ENV_MAP` in `config.py` as single source of truth for secret→env var mapping
- `config set` hard refusal for secret keys (was: warning only)
- `require_key()` error message points to env var, not `sable config set`
- `elevenlabs_api_key` added to `_DEFAULTS` and `SECRET_ENV_MAP`
- Tests: `tests/test_cli_config.py` (9 tests)

## Phase 3 — AUDIT-2: Scanner tweet validation (6ba93e7)

- `_normalise_tweet()` returns `Optional[dict]`; rejects missing id, unparseable date
- `_CORE_ENGAGEMENT_KEYS` presence check; `_safe_int()` coercion for non-core fields
- Callers filter None results, emit `console_warn()` with skip count
- Tests: `tests/pulse/meta/test_scanner_validation.py` (11 tests)

## Phase 4 — AUDIT-3/4/5/6/7 (6ba93e7)

- AUDIT-3: `MIN_SAMPLE = 5` gate in `recommender.py`
- AUDIT-4: Small-vault search fallback parity (try/except + keyword_prescore)
- AUDIT-5: `org_id` threaded through digest, recommender, scorer, vault search/suggest;
  digest SQL fixed (`org_id` not `id`/`slug`); `MAX_DIGEST_POSTS = 25`
- AUDIT-6: `SECRET_ENV_MAP` dedup, org_id patterns explicit
- AUDIT-7: Silent `except: pass` → `logger.warning()` in api.py, suggest.py, digest.py
- Tests: across `test_recommender.py`, `test_search.py`, `test_suggest.py`,
  `test_scorer.py`, `test_api.py`, `test_digest.py`

## Codex hardening round 1 (872fe19)

- Non-numeric core engagement values (`"not_a_number"`) now reject the tweet (was: coerced to 0)
- Non-core fields still coerce via `_safe_int()`
- Tests: updated `test_scanner_validation.py` (split into core/non-core tests)

## Codex hardening round 2 (9d4f24b)

- `enrich_batch()` + `_enrich_chunk()` accept `org` param; pass `org_id` to Claude
- Silent `except Exception` in enrich → `logger.warning("Enrichment chunk failed ...")`
- Both callers (`sync.py`, `cli.py`) updated to pass `org=org`
- TODO.md banner fixed (607→625→634)
- Tests: 4 new in `test_enrich.py`

Validation: 592→620→625→634 passed. ruff clean, mypy clean.

---

# SocialData API Hardening (2026-04-02)

Audited all SocialData call sites against `SablePlatform/docs/SOCIALDATA_BEST_PRACTICES.md`.

## Centralized HTTP client (e722e94)

New `sable/shared/socialdata.py`:
- `socialdata_get_async()` / `socialdata_get()` — single entry point for all SocialData calls
- 402: `BalanceExhaustedError` raised immediately, no retry
- 429: exponential backoff with jitter (1s→4s→16s→64s), 4 retries
- 5xx: same retry schedule as 429
- Network errors (timeout/DNS/connection): retried with same schedule
- Other 4xx: raised immediately

Refactored 4 modules to use shared client:
- `scanner.py`: removed `_get_headers()`, inline 429 handling, `retry_with_backoff_async`
  wrapper; added `BalanceExhaustedError` propagation past per-author exception handlers
- `tracker.py`: removed `_get_headers()`, direct httpx calls
- `trends.py`: removed `_get_headers()`, direct httpx calls, unused imports
- `suggest.py`: removed direct httpx call; fixed endpoint `/twitter/tweet/` → `/twitter/tweets/`

Tests: 9 new in `tests/shared/test_socialdata.py` (402, 429 retry+exhaust, 5xx, 200,
404, network error retry+exhaust, backoff schedule). 2 suggest tests simplified.

Validation: 625→634 passed. ruff clean, mypy clean.

---

# Community Intelligence Features (2026-04-03)

10-phase implementation of all community intelligence features from the multi-agent
feature competition. Each phase gated by adversarial QA subagent (3-tier framework:
Tier 1 prod/cost/secrets, Tier 2 maintainability, Tier 3 test coverage).

## Phase 1 — FEATURE-11A: Watchlist Amplifiers
New `sable/pulse/meta/amplifiers.py`: `compute_amplifiers()` with RT_v, RPR, QTR signals.
CLI: `sable pulse watchlist --amplifiers`. Tests: ~16.

## Phase 2 — FEATURE-10: Community Lexicon
New `sable/lexicon/` package: scanner, store, writer, CLI. Exclusivity filter, LSR math,
optional Claude interpretation. `lexicon_terms` table in meta.db.
`sable write --lexicon` flag for prompt injection. Tests: ~27.

## Phase 3 — FEATURE-12: Voice Check
`sable write --voice-check` flag. `assemble_voice_corpus()` in generator.py loads
tone.md + notes.md + vault notes. `score_draft()` accepts `voice_corpus` param. Tests: ~12.

## Phase 4 — FEATURE-14: Narrative Velocity
New `sable/narrative/` package: tracker, models, CLI. `load_beats()` parses YAML,
`score_uptake()` computes keyword spread. Imports MIN_AUTHORS/MIN_TWEETS from lexicon.
Tests: ~18.

## Phase 5 — FEATURE-15: Style Delta
New `sable/style/` package: fingerprint, delta, report, CLI. `_COARSE_MAP` covers both
posts.sable_content_type and scanned_tweets.format_bucket vocabularies. Tests: ~20.

## Phase 6 — FEATURE-16: Silence Gradient
New `sable/cadence/` package: signals, combine, store, CLI. Three signals (vol_drop,
eng_drop, fmt_reg) with proportional weight redistribution. `author_cadence` table in
meta.db. Tests: ~32.

## Phase 7 — FEATURE-11B: Bridge Node Signals
`sable advise --bridge-aware` flag. `_assemble_bridge_section()` in stage1.py queries
sable.db for bridge_node entities, meta.db for recent engagement. Tests: 6.

## Phase 8 — FEATURE-13: Community Language Injection
`sable advise --community-voice` flag. `_assemble_community_language()` in stage1.py
queries diagnostic_runs for language_arc_phase, cultural terms, mantra candidates.
14-day freshness gate. Tests: 6.

## Phase 9 — CHURN-1: Intervention Playbook
New `sable/churn/` package: interventions, prompts, CLI. One Claude call per at-risk
member with budget check. Soft cap at 50 members. Tests: 16.

## Phase 10 — CHURN-2: Calendar Integration
`sable calendar --churn-input --prioritize-churn` flags. CalendarSlot gains
`churn_targets` field. 30% slot cap enforcement. Tests: 11.
`sable advise --churn-input` flag for brief integration.

## QA Findings Fixed
- volume_drop(0,0) misleading max-drop → now returns insufficient
- Bridge section meta query cross-org data leak → org filter added
- scored_at → started_at column name fix in community language
- Calendar CLI missing SableError catch → added
- Non-dict JSON guard in churn interventions → type check added

Validation: 798 passed, 0 ruff violations, 0 mypy errors.

---

# Phase 2 — `sable serve` (2026-04-03)

Read-only FastAPI backend exposing pulse, meta, and vault data over HTTP.

## Implementation

New `sable/serve/` package:
- `app.py` — app factory, mounts routes, registers /health
- `auth.py` — Bearer token dependency, reads `serve.token` from config
- `deps.py` — DB connection helpers for pulse.db, meta.db, vault
- `routes/` — endpoint modules for pulse, meta, vault

## Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | No | Health check |
| GET | `/api/pulse/performance/{org}` | Yes | Pulse performance summary |
| GET | `/api/pulse/posting-log/{org}` | Yes | Posting log |
| GET | `/api/meta/topics/{org}` | Yes | Topic signals |
| GET | `/api/meta/baselines/{org}` | Yes | Format baselines |
| GET | `/api/meta/watchlist/{org}` | Yes | Watchlist entries |
| GET | `/api/vault/inventory/{org}` | Yes | Vault inventory |
| GET | `/api/vault/search/{org}?q=...` | Yes | Vault keyword search |

## Key decisions

- Read-only: no mutations, no Claude calls, zero API cost
- Bearer token auth on all `/api/` routes; `/health` is unauthenticated
- Optional dependency: `pip install -e ".[serve]"` (FastAPI + uvicorn)
- Config key: `serve.token` in `~/.sable/config.yaml`

## Tests

30 new tests in `tests/serve/` covering all endpoints, auth rejection, and health check.

Validation: 828 passed, 0 ruff violations, 0 mypy errors.

---

## P0-1 — `sable advise --org` Flag (2026-04-04)

**Bug:** `sable advise` required the handle to be in Slopper's roster with an org association. SablePlatform's `SlopperAdvisoryAdapter` resolves org → handle via `entity_handles`, but if the resolved handle isn't in the roster, advise fails with `HANDLE_NOT_IN_ROSTER`.

**Fix:** Added `--org ORG_ID` flag to `sable advise`. When provided:
- Overrides the roster account's org association
- Allows handles not in the Slopper roster to run advise (profile files fall back to defaults)
- Empty string `--org ""` is treated as None (falls through to roster)

**Files changed:**
- `sable/commands/advise.py` — `--org` option, passed to `generate_advise()`
- `sable/advise/generate.py` — `org: str | None` parameter, resolution: `org or account.org`
- Also fixed variable shadowing: `org` DB row → `org_row` to preserve the parameter

**Tests:** 9 new in `tests/advise/test_org_flag.py` — org override, handle-not-in-roster, error precedence, empty string, CLI wiring.

**QA:** Adversarial 2 rounds. Round 1: 2 T2 + 1 T3 findings (shadowing, empty-string edge case, help text). All fixed. Round 2: clean.

Validation: 859 passed, 0 ruff violations.

---

## P1-3 — Pulse Freshness Sync to `sable.db sync_runs` (2026-04-04)

**Problem:** `sable pulse track` and `sable pulse meta scan` write to `pulse.db` and `meta.db` respectively, but never record a sync timestamp in `sable.db sync_runs`. SablePlatform's `weekly_client_loop` freshness checks can't see when pulse data was last refreshed.

**Fix:** After successful completion, both commands now write a `sync_runs` row:
- `pulse track` → `sync_type='pulse_track'`, `records_synced=len(tweets)`
- `meta scan` → `sync_type='pulse_meta_scan'`, `records_synced=tweets_new`

**Design:** Non-fatal — sync_runs write failures log a warning but don't fail the command. Connection wrapped in try/finally. Exception narrowed to `(sqlite3.Error, OSError)`. `pulse track` resolves org via roster; `meta scan` has org as a required CLI option.

**Files changed:**
- `sable/pulse/cli.py` — sync_runs write after `snapshot_account()` success
- `sable/pulse/meta/cli.py` — sync_runs write after `complete_scan_run()`

**Tests:** 6 new in `tests/pulse/test_sync_runs.py` — write, skip-no-org, skip-not-in-roster, non-fatal failure (for each command).

**Remaining:** SablePlatform `weekly_client_loop.py` needs updating to query these new sync_type values.

**QA:** Adversarial 2 rounds. Round 1: 4 T2 + 2 T3 findings (connection leak, broad except, lazy imports, naming). All fixed. Round 2: clean.

Validation: 865 passed, 0 ruff violations.

---

## P1-2 — Cost Logging for Non-Advise Claude Calls (2026-04-04)

**Problem:** `call_claude_with_usage()` couples budget checking and cost logging. Write/score/clip are operator-initiated and should log costs but not budget-gate.

**Fix:** Added `budget_check: bool = True` parameter to `call_claude_with_usage`, `call_claude`, `call_claude_json`. When False + org_id provided, `check_budget()` is skipped but `log_cost()` still runs.

**Files changed:**
- `sable/shared/api.py` — core `budget_check` parameter
- `sable/write/generator.py` — `budget_check=False` on write_variants call
- `sable/write/scorer.py` — `budget_check=False` on score_patterns + score_draft calls
- `sable/clip/selector.py` — `org_id` param added to `select_clips()` and `_evaluate_variants_batch()`
- `sable/clip/cli.py` — `--org` flag added to clip process
- `sable/churn/interventions.py` — fixed double budget check (pre-existing)
- `sable/lexicon/writer.py` — fixed double budget check + connection leak (pre-existing)

**Tests:** 11 new across `tests/shared/test_api_budget_check.py` and `tests/clip/test_clip_cost_logging.py`.

**QA:** Adversarial 2 rounds. Round 1: 3 T1 (double budget checks, conn leak), 4 T2, 4 T3. T1s fixed. Round 2: clean.

Validation: 876 passed, 0 ruff violations.

---

## P2-4 — Content Performance Outcomes from Pulse Snapshots (2026-04-04)

**Problem:** Pulse snapshots capture engagement metrics per post, but no outcomes are written to `sable.db outcomes`. SableWeb impact timeline has no data source.

**Fix:** New `sync_content_outcomes(org_id, handle, conn)` in `sable/pulse/outcomes.py`. Reads pulse.db posts+snapshots, groups by `sable_content_type`, computes per-type avg engagement rate (view-normalised), writes outcome rows with delta from prior via `create_outcome()`.

**Files changed:**
- `sable/platform/outcomes.py` — thin re-export of `create_outcome`, `list_outcomes`
- `sable/pulse/outcomes.py` — `sync_content_outcomes()` implementation
- `sable/pulse/cli.py` — `sable pulse outcomes --org --handle` subcommand

**Tests:** 8 new in `tests/pulse/test_outcomes.py`.

**QA:** Adversarial 2 rounds. Round 1: 0 T1, 3 T2 (redundant queries, non-atomic writes, formula choice), 4 T3. FIND-01 fixed (single query with dict lookup). Round 2: clean.

Validation: 884 passed, 0 ruff violations.

---

## P2-6 — Vault Content as Platform Artifacts (2026-04-04)

**Problem:** Content from `sable meme` and `sable clip` is not registered in `sable.db artifacts`. SableWeb can't list content pipeline output.

**Fix:** New `register_content_artifact(org_id, artifact_type, path, metadata)` in `sable/platform/artifacts.py`. Fully non-fatal — `get_db()` and INSERT inside try/except Exception. Integrated into meme generate, meme batch, and clip process. Only fires when org is resolvable.

**Files changed:**
- `sable/platform/artifacts.py` — new helper
- `sable/meme/cli.py` — registration after meme generate + meme batch render
- `sable/clip/cli.py` — registration after each clip assembly

**Tests:** 7 new across `tests/platform/test_artifacts_helper.py`, `tests/meme/test_meme_artifact.py`, `tests/clip/test_clip_artifact.py`.

**QA:** Adversarial 2 rounds. Round 1: 0 T1, 4 T2 (get_db outside try, batch gap, naming, conn overhead), 3 T3. Fixed: get_db inside try, batch registration added. Round 2: clean.

Validation: 891 passed, 0 ruff violations.

---

## Cost Observability — org_id threading for all Claude calls (2026-04-04)

**Problem:** 8 Claude call sites in meme (3), wojak (1), thumbnail (1), character_explainer (2) generators had no `org_id`, making their spend invisible in `cost_events`. Vault search/suggest and pulse recommend had `call_type="unknown"`.

**Fix:** Added `org_id: str | None = None` parameter to all generator functions (`generate_meme_text`, `suggest_template`, `generate_batch`, `generate_scene`, `_get_headline_and_palette`, `generate_thumbnail`, `assemble_clip`, `generate_script`, `_distill_background`, `generate_explainer`). CLI handlers thread `acc.org` through. Character explainer gained `--org` flag. All use `budget_check=False` (cost logged, not budget-gated). Added descriptive `call_type` values to vault/pulse calls that had `"unknown"`.

**Files:** 13 source files modified (`sable/meme/generator.py`, `sable/meme/cli.py`, `sable/wojak/generator.py`, `sable/wojak/cli.py`, `sable/clip/thumbnail.py`, `sable/clip/assembler.py`, `sable/clip/cli.py`, `sable/character_explainer/script.py`, `sable/character_explainer/pipeline.py`, `sable/character_explainer/cli.py`, `sable/pulse/recommender.py`, `sable/vault/search.py`, `sable/vault/suggest.py`).

**Tests:** 8 new in `tests/test_cost_observability.py`.

**QA:** Adversarial 1 round. FIND-07: stale schema in `test_account_report.py` — fixed. All else clean.

---

## Stale Test Schemas — scanned_tweets alignment (2026-04-04)

**Problem:** `test_anatomy.py`, `test_digest.py`, and `test_account_report.py` had `scanned_tweets` test schemas missing 7–35 columns vs production `_SCHEMA` in `sable/pulse/meta/db.py`.

**Fix:** Updated all three test files to use the full production `scanned_tweets` schema. 72 affected tests still pass.

Validation: 899 passed, 0 ruff violations.

---

## Brainrot Theme Matching (2026-04-04)

**Problem:** Brainrot overlay videos were selected by duration + energy only. No content awareness — a clip about DeFi regulation could get paired with random gaming footage.

**Fix:** Claude now returns `theme_tags` (1-3 topic keywords) per clip during selection. Tags are threaded through `_resolve_clip` → `_evaluate_variants_batch` → `assemble_clip` → brainrot `pick()`. The `pick()` function uses layered preference: theme-matched + long duration > theme-matched > long duration > any. Falls back to untagged sources when no theme match exists — never fails to find a source.

**Files:** `sable/clip/selector.py` (prompt + threading), `sable/clip/assembler.py` (new `theme_tags` param), `sable/clip/brainrot.py` (refactored `pick()` + new `_pick_best()` helper), `sable/clip/cli.py` (threading).

**Tests:** 6 new in `tests/clip/test_brainrot.py` (theme preference, fallback, theme+duration, no-tags, selector threading).

---

## SocialData Hardening: Cost Breakdown, Cost Logging, Cursor Cycling, Checkpoint/Resume (2026-04-04)

### Per-phase cost breakdown
Scanner now tracks `_cost_fetch` and `_cost_deep` separately. Returns `cost_breakdown` dict in scan results. CLI output shows per-phase costs (e.g., "fetch $0.040, deep $0.006"). 3 tests.

### SocialData cost logging to sable.db
Meta scan CLI and pulse track CLI now log SocialData API costs to `sable.db cost_events` via `log_cost()` with `model="socialdata"` and descriptive `call_type` values. Non-fatal pattern. 3 tests.

### Cursor cycling for >100 tweets
`_fetch_author_tweets_async` now paginates via `next_cursor` from SocialData API. Caps at 32 pages (3200 tweets). Uses integer tweet ID comparison for `since_id` (per AR5-9). Returns `(tweets, request_count)` so scanner can track per-author cost accurately. Budget-aware page cap prevents one prolific author from consuming the entire scan budget. 6 tests.

### Checkpoint/resume for interrupted scans
New `scan_checkpoints` table in meta.db. Scanner writes per-author checkpoint after processing. New `--resume SCAN_ID` CLI flag resumes an interrupted scan, skipping already-checkpointed authors. Validates scan_id exists before resuming. 5 tests.

**QA:** Adversarial agent found 3 T1 issues (deep cost undercount in `_estimated_cost`, unbounded per-author pagination budget, orphaned resume scan_id), 2 T2 (hardcoded cost assumption in tracker, duplicate DB pattern). All fixed.

**Files:** `sable/pulse/meta/scanner.py`, `sable/pulse/meta/db.py`, `sable/pulse/meta/cli.py`, `sable/pulse/cli.py`, `sable/clip/brainrot.py`.

Validation: 921 passed, 0 ruff violations, 0 new mypy errors.

---

## Codit Audit Full Remediation (2026-04-05)

Closed all remaining findings from the Codex audit (`codit.md`, 2026-03-23):

- **CRIT-1:** Vault platform_sync partial-sync window — pulse report staging moved before Phase B renames. `_cleanup_temps()` helper extracted. TOCTOU fix on pulse source read. 2 new tests.
- **HIGH-5:** Deep-mode outsider results now explicitly marked transient in console output.
- **MED-5:** `SearchResult.degraded` field signals keyword-fallback results to callers.
- **MED-10:** `upsert_format_baseline` renamed to `insert_format_baseline` with same-second dedup. 1 new test.

Three adversarial QA passes confirmed zero remaining findings.

**Files:** `sable/vault/platform_sync.py`, `sable/vault/search.py`, `sable/pulse/meta/db.py`, `sable/pulse/meta/cli.py`, `sable/pulse/meta/baselines.py`, `tests/vault/test_vault_sync.py`, `tests/vault/test_platform_sync.py`, `tests/pulse/meta/test_meta_db.py`.

Validation: 1157 passed, 0 ruff violations, 0 mypy errors.

---

## RBAC for sable serve (2026-04-05)

Role-based access control with per-operator org scoping on all serve API routes.

### Roles + permission matrix
Three roles: admin (unrestricted), creator (read+write, scoped), operator (read-only, scoped).
Operators see only their configured `orgs` list. Fail-closed: no orgs = no access.
See `docs/ROLES.md` for the full permission matrix.

### Token config (backwards-compatible)
Extended `serve.tokens` config to support dict entries with `role` + `orgs`. Legacy plain-string tokens treated as admin. Unknown roles default to operator (least privilege).

### Route enforcement
Every route calls `require_org_access(request, org, Action.xxx)`. Router-level `verify_token` dependency ensures all routes are authenticated. Empty-string token bypass prevented.

### Security
- Timing-safe token comparison (hmac.compare_digest)
- Immutable `ClientIdentity.allowed_orgs` (tuple, not list)
- Empty-string token guard on all config paths
- 22 RBAC tests (unit + integration + edge cases)

**QA:** Adversarial security audit found one MAJOR (empty-string token bypass on legacy path) — fixed before merge. Final audit clean.

**Files:** `sable/vault/permissions.py`, `sable/serve/auth.py`, `sable/serve/routes/vault.py`, `sable/serve/routes/pulse.py`, `sable/serve/routes/meta.py`, `sable/serve/app.py`, `tests/serve/test_rbac.py`, `tests/serve/test_*.py` (bypass auth updates), `docs/ROLES.md`.

Validation: 1179 passed, 0 ruff violations, 0 mypy errors.

---

## Weekly Automation & Operator Streamlining (2026-04-06)

Reduces operator time from ~4 hours/week per 3-5 accounts to <1 hour/week per 5 accounts.

### `sable weekly run`

New `sable/weekly/` module with `WeeklyRunner` class orchestrating 5 steps:
1. `pulse_track` — `snapshot_account()` per rostered account
2. `meta_scan` — instantiate `Scanner`, run full scan
3. `advise` — `generate_advise()` per account
4. `calendar` — `build_calendar()` + save per account
5. `vault_sync` — `platform_vault_sync(org)`

Each step runs independently — failure in one doesn't block the rest. Cost delta measured via `get_weekly_spend()` before/after each step.

CLI flags: `--org ORG` (single org), `--all` (discover all rostered orgs), `--dry-run` (print plan only), `--cost-estimate` (SocialData + Claude cost estimate without execution). `--org` and `--all` are mutually exclusive.

**Files:** `sable/weekly/__init__.py`, `sable/weekly/runner.py`, `sable/weekly/cli.py`, `sable/cli.py`.
**Tests:** 16 in `tests/weekly/test_runner.py`, 7 in `tests/weekly/test_cli.py`.

### `sable weekly cron install`

New `sable/weekly/cron.py` — launchd plist generator following `com.sable.serve.plist` pattern. Writes `~/Library/LaunchAgents/com.sable.weekly.plist` with `StartCalendarInterval` for Monday 06:00. Prints `launchctl load`/`unload` activation instructions.

**Files:** `sable/weekly/cron.py`, `sable/weekly/cli.py`.

### `sable clip review --org ORG`

New `sable/clip/review.py` — interactive triage queue. `find_unreviewed_clips(org)` scans workspace for `.meta.json` / `_meta.json` files lacking `vault_note_id`. Operator can approve (stamps `vault_note_id`), skip, or delete (moves to `_rejected/` subdirectory). Auto-runs vault sync after approvals.

**Files:** `sable/clip/review.py`, `sable/clip/cli.py`.
**Tests:** 7 in `tests/clip/test_review.py`.

### `GET /api/v1/cost/org/{org_id}/cost-forecast`

New `sable/serve/routes/cost.py` — cost forecast endpoint. Returns `weekly_estimated_usd`, `monthly_estimated_usd`, `last_7d_actual_usd`, `budget_remaining_usd`, `top_cost_drivers`. Uses `require_org_access(request, org_id, Action.pulse_read)` for RBAC.

**Files:** `sable/serve/routes/cost.py`, `sable/serve/app.py`.
**Tests:** 4 in `tests/serve/test_cost_routes.py`.

Validation: 1213 passed, 0 ruff violations, 0 mypy errors.
