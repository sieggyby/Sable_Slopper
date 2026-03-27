# Product Review: Vault Gap Alert + Watchlist Win Wire
> Multi-agent product review — 2026-03-26. Winner: F2 (Vault Gap Alert). Salvage: Watchlist Win Wire.

---

## Executive Summary

Two features emerge from a full PM Council + QA Board review of the Sable_Slopper codebase:

1. **`sable vault gaps --org ORG`** — Cross-references `topic_signals` (niche trending topics from meta.db) against vault note coverage. Outputs a creation priority queue ranked by `avg_lift × acceleration × unique_authors`. Closes an analyst workflow gap that currently has no tool answer: "what should I be creating content on right now?"

2. **`sable write --watchlist-wire`** — Injects top-3 trending niche topics (from `topic_signals`) into the write prompt as a "what's crushing it in your niche this week" context block. Optional flag, off by default.

Both features: zero schema changes, zero new infrastructure, pure read-side meta.db + vault queries, ~150 LOC combined.

**Deferred (next session):** Diagnose→Action Pipeline (F1). **Deferred (strategic):** Cross-Org Niche Delta (F3).

---

## Scope / Out of Scope

**In scope:**
- `sable/vault/gaps.py` — new module with `compute_gap_queue()` function
- `sable/commands/vault.py` — new `gaps` subcommand wiring
- `sable/write/generator.py` — `--watchlist-wire` context injection
- `sable/commands/write.py` — `--watchlist-wire` flag
- Shared helper: `get_top_topic_signals(org, meta_db_path, limit)` extracted to `sable/pulse/meta/db.py` (deduplicates inline queries in diagnose and gaps)
- Tests: `tests/vault/test_gaps.py`, `tests/write/test_generator_watchlist.py`

**Out of scope this session:**
- Diagnose→Action Pipeline (F1) — own session, ~80 LOC
- Cross-Org Niche Delta (F3) — strategic tool, own session
- `--compare-org` flag on vault gaps — deferred after base ships
- Auto-Pulse Capture — requires scheduler infrastructure
- Calendar state persistence — Phase 2
- Recommender downstream wiring — Phase 2

---

## Architecture Impact

No schema changes. No new tables. No migrations.

Data flow for **Vault Gap Alert:**
```
meta.db:topic_signals (filtered to latest scan per org)
    → get_top_topic_signals(org, meta_db_path, limit=20)
    → set of (term, avg_lift, acceleration, unique_authors)

~/.sable-vault/ (via load_all_notes())
    → set of covered terms (topics[] + keywords[] from all note frontmatter)

Gap = topic_signals terms NOT in vault coverage
    → score each gap: avg_lift × acceleration × max(unique_authors, 1)
    → sort descending, emit top N

Output: terminal table (term | signal_score | niche_lift | recommended_type)
        + optional --json flag for piping
```

Data flow for **Watchlist Win Wire:**
```
meta.db:topic_signals (same helper)
    → top 3 by avg_lift × acceleration
    → injected as "niche_wire_block" into generate_tweet_variants prompt
    → positioned alongside vault_block and source_block in user_prompt
```

File dependency graph (new arrows only):
```
sable/vault/gaps.py
  ← sable/vault/notes.py (load_all_notes — existing)
  ← sable/pulse/meta/db.py (get_top_topic_signals — new helper)
  ← sable/shared/paths.py (meta_db_path, vault_dir — existing)

sable/write/generator.py
  ← sable/pulse/meta/db.py (get_top_topic_signals — same new helper)
```

---

## Step-by-Step Implementation Plan

### Slice A: Shared Data Access Helper

**File:** `sable/pulse/meta/db.py`

Add function `get_top_topic_signals`:

