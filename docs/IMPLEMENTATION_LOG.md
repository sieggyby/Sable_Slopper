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
