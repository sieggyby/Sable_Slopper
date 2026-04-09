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

### AUDIT-1–8 Full Remediation (2026-04-01 to 2026-04-02)

8 AUDIT items identified by maintainer review + Codex line-level analysis. Implemented
across 6 phases with adversarial QA subagent gating every commit. 5 QA rounds total.

- **AUDIT-1** (Tier 1): Secret handling — `config set` refuses secrets, `require_key()` points to env vars, `SECRET_ENV_MAP`, `redact_error()` in all CLI handlers
- **AUDIT-2** (Tier 1): Scanner validation — `_normalise_tweet()` rejects malformed payloads, `_safe_int()` coercion, core engagement type check
- **AUDIT-3** (Tier 1): Thin-sample gate — `MIN_SAMPLE = 5` in recommender, insufficiency return
- **AUDIT-4** (Tier 1): Small-vault search fallback — keyword_prescore fallback on Claude failure
- **AUDIT-5** (Tier 1/2): Org budget — `org_id` threaded through 7 Claude call sites, digest SQL fixed, `MAX_DIGEST_POSTS = 25`
- **AUDIT-6** (Tier 2): Maintainability — `SECRET_ENV_MAP` dedup, org_id patterns explicit
- **AUDIT-7** (Tier 2): Silent degradation — `logger.warning()` replaces silent `except: pass` in 4 modules
- **AUDIT-8** (Tier 3): Migration test — version derived from `_MIGRATIONS` source of truth

Two Codex hardening rounds followed (scanner core-field validation, vault enrich org threading).

### SocialData API Hardening (2026-04-02)

Audited all SocialData call sites against `SablePlatform/docs/SOCIALDATA_BEST_PRACTICES.md`.

- New `sable/shared/socialdata.py` centralized HTTP client (402 fatal, 429 exp backoff + jitter, 5xx retry, network error retry)
- Removed duplicate `_get_headers()` / `_BASE_URL` / direct `httpx` from 4 modules
- Fixed `suggest.py` endpoint path (`/twitter/tweet/` → `/twitter/tweets/`)
- 9 tests in `tests/shared/test_socialdata.py`

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
| 2026-03-31 | 578 | 0 | 0 |
| 2026-04-01 (AUDIT-1 partial) | 592 | 0 | 0 |
| 2026-04-02 (AUDIT-1–8 complete) | 620 | 0 | 0 |
| 2026-04-02 (Codex hardening) | 625 | 0 | 0 |
| 2026-04-02 (SocialData hardening) | 634 | 0 | 0 |
| 2026-04-03 (Community Intelligence) | 798 | 0 | 0 |
| 2026-04-03 (Phase 2 sable serve) | 828 | 0 | 0 |
| 2026-04-03 (FEATURE-3, CLIP-2, CLIP-3) | 850 | 0 | 0 |
| 2026-04-04 (P0-1 advise --org) | 859 | 0 | 0 |
| 2026-04-04 (P1-3 pulse sync_runs) | 865 | 0 | 0 |
| 2026-04-04 (P1-2 cost logging) | 876 | 0 | 0 |
| 2026-04-04 (P2-4 content outcomes) | 884 | 0 | 0 |
| 2026-04-04 (P2-6 content artifacts) | 891 | 0 | 0 |
| 2026-04-04 (P2-5 + P1-3 downstream verified in SablePlatform) | 891 | 0 | 0 |
| 2026-04-04 (cost observability + stale test schemas) | 899 | 0 | 0 |
| 2026-04-04 (brainrot theme matching) | 905 | 0 | 0 |
| 2026-04-04 (SocialData hardening: cost breakdown, logging, cursor cycling, checkpoint/resume) | 921 | 0 | 0 |
| 2026-04-04 (Production hardening Phase 1: SS-1, SS-3–SS-14) | 1008 | 0 | 2 pre-existing |
| 2026-04-04 (Production hardening Phase 2: SS-15–SS-21 + QA) | 1038 | 0 | 2 pre-existing |
| 2026-04-05 (AQ remediation batch: AQ-1–34 + QA) | 1091 | 0 | 0 |
| 2026-04-05 (Full repo audit: T1-1–T3-10) | 1155 | 0 | 0 |

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

