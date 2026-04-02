# Audit & Feature History

Chronological record of audit remediation rounds, feature deliveries, and QA fixes.
Moved here from `TODO.md` on 2026-03-29 to keep TODO focused on open items only.

---

## Audit Remediation Timeline

### AR-1 through AR-4 (2026-03-23)

Implemented. Two items deferred at that time (scanner cost attribute promotion
and Click-level CLI scan test) — both superseded by P2.

### AR-5 Maintainer Audit Refresh (2026-03-24)

Full codebase audit sourced from `codit.md`, refreshed against live code using
`AGENTS.md` / `docs/QA_WORKFLOW.md` / `docs/PROMPTS.md` / `docs/THREAT_MODEL.md` lens.

**AR-5 batch 1 fixes:**
- Brainrot loop cap (`min(..., 30)`)
- Whisper model caching
- Normalize.py zero-history `None`-lift semantics
- pulse/db `INSERT OR IGNORE` return value
- Magic constant comments
- `utcnow()` → `datetime.now(timezone.utc)` sweep

**AR-5 batch 1 follow-ups (all resolved 2026-03-24):**
- FOLLOW-UP-1: None arithmetic crash in `weighted_mean_lift()` / `assess_format_quality()`
- FOLLOW-UP-2: `tracker.py` insert_post bool captured
- FOLLOW-UP-3: Ruff 28 → 0 violations
- FOLLOW-UP-4: 9 mypy errors from AR5-18 resolved
- FOLLOW-UP-5: Missing batch 1 tests landed

**AR-5 maintainer-review fixes (2026-03-24):**
- `advise/stage1.py` pulse handle drift: `_norm_handle` extraction
- `posted_by` fatigue contract: `org` parameter threaded through recommender
- SableTracking source-time: `_build_entity_note()` uses `source_time`
- `vault/search.py` large-result path: tuple unwrap confirmed
- `clip/selector.py` first-stage batching: deterministic batched loop

**AR-5 batch 2 (2026-03-24):**
- `advise/generate.py` partial-write safety (temp→swap→restore)
- `advise/stage1.py` silent fallbacks → logger.warning
- `advise/generate.py` deterministic data caveats block
- `clip/selector.py` batch eval cap
- `clip/thumbnail.py` budget-exempt annotation
- `pulse/linker.py` stub clarified as permanent no-op
- `pulse/tracker.py` insert_post bool captured
- `pulse/meta/scanner.py` retry_with_backoff_async wired

### AR-5 Resolved Items

All items below resolved with tests and validation:

- **AR5-6** — Path traversal in `vault_dir()`: `_ORG_SLUG` regex guard
- **AR5-7** — Missing-entity guard in `execute_merge()`: `fetchone()` guard
- **AR5-8** — Failed author fetches: `_failed_authors` list on Scanner
- **AR5-9** — Tweet cursor string `max()`: cast to `int` with `.isdigit()` filter
- **AR5-10** — Deep-mode outsider tweets: resolved via transient scope
- **AR5-11** — Corrupted artifact cache: stale marking on decode error
- **AR5-12** — Entity sync pagination: `LIMIT 500 OFFSET n` loop
- **AR5-13** — FFmpeg subtitle path injection: validated
- **AR5-14** — Migration partial-apply risk: not actionable in Slopper (lives in SablePlatform)
- **AR5-15** — format_baseline duplicate rows: unique index
- **AR5-16** — has_link / classify boundary fix
- **AR5-17** — format_lift unreliable → returns `None`
- **AR5-18** — Zero-baseline lift deflation: `None` return
- **AR5-19** — String date fallback removed
- **AR5-20** — Analysis cost guard added
- **AR5-21** — Timezone sweep: `utcnow()` eliminated
- **AR5-22** — Budget `>=` at-cap: rejected (repo contract treats at-cap as blocked)
- **AR5-23** — Expired merge reconsideration: `reconsider_expired_merges()` added
- **AR5-24** — `INSERT OR IGNORE` silent drop: `rowcount` check
- **AR5-25** — Hardcoded API pricing: `sable/shared/pricing.py` with `compute_cost()`
- **AR5-26** — Whisper model cache
- **AR5-27** — Selector parse failure: retry + warning
- **AR5-28** — Brainrot loop cap

### P1–P5 Critical/High Fixes

- **P1** — Vault partial-sync window: `_PARTIAL_SYNC` extended to meta report phase
- **P2** — Truthful failed-scan rows: partial counts from live instance
- **P3** — Claude budget centralization: org-scoped advise/meta paths fully gated
- **P4** — Crash-safe writes: atomic temp→replace + fcntl lock
- **P5** — Silent fallback in reporting paths: all blocks hardened with `logger.warning`

### AR-6 QA Batch (2026-03-26)

- **QA-TWITTER-DATE-EMPTY-STRING** — `_parse_twitter_date("")` returns `None`
- **QA-ENTITY-NOTE-TAG-LOOP** — tag loop moved outside diagnostic run loop
- **QA-WRITE-COST-NOT-LOGGED** — `log_cost()` added after `call_claude_json()` in write
- **QA-ADVISE-WRONG-ERROR-MSG** — error message corrected in stage1.py