```python
def get_top_topic_signals(
    org: str,
    limit: int = 20,
    min_unique_authors: int = 1,
    conn: Optional[sqlite3.Connection] = None,
) -> list[dict]:
    """Return top topic signals for org from the most recent scan.

    Filters to the latest scan_id per org to avoid stale signal data.
    Returns dicts with: term, avg_lift, acceleration, unique_authors, mention_count.
    Scored by avg_lift * acceleration * unique_authors descending.
    """
    _conn = conn or get_conn()
    try:
        rows = _conn.execute(
            """SELECT ts.term, ts.avg_lift, ts.acceleration,
                      ts.unique_authors, ts.mention_count
               FROM topic_signals ts
               INNER JOIN (
                   SELECT MAX(id) AS max_id FROM scan_runs
                   WHERE org = ?
                     AND completed_at IS NOT NULL
                     AND (claude_raw IS NULL OR claude_raw NOT LIKE 'FAILED:%')
               ) latest ON ts.scan_id = latest.max_id
               WHERE ts.org = ?
                 AND ts.unique_authors >= ?
               ORDER BY (ts.avg_lift * ts.acceleration * ts.unique_authors) DESC
               LIMIT ?""",
            (org, org, min_unique_authors, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        if conn is None:
            _conn.close()
```

**Why this matters:** Both `diagnose/runner.py` (line ~186–195) and the new `vault/gaps.py` have inline topic_signals queries. Extracting a shared helper eliminates duplication and gets the latest-scan filtering right in one place.

---

### Slice B: Vault Gap Alert

**File:** `sable/vault/gaps.py` (new)

```python
"""Vault coverage gap analysis — cross-references meta.db topic signals vs vault notes."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from sable.vault.notes import load_all_notes
from sable.pulse.meta.db import get_top_topic_signals
from sable.shared.paths import meta_db_path as default_meta_db_path, vault_dir


@dataclass
class VaultGap:
    term: str
    signal_score: float       # avg_lift * acceleration * unique_authors
    avg_lift: float
    acceleration: float
    unique_authors: int
    recommended_type: str     # 'standalone_text' | 'short_clip' | 'thread' | 'single_image'


def _terms_from_note(note: dict) -> set[str]:
    """Extract all searchable terms from a vault note."""
    terms: set[str] = set()
    for field in ("topic", "caption"):
        val = note.get(field, "") or ""
        terms.update(val.lower().split())
    for lst_field in ("topics", "keywords", "questions_answered"):
        for item in (note.get(lst_field) or []):
            terms.update(str(item).lower().split())
    return terms


def _recommend_type(term: str, avg_lift: float) -> str:
    """Heuristic: recommend content type based on signal characteristics."""
    # High lift = use the format currently surging; default to standalone_text
    # This is intentionally simple — operators override based on context
    if avg_lift >= 3.0:
        return "short_clip"
    elif avg_lift >= 2.0:
        return "standalone_text"
    else:
        return "standalone_text"


def compute_gap_queue(
    org: str,
    vault_path: Optional[Path] = None,
    meta_db: Optional[Path] = None,
    top_n: int = 10,
    min_unique_authors: int = 2,
) -> list[VaultGap]:
    """Compute prioritized creation queue: trending topics with no vault coverage.

    Returns list of VaultGap sorted by signal_score descending.
    Empty list if vault has no notes or meta.db has no topic signals.
    """
    resolved_vault = vault_path or vault_dir()
    resolved_meta = meta_db or default_meta_db_path()

    if not resolved_meta.exists():
        return []

    # Load vault coverage
    notes = load_all_notes(resolved_vault) if resolved_vault.exists() else []
    covered_terms: set[str] = set()
    for note in notes:
        covered_terms.update(_terms_from_note(note))

    # Load niche signals
    signals = get_top_topic_signals(
        org=org,
        limit=50,
        min_unique_authors=min_unique_authors,
        conn=None,
    )

    gaps: list[VaultGap] = []
    for sig in signals:
        term = sig["term"].lower()
        # Gap: term not present in any vault note's topic/keyword fields
        if not any(term in ct or ct in term for ct in covered_terms):
            score = (sig["avg_lift"] or 0.0) * max(sig["acceleration"] or 0.1, 0.1) * max(sig["unique_authors"], 1)
            gaps.append(VaultGap(
                term=sig["term"],
                signal_score=round(score, 3),
                avg_lift=sig["avg_lift"] or 0.0,
                acceleration=sig["acceleration"] or 0.0,
                unique_authors=sig["unique_authors"],
                recommended_type=_recommend_type(sig["term"], sig["avg_lift"] or 0.0),
            ))

    gaps.sort(key=lambda g: g.signal_score, reverse=True)
    return gaps[:top_n]


def render_gap_queue(gaps: list[VaultGap], org: str) -> str:
    if not gaps:
        return f"Vault Gap Alert ({org}): no gaps found — vault covers all trending topics, or no meta scan data available."

    lines = [f"Vault Gap Alert — {org}", ""]
    lines.append(f"{'#':<3}  {'Term':<20}  {'Score':>7}  {'Lift':>6}  {'Accel':>6}  {'Authors':>7}  Type")
    lines.append("─" * 72)
    for i, gap in enumerate(gaps, 1):
        lines.append(
            f"{i:<3}  {gap.term:<20}  {gap.signal_score:>7.2f}  "
            f"{gap.avg_lift:>6.2f}  {gap.acceleration:>6.2f}  "
            f"{gap.unique_authors:>7}  {gap.recommended_type}"
        )
    lines.append("")
    lines.append(f"{len(gaps)} gap(s) found. Run `sable write` or `sable clip process` to fill top gaps.")
    return "\n".join(lines)
```

