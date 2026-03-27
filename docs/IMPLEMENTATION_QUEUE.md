# Implementation Queue — Vault Niche-Gaps + Watchlist Win Wire

All slices complete as of 2026-03-26.

## Slices

| # | Name | Status | Files |
|---|------|--------|-------|
| 1 | Shared DB helper: `get_top_topic_signals` | DONE | `sable/pulse/meta/db.py`, `tests/pulse/meta/test_db_top_signals.py` |
| 2 | Gap logic: `compute_signal_gaps` + `render_signal_gaps` | DONE | `sable/vault/gaps.py`, `tests/vault/test_gaps_niche.py` |
| 3 | CLI wiring: `vault niche-gaps` | DONE | `sable/vault/cli.py` |
| 4 | Write generator: `watchlist_wire` injection | DONE | `sable/write/generator.py`, `tests/write/test_generator_wire.py` |
| 5 | CLI wiring: `--watchlist-wire` flag | DONE | `sable/commands/write.py` |
| 6 | Docs | DONE | `docs/IMPLEMENTATION_QUEUE.md`, `docs/IMPLEMENTATION_LOG.md`, `docs/IMPLEMENTATION_REPORT.md` |