### Community Intelligence Features (2026-04-03)

10 features shipped in one session: Amplifiers, Lexicon, Voice Check, Narrative Velocity,
Style Delta, Silence Gradient, Bridge Nodes, Community Language, Churn Playbook, Calendar
Churn Integration. 164 new tests. Adversarial QA gating per phase.

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

---

## Production Infrastructure (2026-04-04 suite audit)

### SS-1: CI/CD pipeline [S] ✓

**File:** `.github/workflows/ci.yml`

GitHub Actions on PR and push to main: `pip install -e ".[dev]"` → `ruff check .` → `mypy sable` → `pytest -q`. Cache pip deps.

### SS-3: API contract documentation [S] ✓

**File:** `docs/API_REFERENCE.md`

All 7 endpoints + /health documented with paths, params, response shapes, field types, and SableWeb integration notes.

---

## Production Hardening Phase 1 (2026-04-04 production audit)

12-dimension audit scored Slopper at 5.2/10. All items below completed 2026-04-04.

### P0 — Critical

- **SS-4: Anthropic client timeout + retry [M]** — `httpx.Timeout(300s, connect=10s)`, `max_retries=0` (SDK retry disabled), `_call_with_retry()` with 3 attempts, exp backoff, retry on 429/500/502/503. Tests added.
- **SS-5: Replicate timeout + retry [M]** — `predictions.create()` + polling with 300s timeout. Retry on 429/502/503. Prediction ID logged.
- **SS-6: Replicate cost logging [M]** — `_log_replicate_cost()` helper, `--org` flag on face CLI, org_id threaded through swap_image/swap_video. $0.01/image estimate. Frame count capped at 450 ($4.50 max per video).
- **SS-7: ElevenLabs cost logging [M]** — `_log_elevenlabs_cost()` helper, `org_id` added to TTSEngine interface and all implementations. $0.30/1K chars estimate. Cost logged after synthesis.
- **SS-8: DB transaction wrapping [S]** — All `conn.commit()` calls in generate.py (4 sites), artifacts.py, cli.py (org_create, org_set_config) wrapped in `with conn:` context manager.
- **SS-12: Advise brief cost logging [S]** — `log_cost(conn, org_id, "slopper_advise", cost_usd, model=model_name)` added after synthesis. Non-fatal on logging failure.

### P1 — High

- **SS-9: Test coverage for meme/ [L]** — Added tests/meme/test_templates.py, test_fonts.py, test_bank.py, test_meme_renderer.py, test_meme_cli.py. ~15 new tests.
- **SS-10: Test coverage for character_explainer/ [L]** — Added tests/character_explainer/ with test_config.py, test_tts_elevenlabs.py, test_tts_local.py, test_pipeline.py, test_cli.py, test_phonetics.py, test_subtitles.py. ~20 new tests.
- **SS-11: meta.db SCHEMA_VERSION drift [S]** — `SCHEMA_VERSION` bumped to 5. `migrate()` checks current vs expected, logs version transitions. `_MIGRATIONS` dict in place for future ALTER statements.
- **P1-2: budget_check parameter [M]** — Pre-existing. `budget_check: bool = True` already implemented in api.py and wired into all callers.
- **P2-4: Content performance outcomes [M]** — Pre-existing. `sable/pulse/outcomes.py` with `sync_content_outcomes()`.
- **P2-6: Vault content as platform artifacts [M]** — Pre-existing. `register_content_artifact()` in sable/platform/artifacts.py.

### P2 — Medium

- **SS-13: Schema versioning for pulse.db/meta.db [L]** — Both DBs have `schema_version` table, `_MIGRATIONS` dict, version check/update in `migrate()`. `sable db migrate` extended to cover all three DBs. Tests in test_schema_versioning.py.
- **SS-14: ElevenLabs retry logic [S]** — `_post_with_retry()` with 3 attempts, exp backoff on 429/500/502/503. Timeout retries included.

---

## Production Hardening Phase 2 (2026-04-04 multi-dimensional assessment)

### P0 — API Hardening