**CLI wiring in `sable/commands/vault.py`:**

Locate the existing vault command group. Add:

```python
@vault.command("gaps")
@click.option("--org", required=True, help="Org name (matches meta.db scan org)")
@click.option("--top", default=10, show_default=True, help="Number of gaps to show")
@click.option("--min-authors", default=2, show_default=True, help="Min unique authors for signal")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def vault_gaps(org: str, top: int, min_authors: int, as_json: bool) -> None:
    """Show topics trending in niche with no vault coverage."""
    from sable.vault.gaps import compute_gap_queue, render_gap_queue
    import json as _json

    gaps = compute_gap_queue(org=org, top_n=top, min_unique_authors=min_authors)
    if as_json:
        click.echo(_json.dumps([vars(g) for g in gaps], indent=2))
    else:
        click.echo(render_gap_queue(gaps, org))
```

---

### Slice C: Watchlist Win Wire (`--watchlist-wire` on `sable write`)

**File:** `sable/write/generator.py`

In `generate_tweet_variants` function, after the `vault_context` assignment (around line 190), add:

```python
# Watchlist win wire (optional)
niche_wire_block = ""
if watchlist_wire and conn is not None:
    from sable.pulse.meta.db import get_top_topic_signals
    wire_signals = get_top_topic_signals(org=resolved_org, limit=3, min_unique_authors=1, conn=conn)
    if wire_signals:
        wire_lines = []
        for sig in wire_signals:
            wire_lines.append(
                f"  • \"{sig['term']}\" — {sig['avg_lift']:.1f}x lift, "
                f"{sig['unique_authors']} authors, acceleration {sig['acceleration']:+.2f}"
            )
        niche_wire_block = (
            "\nWhat's trending in your niche this week (niche intelligence — "
            "use for topic angles, not verbatim):\n" + "\n".join(wire_lines)
        )
```

Add `watchlist_wire: bool = False` parameter to `generate_tweet_variants` signature.

In prompt assembly, inject `niche_wire_block` alongside `vault_block`:
```python
f"Topic to write about: {topic_str}"
f"{source_block}"
f"{vault_block}"
f"{niche_wire_block}\n\n"  # add this line
```

**CLI wiring in `sable/commands/write.py`:**

Add `--watchlist-wire` flag to the write command and pass it through to `generate_tweet_variants`.

```python
@click.option("--watchlist-wire", is_flag=True, default=False,
              help="Inject top niche topics from meta.db into prompt")
```

---

## Edge Cases

