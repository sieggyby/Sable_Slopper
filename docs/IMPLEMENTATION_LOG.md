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