- **SS-15: Rate limiting on `sable serve` endpoints [M]** — In-process sliding-window rate limiter in `sable/serve/rate_limit.py`. Default 60 RPM, configurable via `serve.rate_limit_rpm`. Returns 429 + Retry-After. Path-param normalization prevents key-space inflation. Deque for O(1) eviction, max-keys cap (100). Middleware in `app.py` skips `/health`. 6 tests.
- **SS-16: `/health` endpoint dependency checks [S]** — `/health` now returns `{"status": "ok"|"degraded", "checks": {"pulse_db": bool, "meta_db": bool, "vault": bool}}`. Read-only checks (SQLite `?mode=ro`, no directory creation). HTTP 200 for both ok and degraded.
- **SS-17: Per-client token audit trail [M]** — `_resolve_token()` in `auth.py` checks named tokens (`serve.tokens`) first, falls back to legacy `serve.token`. Logs `client_name` on every authenticated request via `request.state.client_name`. `get_serve_cfg()` extracted as shared config resolver. 4 contract tests.

### P1 — Observability

- **SS-18: Structured JSON logging [M]** — `sable/shared/logging.py` with `StructuredFormatter` (JSON lines). `--json-log` flag on CLI main group. `configure_logging()` called unconditionally. Extra fields: `client_name`, `org_id`, `call_type`, `cost_usd`, `model`. 4 tests.
- **SS-19: Progress indicators for long operations [S]** — Rich progress bars on: (1) frame-by-frame video swap (`video.py`), (2) meta scan author iteration (`scanner.py`). TTY-only via shared `sable/shared/terminal.py:is_tty()`. Progress stopped cleanly on BalanceExhaustedError.

### P2 — Cross-Suite Integration

- **SS-20: Adopt TrackingMetadata contract from SablePlatform [S]** — `stage1.py` imports `TrackingMetadata` from `sable_platform.contracts.tracking`, validates parsed `metadata_json` via `model_validate()`, logs warning on unknown `schema_version`, uses typed field access. 5 integration tests in `tests/integration/test_tracking_metadata.py`.
- **SS-21: Cross-repo integration test contract [M]** — `tests/integration/test_contracts.py` with contract tests: health response shape (SS-16 spec), pulse performance/posting-log shapes, meta topics/baselines/watchlist shapes, vault inventory/search shapes, auth named + legacy + rejection, TrackingMetadata 17-field enumeration. ~15 tests.

### QA Audit Loop

2 adversarial QA rounds using AGENTS.md lens. Round 1 found 7 issues (2 Tier 1, 2 Tier 2, 3 Tier 3):
- Tier 1: Rate limiter unbounded memory (switched to deque + path normalization + max-keys cap), scanner progress leak on BalanceExhaustedError (added explicit stop before raise)
- Tier 2: Duplicated `_is_tty()` (extracted to `sable/shared/terminal.py`), duplicated serve config resolution (extracted `get_serve_cfg()` in auth.py)
- Tier 3: 3 minor doc/naming items

Round 2 confirmed all clean — 0 findings.

### Validation at completion: 1038 tests, ruff 0, mypy 2 (pre-existing)

---

## AQ Remediation Batch (2026-04-05)

Full audit remediation pass across 9 batches (AQ-1 through AQ-34). Adversarial QA
subagent gating with AGENTS.md lens. 2 critical, 3 high, 4 low findings caught and
fixed in QA round. Final validation: 1091 tests, ruff 0, mypy 0.

### Batch 1 — Silent Exception Hardening

- **AQ-17:** Retry helper intermediate failure logging — `sable/shared/retry.py` now logs `logger.debug` on each non-final retry attempt (sync and async paths)
- **AQ-18:** Clip selector eval retry fallback — `sable/clip/selector.py` logs `logger.warning` when batch eval retry exhausted, falls back to empty evaluations
- **AQ-19:** Serve health check bare excepts — `sable/serve/app.py` health probes log `logger.warning` with exception detail on pulse_db, meta_db, vault failures
- **AQ-20:** Advise cache date parse — `sable/advise/generate.py` catches `(ValueError, TypeError)` with `logger.warning` instead of silent pass
- **AQ-21:** Vault export frontmatter strip — `sable/vault/export.py` logs `logger.warning` on strip failure instead of silent pass
- **AQ-22:** Face track detection failure — `sable/clip/face_track.py` logs `logger.debug` on per-frame face detection failure