| Case | Handling |
|------|----------|
| meta.db does not exist | `compute_gap_queue` returns `[]`; `render_gap_queue` prints "no meta scan data available" |
| No topic_signals for org | Same — empty signals → empty gap list |
| Vault is empty (0 notes) | All signals become gaps; output includes note "vault has 0 notes — all topics are gaps" |
| topic_signals from stale scan | `get_top_topic_signals` filters to MAX(scan_id) per org for non-failed scans |
| `--watchlist-wire` with no meta.db | `niche_wire_block` remains `""` — no prompt change, no error |
| term matching: "btc" vs "Bitcoin" | Fuzzy by substring (`term in ct or ct in term`); acceptable for MVP; documented as a known limitation |
| All vault terms cover all signal terms | `gaps = []`; render outputs positive "vault covers all trending topics" message |
| 1-author signal only | `min_unique_authors=2` default filters these out; `--min-authors 1` overrides |
| Org not in meta.db | Returns `[]` from `get_top_topic_signals`; no error |
| Large vault (500+ notes) | `load_all_notes()` is a disk loop; acceptable for current scale; note for future indexing |

---

## Tech Debt / Prerequisites

**Prerequisite:** Verify `sable/pulse/meta/db.py` is importable from `sable/vault/gaps.py` without circular import. Current import graph has no vault→pulse dependencies — check this before wiring.

**Tech debt introduced (none significant):**
- `_terms_from_note()` in `gaps.py` duplicates some field-extraction logic with `vault/search.py:keyword_prescore()`. Low priority to unify — different use cases (coverage check vs. relevance ranking).
- Inline `topic_signals` queries in `diagnose/runner.py:_audit_topic_freshness` (lines 183–196) and `_audit_vault_utilization` (lines 255–269) should be migrated to use `get_top_topic_signals()` helper in a follow-on cleanup pass. Not a blocker.

**Existing tech debt this touches:**
- `diagnose/runner.py` has duplicated meta.db connection patterns (two separate inline opens for topic_signals). The new shared helper reduces this in future.

---

## Acceptance Criteria

### `sable vault gaps`

- [ ] `sable vault gaps --org psy` outputs a ranked table of topics with niche signal but no vault coverage
- [ ] Output includes: term, signal score, avg_lift, acceleration, unique_authors, recommended_type
- [ ] Empty vault outputs all signal terms as gaps (with note about vault size)
- [ ] No meta.db outputs "no meta scan data available" message (non-error exit)
- [ ] `--json` flag outputs valid JSON array of gap objects
- [ ] `--top N` limits output to N rows
- [ ] `--min-authors N` filters signals with fewer than N unique authors
- [ ] Stale/failed scan data is excluded (latest successful scan only)
- [ ] No schema changes; no new DB tables; sable.db untouched

### `sable write --watchlist-wire`

- [ ] `sable write @handle --topic X --watchlist-wire` injects top-3 niche topics into prompt
- [ ] Without `--watchlist-wire`, behavior is identical to current (no regression)
- [ ] No meta.db → flag silently no-ops (no error, no prompt change)
- [ ] Wire block appears in prompt between vault context and generation instructions
- [ ] Wire block includes: term, lift score, unique authors, acceleration indicator

---

## Full Test Plan

### `tests/vault/test_gaps.py`

```
test_compute_gap_queue_empty_vault
  → vault has 0 notes; 5 topic signals → all 5 returned as gaps
  → verify signal_score computed correctly

test_compute_gap_queue_full_coverage
  → vault notes cover all signal terms → empty gap list returned

test_compute_gap_queue_partial_coverage
  → 3 signals: 2 covered, 1 not → 1 gap returned, correct term

test_compute_gap_queue_no_meta_db
  → meta.db path does not exist → returns []

test_compute_gap_queue_sorts_by_score
  → 3 gaps with different lift/acceleration → sorted descending by signal_score

test_compute_gap_queue_min_authors_filter
  → signal with 1 unique_author excluded when min_unique_authors=2
  → signal included when min_unique_authors=1

test_render_gap_queue_empty
  → empty gap list → "no gaps found" message

test_render_gap_queue_nonempty
  → 3 gaps → table output with correct column values
```