### Simplify Batch (2026-03-26)

- **SIMPLIFY-DEAD-ATOMIC-WRITE** — removed dead `_atomic_write()` from platform_sync
- **SIMPLIFY-HANDLE-NORM-TODO** — tracked TODO comment added for future consolidation

---

## Feature Delivery Timeline

### Stage 2: FEATURE-3 — `sable pulse account` (2026-03-24)

Account-level format lift report. 3 slices (data contract, niche integration, CLI).
35+ tests in `tests/pulse/test_account_report.py`.

### Stage 3: FEATURE-1 — `sable write` (2026-03-25)

Tweet writer with format trends, vault context, Claude generation.
3 slices (context assembly, generation core, CLI). 14 tests.

### Stage 3: FEATURE-2 — `sable score` (2026-03-25)

Hook scorer with pattern extraction and structural scoring.
18 tests (12 scorer + 6 write integration).

### Stage 4: FEATURE-4 — Viral Anatomy Archive (2026-03-25)

Auto-archive structural breakdowns of 10x+ lift tweets as vault notes.
3 slices. 14 tests in `tests/pulse/meta/test_anatomy.py`.

### Stage 4: FEATURE-6 — Watchlist Digest (2026-03-25)

Weekly curated report of structurally interesting watchlist posts.
3 slices. 6 tests in `tests/pulse/meta/test_digest.py`.

### Stage 5: FEATURE-8 — `sable diagnose` (2026-03-25)

Account health diagnosis: format portfolio, topic freshness, vault utilization,
cadence, engagement trend. Shipped with diagnose→action pipeline (suggested commands).

### Stage 6: FEATURE-9 — `sable pulse attribution` (2026-03-26)

Content attribution report: Sable-produced vs organic engagement breakdown.
12 tests (4 Slice A + 8 Slice B).

### Stage 7: FEATURE-7 — `sable calendar` (2026-03-26)

Content calendar planner. Spec rewritten ground-up with `posted_by` dicts,
`assembled_at`, `avg_total_lift`. 12 tests in `tests/calendar/test_planner.py`.

### Stage 8: Small Features (2026-03-26)

- **FEATURE-PULSE-META-SKIP-FRESH** — `--skip-if-fresh` flag + `pulse meta status`
- **FEATURE-ONBOARD-PREP** — `sable onboard --prep` stub-creator
- **FEATURE-ADVISE-EXPORT** — `sable advise --export` flag

### Stage 9: MIGRATION-006 (2026-03-26)

`discord_pulse_runs` table for Cult Doctor F-DM platform sync.
Schema v5 → v6. Write path owned by Cult Grader's `platform_sync.py`.

---

## Validation History

| Date | Tests | Ruff | Mypy |
|------|-------|------|------|
| 2026-03-24 (AR-5 batch 1) | 216 | 0 | 102 errors / 27 files |
| 2026-03-24 (FEATURE-3 Slice A) | 274 | 0 | 98 errors / 25 files |
| 2026-03-25 (FEATURE-8) | 359 | 0 | 0 |
| 2026-03-26 (FEATURE-9 + FEATURE-7) | 388 | 0 | 0 |
| 2026-03-26 (AR-6 QA + Simplify) | 401 | 3 E702 | 1 call-arg |
| 2026-03-26 (FEATURE-PULSE-META-SKIP-FRESH) | 414 | 3 E702 | 1 call-arg |
| 2026-03-29 | 557 | 3 E702 | 1 call-arg |
| 2026-03-31 (current) | 578 | 0 | 0 |

---

## Community Intelligence Feature Competition (2026-04-01)

Multi-agent feature proposal competition to source the next batch of community
intelligence features for Slopper. 5 proposer agents, 3 QA reviewer agents, 5
revision rounds, final evaluation and ranking.

### Evaluation criteria

| Criterion | Weight |
|-----------|--------|
| Client Revenue Impact | 25% |
| Operator Leverage | 20% |
| Strategic Differentiation | 20% |
| Feasibility | 15% |
| Community Understanding Depth | 12% |
| Cross-Tool Synergy | 8% |

### 15 original proposals

| # | Proposal | Agent | Disposition |
|---|----------|-------|-------------|
| 1 | Lexicon Tracker (`sable lexicon`) | Client PM | Merged → FEATURE-10 |
| 2 | Subsquad Radar (`sable squads`) | Client PM | Rejected (wrong repo) |
| 3 | Narrative Velocity (`sable narrative`) | Client PM | Retained → FEATURE-14 |
| 4 | Moment Finder | Community PM | Deferred (below median) |
| 5 | Vernacular Drift Detector | Community PM | Merged → FEATURE-10 |
| 6 | Community Echo | Community PM | Deferred (insufficient standalone value) |
| 7 | `sable lexicon` (operator variant) | Operator PM | Merged → FEATURE-10 |
| 8 | `sable pulse watchlist --leaders` (renamed → `--amplifiers`) | Operator PM | Merged → FEATURE-11 |
| 9 | `sable write --voice-check` | Operator PM | Retained → FEATURE-12 |
| 10 | Community Language Injection | Cross-repo PM | Retained → FEATURE-13 |
| 11 | Score Export to Lead Identifier | Cross-repo PM | Rejected (wrong integration pattern) |
| 12 | Bridge Node Content Amplification | Cross-repo PM | Merged → FEATURE-11 |
| 13 | Style Delta | Academic PM | Retained → FEATURE-15 |
| 14 | Bridge Score | Academic PM | Merged → FEATURE-11 (deferred phase) |
| 15 | Silence Gradient | Academic PM | Retained → FEATURE-16 |

