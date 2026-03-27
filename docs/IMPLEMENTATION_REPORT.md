# Implementation Report — Vault Niche-Gaps + Watchlist Win Wire

**Date:** 2026-03-26
**Status:** Complete — all slices implemented and tested.

## Summary

Implemented two interconnected features:

1. **Vault Niche-Gaps** (`sable vault niche-gaps`): surfaces trending topics from
   meta.db scan data that have no vault coverage. Helps identify content production
   opportunities based on real community signal.

2. **Watchlist Wire** (`sable write --watchlist-wire`): injects the top 3 niche-trending
   topics from meta.db into the write prompt so Claude can factor live community
   signal when generating tweet variants.

## Files Changed

| File | Change |
|------|--------|
| `sable/pulse/meta/db.py` | Added `get_top_topic_signals()` |
| `sable/vault/gaps.py` | Added `VaultSignalGap`, `compute_signal_gaps()`, `render_signal_gaps()` |
| `sable/vault/cli.py` | Added `vault niche-gaps` command |
| `sable/write/generator.py` | Added `watchlist_wire` parameter and injection logic |
| `sable/commands/write.py` | Added `--watchlist-wire` flag |

## Files Created

| File | Purpose |
|------|---------|
| `tests/pulse/meta/test_db_top_signals.py` | 6 tests for `get_top_topic_signals` |
| `tests/vault/test_gaps_niche.py` | 8 tests for signal gap logic |
| `tests/write/test_generator_wire.py` | 3 tests for watchlist wire injection |

## Test Results

- `tests/pulse/meta/test_db_top_signals.py`: 6/6 pass
- `tests/vault/test_gaps_niche.py`: 8/8 pass
- `tests/write/`: 37/37 pass

## Design Decisions

- Lazy import of `get_top_topic_signals` inside `compute_signal_gaps` function body
  to avoid circular imports between vault and pulse.meta packages.
- `compute_signal_gaps` returns `[]` when no meta.db file exists on disk — no crash,
  no misleading empty-table output.
- `watchlist_wire=False` is the default; zero behavior change for existing callers.
- Wire errors are swallowed with a warning log, not raised — write command must never
  fail due to missing signal data.
- `render_signal_gaps` uses Rich markup for the empty-state message but plain table
  text for the non-empty case (works in both Rich and plain-text contexts).

---

# Implementation Report — F1: Diagnose→Action Pipeline

**Date:** 2026-03-26
**Status:** Complete — all slices implemented and tested.

## Summary

Every WARNING (and actionable INFO) finding in `sable diagnose` now emits a runnable
`sable` command. Operators can close the loop without manually translating findings into
commands. The pipeline uses a post-process approach: all 5 audit functions are unchanged;
`_attach_suggested_commands` mutates findings after they're collected.

## Files Changed

| File | Change |
|------|--------|
| `sable/diagnose/runner.py` | Added `suggested_command` field to `Finding`; added `_map_finding_to_command`, `_attach_suggested_commands`, `diagnosis_to_json`; updated `run_diagnosis` and `render_diagnosis` |
| `tests/diagnose/test_runner.py` | Added 7 new tests (tests 13–19) |
| `docs/IMPLEMENTATION_LOG.md` | F1 log entries |
| `docs/IMPLEMENTATION_REPORT.md` | This report |

## Design Decisions

- Post-process approach: audit functions are untouched. Commands are attached in one pass
  after all findings are collected, keeping the mapper logic centralized.
- `re` was already imported — no new imports needed.
- INFO findings get inline `→ Run:` lines but are excluded from Quick Actions (warnings-first UX).
- `diagnosis_to_json` was not previously present; added as new function.