### `tests/pulse/meta/test_db_top_signals.py`

```
test_get_top_topic_signals_latest_scan_only
  → two scan_runs for same org; only signals from latest non-failed scan returned

test_get_top_topic_signals_excludes_failed_scans
  → latest scan_run has claude_raw = 'FAILED: ...' → uses prior scan

test_get_top_topic_signals_empty_org
  → no scan_runs for org → returns []

test_get_top_topic_signals_min_authors
  → signal with unique_authors=1 excluded at min_unique_authors=2
```

### `tests/write/test_generator_watchlist.py`

```
test_watchlist_wire_injects_block
  → generate_tweet_variants with watchlist_wire=True and meta.db populated
  → verify prompt contains niche wire terms

test_watchlist_wire_off_by_default
  → generate_tweet_variants with watchlist_wire=False
  → prompt does NOT contain wire block

test_watchlist_wire_no_meta_db
  → meta_db_path does not exist, watchlist_wire=True
  → no error; prompt unchanged from non-wire run
```

### Manual smoke tests

```
sable vault gaps --org psy --top 5
  → expect table with 5 rows, no crash

sable vault gaps --org neworg
  → expect "no meta scan data available" message

sable vault gaps --org psy --json | python3 -m json.tool
  → expect valid JSON

sable write @testhandle --topic "defi" --watchlist-wire
  → expect variants generated; inspect prompt logs for wire block
```

---

## Open Questions

1. **Term matching fidelity:** `term in covered_terms` uses substring matching. Will this produce false-positive "covered" judgments (e.g. "btc" matching "abstract")? Consider whole-word matching: `any(term == ct for ct in covered_terms)` vs. current substring. Trade-off: more gaps with strict match, fewer with substring. Recommend starting with substring and adjusting based on operator feedback.

2. **`recommended_type` heuristic:** Current heuristic (`avg_lift >= 3.0 → short_clip`) is rough. Should this map to the *currently surging format bucket* from `format_baselines` instead? That would require a `format_baselines` query in `compute_gap_queue`. Add as `--use-format-baselines` flag in follow-on.

3. **Vault gaps persistence:** Should gap queue be saved to sable.db as an artifact (like `save_diagnosis_artifact`)? Useful for tracking which gaps were acted on. Deferred — ship read-only first.

4. **Watchlist wire signal staleness:** Top-3 terms are from latest scan. If last scan was 3+ weeks ago, the "trending this week" framing is misleading. Should the prompt block include a "last scanned N days ago" caveat? Recommended: yes, add `last_scan_at` to the wire block header.

5. **Circular import check:** `sable/vault/gaps.py` imports from `sable/pulse/meta/db.py`. Need to verify this doesn't create a circular dependency with any existing pulse→vault import. Verify before wiring.

---

## Likely File Targets

| File | Change type |
|------|-------------|
| `sable/pulse/meta/db.py` | ADD `get_top_topic_signals()` function |
| `sable/vault/gaps.py` | CREATE new module: `VaultGap`, `compute_gap_queue()`, `render_gap_queue()` |
| `sable/commands/vault.py` | ADD `vault gaps` subcommand |
| `sable/write/generator.py` | ADD `watchlist_wire` param + `niche_wire_block` injection |
| `sable/commands/write.py` | ADD `--watchlist-wire` flag |
| `tests/vault/test_gaps.py` | CREATE new test file |
| `tests/pulse/meta/test_db_top_signals.py` | CREATE or extend with `test_get_top_topic_signals_*` tests |
| `tests/write/test_generator_watchlist.py` | CREATE or extend existing write generator tests |

**Files NOT to touch this session:**
- `sable/diagnose/runner.py` — F1 deferred; leave inline queries for now
- `sable/vault/search.py` — no changes needed
- `sable/pulse/meta/scanner.py` — no changes needed
- Any DB migration files — no schema changes