### Batch 2 — SocialData Cost Logging

- **AQ-6:** SocialData cost logging in vault suggest — `sable/vault/suggest.py:fetch_tweet_text()` now accepts `org` param, logs `$0.002` cost event with `call_type=socialdata_suggest` via `platform.cost.log_cost()`. `sable/vault/cli.py` threads org through.

### Batch 3 — Scanner Transaction Atomicity

- **AQ-9:** Batch upsert + atomic transactions — `sable/pulse/meta/db.py` gains `bulk_upsert_tweets()` operating on caller-provided connection for transaction scope. `sable/pulse/meta/scanner.py` accumulates author tweets into batch, wraps upsert + profile update + checkpoint in single `with conn:` block. Fixed `attrs_json` serialization bug: `isinstance(attrs, (list, dict))` in both `upsert_tweet()` and `bulk_upsert_tweets()`.

### Batch 4 — Doc Corrections

- **AQ-23:** `docs/COMMANDS.md` — Fixed serve port `8000` → `8420`
- **AQ-24:** `docs/ENV_VARS.md` — Documented both `nano` (roster) and `vi` (narrative) EDITOR fallbacks
- **AQ-25:** `docs/SCHEMA_INVENTORY.md` — Added `hook_pattern_cache` and `viral_anatomies` table definitions; fixed `scan_checkpoints` PRIMARY KEY and columns
- **AQ-26:** `docs/CONFIG_REFERENCE.md` — Added vault config keys section and `max_analysis_cost` under pulse_meta

### Batch 5 — New Test Coverage

- **AQ-13:** Scanner transaction tests — `tests/pulse/meta/test_scanner_balance_exhausted.py`: `bulk_upsert_tweets` return count, transaction rollback on failure, checkpoint persistence
- **AQ-14:** Serve auth success tests — `tests/serve/test_auth_success.py`: valid bearer token returns 200 on performance and posting-log endpoints
- **AQ-15:** FFmpeg failure tests — `tests/clip/test_ffmpeg_failure.py`: CalledProcessError, TimeoutExpired, FileNotFoundError all raise RuntimeError
- **AQ-16:** Brainrot exhaustion tests — `tests/clip/test_brainrot_exhaustion.py`: empty index, no matching energy, all files missing → returns None
- **AQ-28:** Calendar planner tests — `tests/calendar_plan/test_calendar_build.py`: Claude response parsing, empty data graceful degradation, invalid JSON fallback
- **AQ-29:** Pulse DB tests — `tests/pulse/test_pulse_db.py`: migrate, WAL mode, insert_post deduplication, handle normalization, thread columns
- **AQ-30:** Vault notes core tests — `tests/vault/test_notes_core.py`: read/write note, read_frontmatter, load_all_notes with valid/invalid/empty frontmatter
- **AQ-32:** Advise generate orchestration tests — `tests/advise/test_generate_orchestration.py`: dry_run, cache hit, unknown org, no roster entry, budget exceeded (degrade_mode=error)
- **AQ-34:** Face library tests — `tests/face/test_library.py`: add/get/remove reference, missing file, consent filter, deduplication

### QA Findings (caught by adversarial subagent)

- **C-1 (Critical):** `upsert_tweet()` line 327 still had `isinstance(attrs, list)` — dict attrs from `classify_tweet()` caused `sqlite3.ProgrammingError`. Fixed to `isinstance(attrs, (list, dict))`.
- **C-2 (Critical):** Test false confidence — `test_scanner_balance_exhausted` tested wrong function. Rewritten to validate `bulk_upsert_tweets` transactional integrity directly.
- **H-1 (High):** Scanner empty `raw_tweets` branch skipped checkpoint — caused unnecessary re-fetches on resume. Fixed by adding `checkpoint_author` call + progress advance.
- **H-2 (High):** AQ-20 used `logger.debug` instead of spec'd `logger.warning`. Fixed.
- **H-3 (High):** Missing budget-exceeded test path. Added test with `degrade_mode: "error"` config mock.
- **L-1 (Low):** `_row_to_tweet` bare `except Exception:` with no logging. Narrowed to `(json.JSONDecodeError, TypeError)` with warning.
- **L-2–L-4 (Low):** Minor doc/assertion tightening in test files.