### QA review summary

3 QA agents reviewed all proposals against `AGENTS.md` tier system:
- **ACCEPT:** 1 (Operator PM `--leaders`, later renamed `--amplifiers`)
- **REVISE:** 11 (most proposals required spec tightening)
- **REJECT:** 3 (Subsquad Radar, Score Export, Narrative Velocity initial version)

Narrative Velocity was restructured after rejection and re-entered successfully.
Subsquad Radar and Score Export were permanently withdrawn, leaving 13 proposals
in final evaluation.

### Final ranking

| Rank | Proposal | Agent | Score |
|------|----------|-------|-------|
| 1 | `--amplifiers` | Operator PM | 7.76 |
| 2 | Silence Gradient | Academic PM | 7.60 |
| 3 | Narrative Velocity | Client PM | 7.52 |
| 4 | Lexicon Tracker | Client PM | 7.47 |
| 5 | Style Delta | Academic PM | 7.40 |
| 6 | `--voice-check` | Operator PM | 7.22 |
| 7 | `sable lexicon` (operator) | Operator PM | 7.16 |
| — | *50th percentile line* | | |
| 8 | Bridge Score (phased) | Academic PM | 6.88 |
| 9 | Community Echo | Community PM | 6.72 |
| 10 | Community Language Injection | Cross-repo PM | 6.52 |
| 11 | Vernacular Drift Detector | Community PM | 6.36 |
| 12 | Moment Finder | Community PM | 5.88 |
| 13 | Bridge Node Amplification | Cross-repo PM | 5.76 |

Scores are weighted composites (0–10 scale) of the 6 criteria above. Per-criterion
breakdowns were not preserved — only composite scores were recorded.

### Agent leaderboard

| Agent | Points |
|-------|--------|
| Operator PM | +7 (winner — tiebreaker: highest single proposal) |
| Client PM | +7 |
| Academic/Tech PM | +6 |
| Cross-repo PM | −9 |
| Community Member PM | −11 |

### Consolidation rationale

Three overlap clusters identified and merged:

1. **Lexicon × 3 → FEATURE-10:** Client PM Lexicon Tracker (rank 4) + Operator PM
   `sable lexicon` (rank 7) + Community PM Vernacular Drift Detector (rank 11).
   Operator PM's design chosen as base (tighter scope, existing infrastructure).

2. **"Who matters" × 3 → FEATURE-11:** Operator PM `--amplifiers` (rank 1) +
   Academic PM Bridge Score (rank 8) + Cross-repo PM Bridge Node Amplification
   (rank 13). Graph work deferred; amplifiers + bridge-node advise section retained.

3. **Silence Gradient + CHURN → FEATURE-16:** Academic PM Silence Gradient (rank 2)
   produces compatible upstream data for CHURN-1, removing Platform dependency.

Top-6 pattern: all build on data already in meta.db/pulse.db, minimize or eliminate
Claude calls, deliver signal the operator can act on immediately.

### Consolidated feature set

| Feature | Merged From | Est. Tests |
|---------|------------|------------|
| FEATURE-10 Community Lexicon | 3 lexicon proposals | 18–22 |
| FEATURE-11 Amplifiers + Bridge Nodes | 3 "who matters" proposals | 14–18 |
| FEATURE-12 Voice Check | Standalone | 10–14 |
| FEATURE-13 Language Injection | Standalone (cross-repo) | 6–8 |
| FEATURE-14 Narrative Velocity | Standalone | 10–14 |
| FEATURE-15 Style Delta | Standalone | 12–16 |
| FEATURE-16 Silence Gradient | Standalone (feeds CHURN) | 16–20 |

Full specs and implementation plans in `TODO.md` § "Community Intelligence Features."

---

## External Audit Triage (Invalid For This Repo)

An external audit referencing `diagnostician.py`, `classifier.py`, `runner.py`,
`scoring.py`, `error_log.py`, `archive.py`, `subsquads.py`, `comparison.py`,
`report_internal.md.j2` was supplied. Those files do not exist in Slopper.

All findings (C1–C4, H1–H7, M1–M5) are not legitimate for this repo.

Useful meta-priorities carried over conceptually:
- Output trustworthiness ahead of feature work
- Cost burst / concurrency control as first-class hardening
- Secret leakage via logs/errors deserves scrutiny
- Partial-run recovery wired into operator workflows