---

## Deferred Features (next sessions)

### F1: Diagnose→Action Pipeline (next priority)

Add `suggested_command: str | None = None` to `Finding` dataclass. Add `_map_finding_to_command(finding, handle, org)` helper that returns a runnable `sable` command string for each WARNING finding. Add rendering branch in `render_diagnosis`. Estimated: 50–80 LOC, 1 session.

Key mappings to implement:
- `Over-indexed on <format>` → `sable write @handle --format <alt_format> --topic <gap_topic>`
- `Niche surging format unused: <format>` → `sable write @handle --format <format>`
- `Stale inventory: N unposted notes` → `sable vault search @handle --available`
- `Execution gap on primary format` → `sable pulse meta scan --org <org>` (refresh data)
- `Topic gap: '<term>' trending but absent` → `sable write @handle --topic <term> --watchlist-wire`

### F3: Cross-Org Niche Delta (strategic, own session)

New `sable/pulse/meta/compare.py` module. `compare_orgs(orgs, period_days, meta_db_path)`. Cross-org `format_baselines` matrix. Temporal alignment requirement: filter to scans within shared lookback window. Output: delta table + actionable cross-pollination hypotheses.

### PM-3 Salvage: `--compare-org` on `sable vault gaps`

After vault gaps ships and has operator validation. Add `compare_org: Optional[str]` param to `compute_gap_queue`. Additional column in gap output: "also trending in <compare_org>: Y/N".

---

### Write-Pulse Freshness Loop (dropped at PM-1 finalist stage — should have been salvaged)

**What it is:** Pass the account's last 7 days of posts into the `generate_tweet_variants` prompt so the model knows what angles and topics have already been covered. Prevents duplicate-framing across back-to-back write sessions.

**Why it lost:** PM-1 chose Diagnose→Action as the finalist because it closes a more visible loop. The dismissal reasoning — "the write prompt already has vault context and format trend summary" — was weak. Those blocks don't convey recency; they convey inventory and niche trends. Recency is orthogonal.

**Why it should have been salvaged:** ~30 LOC, zero schema changes, benefits every `sable write` call unconditionally. The query already exists verbatim in `diagnose/runner.py:_audit_topic_freshness` (line 163 — same SELECT from `posts` by `account_handle`). This is the lowest LOC-to-value ratio of any deferred feature.

**Implementation:**
- Add `pulse_db_path: Optional[Path]` to `generate_tweet_variants` signature (same pattern as `meta_db_path` already there)
- Add `_load_recent_posts(handle, days, pulse_db_path) -> list[str]` — SELECT text FROM posts WHERE account_handle = ? ORDER BY posted_at DESC LIMIT 20
- Extract top terms (reuse or inline the Counter logic from `diagnose/runner.py:_audit_topic_freshness`)
- Inject as `recent_posts_block` in prompt, positioned before generation instructions:
  ```
  Recently posted topics/angles (avoid retreading these):
  • <top 5 terms or topic phrases from last 7 days>
  ```
- Flag: `--no-freshness` to opt out if operator wants unconstrained generation

**Files:** `sable/write/generator.py`, `sable/commands/write.py`
**Estimated LOC:** 30–40 net new
**Schema changes:** none
**Prerequisites:** none — `pulse.db` is already available at runtime

---

### Auto-Pulse Capture (deferred — requires scheduler infrastructure)

**What it is:** Scheduled `pulse track` that polls SocialData for new posts per account on a configurable interval (e.g. every 6 hours), inserts to `pulse.db`, and removes the requirement for the operator to manually remember to run `pulse track` after posting.

**Why it lost:** PM-2 chose Vault Gap Alert as the finalist because it's pure read-side with zero infrastructure. Auto-Pulse Capture requires a scheduler — either a daemon process, OS-level cron, or a `sable daemon` concept — none of which exist yet. The implementation surface is significantly larger.