### Validation at completion: 1091 tests, ruff 0, mypy 0

---

## Full Repo Audit Remediation (2026-04-05)

Multi-dimensional audit across test coverage, cost/resource risks, security, resilience,
schema drift, and output trustworthiness. 19 items identified and organized by AGENTS.md
tier system. All 19 unblocked items implemented with adversarial QA gating.

### Tier 1 — Breaks prod, leaks secrets, or burns money

- **T1-1 (Critical):** Replicate API key env leak — `sable/face/swapper.py` was setting
  `os.environ["REPLICATE_API_TOKEN"]` on every call. Fixed: `replicate.Client(api_token=...)`
  returns isolated client. Test: `tests/face/test_swapper.py` verifies env untouched.

- **T1-2 (Critical):** Strategy brief sample size disclosure — `sable/advise/stage1.py`
  rendered pulse trends without sample counts. Fixed: 4 sites patched (topic rendering
  includes author/mention counts, format rendering includes sample count, thin-sample
  caveats in generate.py, stage2 contract rule). Tests: `tests/advise/test_sample_disclosure.py`.

- **T1-3 (High):** Account format report confidence grade — `sable/pulse/account_report.py`
  showed lift from 2-post samples with no quality signal. Fixed: `account_confidence` field
  (A/B/C/D thresholds: 20/10/5) on `FormatLiftEntry`, grades rendered in output.

### Tier 2 — Breaks maintainers

- **T2-1:** pulse/meta/db.py tests — 14 tests in `tests/pulse/meta/test_meta_db.py` covering
  migrate, upsert, query, checkpoint, scan_run, format_baseline functions.
- **T2-2:** pulse/meta/scanner.py tests — 8 tests in `tests/pulse/meta/test_scanner.py` covering
  tweet normalization, budget cap, empty author, balance exhausted, checkpoint resume.
- **T2-3:** pulse/meta/cli.py tests — 5 tests in `tests/pulse/meta/test_meta_cli.py` covering
  scan dry-run, empty watchlist, status with/without data, help text.
- **T2-4:** ElevenLabs key loaded from `os.environ` instead of config —
  `sable/character_explainer/tts/elevenlabs.py` now uses `require_key("elevenlabs_api_key")`.
- **T2-5:** Vault notes TTL cache — `sable/vault/notes.py` gains module-level 5-min TTL cache
  with `invalidate_notes_cache()`. Tests: `tests/vault/test_notes_cache.py`.
- **T2-6:** face/optimize.py exception logging — 4 bare `except Exception` blocks now log
  `logger.debug` with error details.

### Tier 3 — Slows future work / test gaps

- **T3-1:** calendar/planner.py tests — 6 tests in `tests/calendar_planner/test_planner.py`
  covering parse, fallback, churn cap, render.
- **T3-2:** shared/ffmpeg.py tests — 6 tests in `tests/shared/test_ffmpeg.py` covering
  run() error handling and command construction for extract_clip/extract_audio.
- **T3-3:** onboard/orchestrator.py tests — 3 tests in `tests/onboard/test_orchestrator.py`
  covering YAML loading, missing file, malformed YAML.
- **T3-4:** vault/cli.py tests — 3 tests in `tests/vault/test_vault_cli.py` covering
  init, search, status commands.
- **T3-5:** platform/cli.py tests — 3 tests in `tests/platform/test_platform_cli.py`
  covering org list (empty/populated), db status.
- **T3-6:** Rate limiter FIFO eviction → LRU — `sable/serve/rate_limit.py` eviction now
  uses `min()` by last-request timestamp instead of insertion order.
- **T3-7:** Global exception handler — `sable/serve/app.py` gains
  `@app.exception_handler(Exception)` returning generic 500 with logged traceback.
- **T3-8:** Write generator anatomy sample count — prompt block now includes
  `{len(patterns)} highest-performing posts` with caveat language.