**Why it matters:** Pulse tracking is currently 100% manual. If the operator forgets to track, the engagement data is gone — snapshots can only be taken while the post is relatively recent (Twitter engagement decays fast). Every missed track degrades the quality of `sable pulse report`, `sable pulse attribution`, and `sable diagnose`. The longer this stays manual, the more data quality erodes.

**Implementation approach (two options):**

Option A — OS cron (simpler, no daemon):
- `sable pulse capture --org ORG` — idempotent version of `pulse track` that fetches recent posts for all accounts in the roster for a given org, deduplicates against existing `posts` rows, inserts new ones
- Operator sets up `crontab` with `0 */6 * * * sable pulse capture --org psy`
- Document in `docs/PULSE_META.md`
- Estimated: 60–80 LOC + docs

Option B — Built-in scheduler (heavier):
- `sable daemon start` — long-running process with configurable capture intervals per org
- New config keys: `pulse.auto_capture_interval_hours`, `pulse.auto_capture_orgs`
- Requires process management (PID file, start/stop/status)
- Estimated: 200+ LOC, Phase 2 candidate

**Recommendation:** Ship Option A first. It's a single idempotent command the operator can cron themselves. Validates the workflow before building a daemon.

**Key deduplication requirement:** `pulse track` currently requires the operator to provide the tweet URL or ID. `sable pulse capture` must fetch recent posts from SocialData by account handle and use `posts.id` (tweet_id) as the dedup key — `INSERT OR IGNORE` semantics. The `posts` table already has `id TEXT PRIMARY KEY` which makes this safe.

**Files:** `sable/pulse/capture.py` (new), `sable/commands/pulse.py`
**Schema changes:** none
**Prerequisites:** verify SocialData timeline endpoint supports fetching recent posts by handle without a cursor (or reuse the cursor pattern from `scanner.py`)

---

### Operator Scorecard (deferred — Phase 2 CLI wrapper, Phase 2 web UI target)

**What it is:** A single `sable scorecard @handle` command that runs `diagnose`, `pulse attribution`, and `vault gaps` for an account and emits a unified ranked "here's what needs attention this week" brief. One command, one output, actionable priority order.

**Why it lost:** PM-3 chose Cross-Org Niche Delta as the finalist because it's more differentiated. Scorecard is mostly an orchestration wrapper — the intelligence already exists in the underlying tools. In a CLI context the operator can already run the three commands manually. The value proposition increases dramatically in a web UI context (Phase 2) where a dashboard renders it.

**Why it should be tracked:** The operator friction of running three commands and mentally synthesizing them is real. A unified brief with a ranked priority list — even in terminal output — reduces cognitive load in weekly account reviews. The underlying logic is already implemented; this is assembly work.

**Implementation:**

```python
# sable/scorecard/runner.py
def run_scorecard(handle, org, days, pulse_db_path, meta_db_path, vault_root, sable_db_path):
    diagnosis = run_diagnosis(handle, org, days, ...)       # existing
    attribution = compute_attribution(handle, days, ...)    # existing
    gaps = compute_gap_queue(org, vault_root, meta_db_path) # new (from vault gaps)

    # Merge into ranked action list
    actions = []
    for finding in diagnosis.findings:
        if finding.severity == FindingSeverity.WARNING:
            actions.append(ScorecardAction(priority=1, source="diagnose", message=finding.message, ...))
    for gap in gaps[:3]:
        actions.append(ScorecardAction(priority=2, source="vault_gaps", message=f"Create content on '{gap.term}'", ...))
    # ... attribution signals

    actions.sort(key=lambda a: a.priority)
    return ScorecardReport(handle=handle, org=org, actions=actions, ...)
```

**Prerequisite:** Vault Gap Alert must ship first (scorecard depends on `compute_gap_queue`). Diagnose→Action Pipeline (F1) should also ship first so scorecard can include suggested commands in the action list.

**Files:** `sable/scorecard/runner.py` (new), `sable/commands/scorecard.py` (new)
**Estimated LOC:** 100–150 (mostly rendering + merging logic)
**Schema changes:** none; optionally save to `sable.db` artifacts