- **T3-9:** Narrative velocity min sample guard — `sable/narrative/tracker.py` returns
  `None` velocity when `unique_authors < 3` or `days_since < 2`. Model field updated
  to `Optional[float]`.
- **T3-10:** Lexicon scanner metadata return — `sable/lexicon/scanner.py` return type
  changed from `list[dict]` to `tuple[list[dict], dict]` with corpus_tweets,
  corpus_authors, below_threshold metadata. CLI caller updated.

### QA Findings

Adversarial QA subagent reviewed all 19 implementations. No Tier 1 or Tier 2 findings.

### Validation at completion: 1155 tests, ruff 0, mypy 0

---

## Codit Audit Remediation (2026-04-05)

Full remediation of `codit.md` (Codex audit dated 2026-03-23). All 5 critical, 7 high,
and 12 medium findings resolved. Three adversarial QA passes confirmed zero remaining findings.

### Key changes:
- **CRIT-1:** `vault/platform_sync.py` — pulse report staging moved before Phase B renames,
  closing the partial-sync window. `_cleanup_temps()` helper extracted. TOCTOU fix on pulse
  source read.
- **MED-5:** `vault/search.py` — `SearchResult.degraded` field signals keyword-fallback results.
- **MED-10:** `pulse/meta/db.py` — `upsert_format_baseline` renamed to `insert_format_baseline`,
  same-second duplicate prevention added. Backwards-compat alias retained.
- **HIGH-5:** `pulse/meta/cli.py` — deep-mode outsider results now explicitly marked transient
  in console output.

Most findings (CRIT-2 through CRIT-5, HIGH-1 through HIGH-4, HIGH-6, HIGH-7, MED-1 through
MED-4, MED-6 through MED-9, MED-11, MED-12) had already been resolved during prior AR-5
remediation passes.

### Validation at completion: 1157 tests, ruff 0, mypy 0

---

## Completed Items Moved from TODO.md (2026-04-08)

The following completed items were removed from `TODO.md` to reduce stale bulk.
Full details for each are in `docs/IMPLEMENTATION_LOG.md`.

- **SS-SEC:** `.env` security verified — never committed, `.gitignore` covers it, `deploy/.env.example` exists. (2026-04-06)
- **SS-VPS:** VPS deployment scripts audited — yt-dlp added, log rotation configured, smoke test created. (2026-04-06)
- **SS-WEEKLY-ALL:** `sable weekly run --all` verified — `discover_orgs()` iterates all active roster accounts, 19 tests. (2026-04-06)
- **SS-3:** Weekly automation shipped — `sable weekly run` (5-step pipeline), `sable clip review`, cost-forecast endpoint, 34 tests. (2026-04-06)
- **SS-2:** `sable serve` shipped — FastAPI on Hetzner CX21 VPS, Cloudflare tunnel, systemd services. (2026-04-06)
- **Phase 2 RBAC:** `vault/permissions.py` + org-scoping shipped. (2026-04-05)
- **Phase 3 VPS:** Hetzner CX21 deployed, `sable-weekly.timer` running. (2026-04-06)
- **Full Repo Audit (T1-1 through T3-10):** All 19 items closed 2026-04-05.
- **Codit Audit Remediation (CRIT/HIGH/MED):** All findings closed 2026-04-05.

---

## Named Params Conversion for sable.db Queries (2026-04-08)

Converted all `?`-positional SQL params to `:named` params with dict args in Slopper's
two files that have direct `conn.execute()` calls targeting `sable.db`:

- `sable/platform/artifacts.py` — 1 INSERT query
- `sable/platform/cli.py` — 14 queries (SELECT, INSERT, UPDATE)

Mechanical conversion only — no SQL logic changes. Forward-compat for when SablePlatform's
`CompatConnection` retires `?`-positional support. `pulse.db` and `meta.db` queries via
direct `sqlite3.connect()` were not touched (out of scope).

Added `TODO` comment on `datetime('now')` SQLite-specific call in `org_set_config`.

Adversarial QA audit (AGENTS.md framework): clean — no missed conversions, no scope creep.

### Validation: 1117 passed, 96 failed (pre-existing upstream), ruff 0, mypy 0
