# TODO

---

## Strategic Direction (as of 2026-03-25)

Slopper is the content production engine. In the current 6–12 month services phase, the focus is on delivering high-quality content for existing and incoming clients — not building a general-purpose social media product.

**Current and incoming clients needing Slopper profiles:**
- **TIG Foundation** — active (profile should exist or be created)
- **Multisynq** — pseudo-client; profile prep useful
- **PSY Protocol** — best current lead; prepare `~/.sable/profiles/@psy_handle/` in advance so onboarding is fast when signed
- **Flow L1** — next lead after PSY; profile prep when outreach begins

**Phase 2 (local web UI) remains deferred.** It is not needed for the services phase — CLI is sufficient for Sable operators. Revisit when client volume makes CLI management impractical (roughly 5+ active accounts).

**What not to build:** Any multi-tenant, self-serve, or externally accessible content product. Slopper stays internal tooling for this phase.

---

## Audit Remediation — AR-5

Sourced from `codit.md` full-codebase audit, then refreshed against the live code on
2026-03-24 using the `AGENTS.md` / `docs/QA_WORKFLOW.md` / `docs/PROMPTS.md` /
`docs/THREAT_MODEL.md` review lens.

This file now mixes:
- the current open queue that still matters
- historical AR-5 notes kept for context
- follow-up validation notes from the first implementation batch

Do not assume every item below is still open. Use the **Current Open Queue** first.

Validation snapshot (current):
- `./.venv/bin/python -m pytest -q` → `401 passed`
- `./.venv/bin/ruff check .` → 3 pre-existing E702 violations in `tests/pulse/test_attribution.py` (semicolons); no new violations
- `./.venv/bin/mypy sable` → 1 pre-existing `call-arg` error in `sable/pulse/cli.py`; no new errors

Historical note kept for trend only:
- after FEATURE-3 Slice A (2026-03-24): `274 passed / 0 ruff / 98 mypy in 25 files`
- 2026-03-24 maintainer audit refresh: `216 passed / 0 ruff / 102 mypy in 27 files`
- earlier 2026-03-24 reconciliation pass was `205 passed / 28 ruff violations / 96 mypy errors`
- after FEATURE-8 (2026-03-25): `359 passed / 0 ruff / 0 mypy`
- after FEATURE-9 + FEATURE-7 (2026-03-26): `388 passed / 0 ruff / 0 mypy`
- after QA-TWITTER-DATE-EMPTY-STRING (2026-03-26): `399 passed / 0 ruff / 0 mypy`
- after AR-6 QA batch + AR-6 Simplify batch (2026-03-26): `401 passed` / 3 pre-existing ruff E702 / 1 pre-existing mypy call-arg
- after FEATURE-PULSE-META-SKIP-FRESH marked done (2026-03-26): `414 passed` / 3 pre-existing ruff E702 / 1 pre-existing mypy call-arg

---

## Codebase Quality Accounting (Current)

### What is actually healthy

- Core test suite is green: `401` tests passing.
- Several former criticals are now genuinely fixed:
  - `pulse/meta` zero-history `None`-lift aggregation hardening
  - vault `_PARTIAL_SYNC` coverage through the pulse report step
  - org-aware Claude wrapper rollout for advise synthesis + pulse/meta analysis
  - atomic roster + vault note writes
  - org slug validation in `vault_dir()`
  - merge missing-entity guards
  - truthful failed-scan row persistence
  - entity pagination in platform vault sync
  - deep-mode outsider scope clarified as transient
  - numeric tweet cursor handling
  - Whisper model caching
  - brainrot loop cap
  - timezone sweep away from `utcnow()`
  - `advise/stage1.py` pulse handle contract — both queries now use `@handle` form
  - `recommender.py` / `cli.py` `posted_by` fatigue — `org` now threaded from CLI through `build_recommendations()` to `compute_priority()`; fatigue fires correctly on real vault notes
  - `vault/platform_sync.py` `_build_entity_note()` — `source_time` used for filter and display (not `created_at`)
  - `vault/search.py` large-result path — `(note, score)` tuples unwrapped before `claude_rank()` (line 60)
  - `clip/selector.py` first-stage batching — hard truncation replaced with deterministic batched loop + `_dedup_selections()`

### What is still structurally weak

- AI spend / prompt-size controls are still uneven outside the org-gated advise/meta flows.
  - non-org Claude call sites remain intentionally budget-exempt, so spend is still not observable
    in a single place for content-generation flows
- tests and types are not yet aligned with the real contracts.
  - some tests still encode stale producer/consumer schemas
  - lint is green, and mypy is clean: `0` errors

**Resolved in AR-5 maintainer-review fixes + follow-up (2026-03-24):**
- `advise/stage1.py` freshness query: extracted `_norm_handle`; both pulse.db queries now use normalized `@handle` form
- `pulse/meta/recommender.py` `compute_priority()`: added `org` parameter; removed silent `content.get("org", "")` fallback that always returned `""` from real vault notes — caller must supply org explicitly
- `pulse/meta/recommender.py` `build_recommendations()`: added `org` parameter, threaded through to `compute_priority()`
- `pulse/meta/cli.py` `_run_analysis()`: added `org=org` to `build_recommendations()` call — fatigue now fires on live CLI path
- `vault/platform_sync.py` `_build_entity_note()`: filter and display now use `source_time` (with `created_at` fallback) instead of `created_at` alone
- `sable/clip/selector.py`: replaced hard truncation at `_MAX_WINDOW_CONTEXT` with deterministic batched loop; added `_dedup_selections()` to merge overlapping window spans across batches
- 7 new tests added (stage1 handle normalization, recommender org parameter × 2, recommender `build_recommendations` integration, platform_sync source_time × 2, selector batch count and index offset × 2, `_run_analysis()` CLI boundary regression)
- Validation: `233 passed · 0 ruff · 101 mypy errors in 26 files` (was 226 passed / 0 ruff / 101 mypy)

**Resolved in AR-5 batch 2 (2026-03-24):**
- `advise/generate.py` partial-write safety: temp→swap→restore pattern implemented
- `advise/stage1.py` silent fallbacks: all 3 bare-except blocks now emit logger.warning
- `advise/generate.py` data caveats block: deterministic `## Data Caveats` prepended when data is stale/degraded
- `sable/clip/selector.py` batch eval cap: `_MAX_EVAL_BATCH = 20` + recursive batching + retry_with_backoff
- `sable/clip/thumbnail.py` budget-exempt annotation added
- `sable/pulse/linker.py` stub clarified: docstring now explicit that this is a permanent no-op
- `sable/pulse/tracker.py` insert_post bool captured and counted
- `sable/pulse/meta/scanner.py` retry_with_backoff_async wired into fetch loop
- Ruff lint baseline: 28 violations → 0 (all F541, F841, E701, F811 cleared)
- 11 new tests added covering partial-write recovery, data caveats, stage1 warning blocks, transcribe cache, brainrot cap, pulse/db duplicate insert, zero-history aggregation

### How to sequence work

1. Fix cross-tool contract bugs and output-trustworthiness defects before any feature work.
2. Align tests with the live producer/consumer schemas while fixing those bugs.
3. Tighten prompt-size / spend controls and run the focused secret-scrubbing audit.
4. Keep touched-file mypy debt from spreading; reduce it in the glue code you touch.
5. Only then start staged feature work in the order defined later in this file.

---

## External Audit Triage (Invalid For This Repo)

An external audit was supplied referencing modules such as:
- `diagnostician.py`
- `classifier.py`
- `runner.py`
- `scoring.py`
- `error_log.py`
- `archive.py`
- `subsquads.py`
- `comparison.py`
- `report_internal.md.j2`

Those files and symbols do **not** exist in this Slopper repo. `rg` against the workspace
confirms the findings are from a different project/codebase.

### Verdict on those findings

- `C1` through `C4`: not legitimate for this repo as stated
- `H1` through `H7`: not legitimate for this repo as stated
- `M1` through `M5`: not legitimate for this repo as stated

Do **not** create code tasks in Slopper that pretend these exact defects are present here.

### Useful signal to carry over conceptually

Even though the file-level findings are invalid here, the meta-priorities are aligned with
this repo's real threat model:
- output trustworthiness should stay ahead of feature work
- cost burst / concurrency control should be treated as a first-class hardening area
- secret leakage via logs/errors deserves explicit scrutiny
- partial-run / partial-output recovery should be wired into real operator workflows, not
  just helper utilities

Those themes are already reflected in the Current Open Queue and should remain above any
feature/backlog work unless a new live code inspection proves otherwise.

---

## Current Open Queue (2026-03-24 Maintainer Audit Refresh)

This section supersedes the older queue ordering. Treat it as the source of truth for Claude.

**Execution contract for Claude:**
- **Stage 0 is fully closed** (items 1–4 all resolved with tests; see "Recently resolved" below)
- **Stage 1 item 5 is closed** (selector first-stage batching resolved)
- **FEATURE-3 (`sable pulse account`) is fully shipped** — all 3 slices landed 2026-03-24 ahead of the item 6/7 gate; items 6 and 7 remain open
- **FEATURE-1 (`sable write`) fully shipped** — Slices A, B, C complete (2026-03-25)
- **Items 6, 7, 8 closed (2026-03-25). FEATURE-2 unblocked.**
- do one queue item per patch set where practical
- add failing tests first for the specific contract or edge case being fixed
- rerun repo-wide validation after each patch set:
  - `./.venv/bin/python -m pytest -q`
  - `./.venv/bin/ruff check .`
  - `./.venv/bin/mypy sable`
- update this TODO entry after each completed patch with exact validation results

**Recently resolved; keep closed unless they regress:**
- `pulse/meta` downstream `None`-lift crash in `weighted_mean_lift()` / `assess_format_quality()`
- vault pulse-report partial-sync gap in `platform_sync.py`
- `advise/stage2.py` wrapper bypass and `pulse/meta/analyzer.py` missing `org_id`
- `advise/generate.py` partial-write safety
- `advise/stage1.py` silent parse fallbacks + pulse handle contract (`@handle` normalization in both queries)
- `advise/generate.py` deterministic data caveats block
- `tracker.py` insert_post bool not captured
- repo-wide ruff baseline: `28` violations → `0`
- missing batch-2 regression tests (all landed)
- **Stage 0 item 1** — `advise/stage1.py` pulse handle drift: both queries now use `_norm_handle` (`@handle` form); tests updated to use `@alice`; `test_pulse_last_track_populates_for_at_handle` added
- **Stage 0 item 2** — `posted_by` fatigue contract: `compute_priority()` now takes `org` parameter; `build_recommendations()` threads it through; `pulse/meta/cli.py` `_run_analysis()` passes `org=org`; recommender no longer reads stale `content.get(“org”, “”)`; `has_similar_recent_post` and `get_days_since_last_post` already used `posted_at` correctly; integration test `test_build_recommendations_threads_org_for_fatigue` added
- **Stage 0 item 3** — SableTracking source-time local fixes: `vault/platform_sync.py` `_build_entity_note()` now uses `source_time` for filter+display (with `created_at` fallback); `test_build_entity_note_*` tests added; cross-repo contract confirmation for `sync_to_platform()` sync/async and `posted_at` canonicity still pending (tracked in “structurally weak” section above)
- **Stage 0 item 4** — `vault/search.py` large-result path: `top50_notes` already unwraps tuples at line 60 — confirmed fixed
- **Stage 1 item 5** — `clip/selector.py` first-stage batching: hard truncation replaced with batched loop + `_dedup_selections()`; tests added for batch count and index offset

### Stage 1 — hardening and debt reduction before feature work

### 6. MED · Explicit log/error secret scrubbing audit ✓ **Done**

No confirmed live key leak found in the current audit, but this remains a valid hardening task.
Do it **after** the correctness blockers above and **before** shipping new features.

**Scope:**
- search explicit exception logging / persisted error paths in platform, vault, advise,
  pulse-meta, and any future web/UI entrypoints
- confirm upstream exceptions cannot persist config dicts, auth headers, or client reprs
- add a single redaction helper if any persistence path is found to be risky

**Tests / checks:**
- synthetic exception containing `ANTHROPIC_API_KEY=test-secret` is redacted before persistence
- no generated artifact or persisted log path stores key-looking strings

### 7. MED · Touched-file mypy cleanup ✓ **Done**

Repo-wide state at time this item closed (historical — see validation snapshot at top of file):
- `pytest` → `304 passed`
- `ruff` → `0` violations
- `mypy` → `97` errors in `24` files (jobs.py fix reduced touched-file errors to 0; baseline unchanged)

**Required discipline for Claude:**
- no patch should claim “clean” unless the repo-wide commands above support that claim
- reduce mypy errors only in files touched during items 6–7 (do not touch-and-type random modules)
- priority files if touched:
  - `sable/pulse/meta/cli.py` (touched by CLI regression test)
  - `sable/clip/selector.py` (touched by selector batching)
  - any new helper introduced during item 6 secret scrubbing

### 8. LOW · `pulse/linker.py::auto_link_posts()` is still a feature-shaped stub ✓ **Done**

**File:** `sable/pulse/linker.py`

`auto_link_posts()` still looks like a live auto-linker while behaving as a permanent no-op.
This is not urgent, but it is misleading surface area.

**Fix options:**
- keep it explicit no-op and document/test that state
- or implement a truly minimal linker only after the bugfix stages above are done

**Tests:**
- if kept as placeholder, test and docs should say it is intentionally no-op
- if implemented later, add false-positive / threshold / duplicate tests before exposing it

### Stage 2 — Targeted QA fixes (AR-6 batch, 2026-03-26)

Items below are sourced from a focused live-code audit. All four are independent; they can
be sequenced in priority order. Do one per patch set; run full validation after each.

### QA-TWITTER-DATE-EMPTY-STRING · HIGH · `pulse/meta/scanner.py` ✓ **Done**

**What:** `_parse_twitter_date()` returns `datetime.now(timezone.utc).isoformat()` when
`date_str` is an empty string instead of returning `None`.

**Why:** The downstream filter at line 138 (`if posted_at is None: continue`) is the guard
against bad records. An empty `created_at` bypasses this guard entirely — the tweet is
treated as timestamped right now, corrupting temporal analytics (freshness calculations,
date-window filters, and all downstream time-series queries).

**Files:** `sable/pulse/meta/scanner.py` — `_parse_twitter_date` function (~lines 84–87)

**Fix:** Replace:
```python
if not date_str:
    return datetime.now(timezone.utc).isoformat()
```
with:
```python
if not date_str:
    return None
```
Verify all callers handle `None` correctly. The filter at line 138 already does. Run a
grep for other call sites before closing.

**Expected outcome:** Empty `created_at` tweets are skipped at the line-138 guard, never
treated as "posted just now."

**Tests:** Add a unit test: `_parse_twitter_date("")` returns `None` (not a datetime string).
Add a second test: `_parse_twitter_date(None)` also returns `None`. Confirm the line-138
guard test path is covered.

**Gotchas:** Do NOT change behavior for well-formed date strings. Only the empty-string
and `None` branches are affected.

---

### QA-ENTITY-NOTE-TAG-LOOP · MED · `vault/platform_sync.py` ✓ **Done**

**What:** In `_build_entity_note()`, the `for t in tags:` loop that emits tag-based
mention lines is nested inside the `for run in diag_runs:` loop. One tag-mention line is
emitted per diagnostic run per tag, not once per tag.

**Why:** Structural logic error. Tags describe the entity's current state and are
independent of run history. An entity with 2 tags and 3 diagnostic runs currently produces
6 tag-mention lines (3 runs × 2 tags). The correct output is 2 lines.

**Files:** `sable/vault/platform_sync.py` — `_build_entity_note` function (~lines 155–162)

**Fix:** Move the `for t in tags:` block entirely outside (after) the `for run in
diag_runs:` loop. No other logic changes needed.

**Expected outcome:** An entity with 2 tags and 3 diagnostic runs produces exactly 2
tag-mention lines.

**Tests:** Add a unit test: build an entity note with 2 tags and 3 diagnostic runs. Assert
the rendered note contains exactly 2 tag-mention lines (count occurrences of the tag-mention
pattern in the output string). The test should fail before the fix and pass after.

**Gotchas:** Read `_build_entity_note` in full before editing — confirm which indentation
block the tag loop currently lives in. Do not disturb the `for run in diag_runs:` loop body.

---

### QA-WRITE-COST-NOT-LOGGED · MED · `write/generator.py` ✓ Done

**What:** `sable/write/generator.py` calls `call_claude_json()` with
`call_type="write_variants"` but never calls `log_cost()` afterward. Write pipeline spend
is invisible in `sable.db` `cost_events`.

**Why:** `AGENTS.md` mandates cost logging for all org-scoped Claude API calls. The write
pipeline is currently a blind spot in budget tracking — operators cannot see what `sable
write` is costing them.

**Files:** `sable/write/generator.py` — after the `call_claude_json()` call (~line 236)

**Fix:** Add `log_cost(org_id=resolved_org, call_type="write_variants", tokens=response.usage)`
immediately after the Claude call. `resolved_org` should already be in scope. Also add
`check_budget(resolved_org)` before the call if `resolved_org` is available at that point
(matches the pattern used in `advise/stage2.py` and `pulse/meta/analyzer.py`).

**Expected outcome:** After `sable write @handle --topic foo`, a row appears in
`cost_events` with `call_type="write_variants"` and the correct org and token counts.

**Tests:** Add a test: mock `call_claude_json` to return a valid response with
`usage.input_tokens=100, usage.output_tokens=50`. Assert `log_cost` is called once with
`org_id=resolved_org` and `call_type="write_variants"`. Use an in-memory sable.db and
verify the `cost_events` row exists.

**Gotchas:** `response.usage` shape must match what `log_cost()` expects — check the
`call_claude_json` return type and `log_cost` signature before wiring. Do not break the
existing write tests.

**✓ Done (2026-03-26):** Cost logging is wired via the `call_claude_with_usage()` wrapper.
`generate_tweet_variants()` passes `org_id` + `call_type="write_variants"` through
`call_claude_json()` → `call_claude()` → `call_claude_with_usage()`, which calls
`log_cost()` internally. No explicit `log_cost()` call needed in `generator.py`.
Confirmed by `test_write_variants_logs_cost_to_sable_db` in `tests/write/test_generator.py`.

---

### QA-ADVISE-WRONG-ERROR-MSG · LOW · `advise/stage1.py` ✓ **Done**

**What:** The `except` block handling the `content_items` DB query (~line 289) logs
`"sable.db entity read failed: %s"` — but this block is handling a `content_items` query,
not an entity read.

**Why:** Misleading error message. An operator diagnosing a `content_items` failure would
search logs for "entity read" and find nothing relevant.

**Files:** `sable/advise/stage1.py` — except block ~line 289

**Fix:** Change the log message from `"sable.db entity read failed: %s"` to
`"sable.db content_items read failed: %s"`. One-line change.

**Expected outcome:** The correct message appears in logs when the `content_items` query
fails.

**Tests:** No new test required unless a test already covers this except branch. If the
nearby except-block tests from AR-5 batch 2 cover this path, update their assertion strings
to match the new message.

**Gotchas:** Read the block in context first to confirm this is specifically the
`content_items` except block and not a different one with a similar message. Do not touch
the entity-read except blocks above it.

---

### Feature Gate

No `FEATURE-*` work begins until:
1. Stage 0 items are closed with tests. ✓ **Done** — all four items resolved.
2. Stage 1 item 5 is closed. ✓ **Done** — selector first-stage batching resolved.
3. Stage 1 items 6 and 7 are closed. ✓ **Done.** (secret scrubbing audit + mypy debt pass, 2026-03-25). FEATURE-2 unblocked.
4. Repo-wide validation still reads `pytest green / ruff 0 / mypy no worse than current baseline`.

### Resolved / Obsolete From The Original AR-5 Draft

These no longer belong in the active queue unless they regress:
- `P1` vault partial-sync coverage through the pulse report step: landed
- `P3` core Claude wrapper rollout for advise + pulse/meta org-scoped calls: landed
- `P2` truthful failed-scan rows: landed
- `P4` crash-safe roster + vault note writes: landed
- `AR5-6` org slug validation in `vault_dir()`: landed
- `AR5-7` missing-entity merge guards: landed
- `AR5-8` failed author fetch tracking: landed
- `AR5-9` numeric tweet cursor max: landed
- `AR5-10` smaller-scope outsider behavior chosen: outsider results are now explicitly transient
- `AR5-12` entity pagination in platform sync: landed
- `AR5-13` FFmpeg subtitle path validation + guarded call sites: landed
- `AR5-15` format baseline de-dupe + unique index: landed
- `AR5-16` `has_link` / classify boundary fix: landed
- `AR5-17` unreliable `format_lift` now returns `None`: landed
- `AR5-18` zero-history `None`-lift semantics + downstream aggregation hardening: landed
- `AR5-19` string date fallback removed: landed
- `AR5-20` analysis cost guard: landed
- `AR5-21` timezone sweep: landed
- `AR5-22` exact-cap blocking: obsolete as a TODO item; current `>=` behavior matches repo policy
- `AR5-23` expired merge reconsideration: landed
- `AR5-24` `insert_post()` duplicate visibility: landed, but caller adoption remains open
- `AR5-26` Whisper model cache: landed
- `AR5-27` selector parse failure retry + warning path: landed
- `AR5-28` brainrot loop cap: landed
- cross-cutting `utcnow()` sweep and magic-constant comments: landed

---

### P1 · Close vault partial-sync window — `vault/platform_sync.py` (CRIT-1) — RESOLVED

**Status:** Landed in current workspace. `_PARTIAL_SYNC` coverage now starts at phase-B
renames and includes the pulse report step. Keep the notes below as historical context for
why the fix mattered.

**File:** `sable/vault/platform_sync.py`, lines 432–479
**Issue (historical):** The sentinel patch reduced the risk but did not eliminate it.
Phase-B renames happened before the pulse report step, and the pulse report step ran before
the sentinel-protected DB delete/insert/commit block. A crash in that gap left the
filesystem ahead of the DB with no `_PARTIAL_SYNC` marker.

**Fix strategy — keep FS-before-DB ordering, add sentinel on failure:**
1. Move `meta_report.md` into phase A: write it to a temp path and append it to `temp_writes`
   before *any* phase-B rename fires.
2. Keep the FS-before-DB ordering.
3. Ensure every failure after the first phase-B rename writes `_PARTIAL_SYNC`, including a
   failure in the pulse report copy step.

Note: moving `commit()` before `os.replace()` would flip the inconsistency (DB ahead of FS)
and is not the right direction.

**Tests:**
- inject failure after the last phase-B rename but before `conn.commit()`
- inject failure in the `meta_report.md` write/copy step after phase-B renames
- assert `_PARTIAL_SYNC` exists and old artifact rows are still present in both cases

---

### P2 · Truthful failed-scan rows — `pulse/meta/scanner.py` (HIGH-1) — RESOLVED

**Files:** `sable/pulse/meta/scanner.py`, `sable/pulse/meta/cli.py`, `sable/pulse/meta/db.py`
**Issue (historical):** On generic scan exception, `tweets_new` and `estimated_cost` in `scan_runs` were
saved as 0 even when partial work completed. (`tweets_collected` was fixed in AR-3; these
two were deferred — this supersedes that deferred item.)

**Fix:**
```python
# In Scanner.__init__:
self._estimated_cost: float = 0.0
self._tweets_new: int = 0
# Increment in the per-author loop wherever local vars are updated today.

# In cli.py exception handler, before fail_scan_run():
# tweets_collected is already derived from the DB via get_tweets_for_scan() — keep that.
# Only tweets_new and estimated_cost need the promoted instance attributes:
partial = meta_db.get_tweets_for_scan(scan_id, org)
meta_db.fail_scan_run(
    scan_id,
    str(e),
    tweets_collected=len(partial),
    tweets_new=scanner._tweets_new,
    estimated_cost=scanner._estimated_cost,
)
```

**Test:** Mid-scan exception after 1+ successful fetches. Assert `scan_runs` row has
non-zero `estimated_cost` and correct partial `tweets_new`.

---

### P3 · Finish Claude budget/cost centralization — `shared/api.py` rollout follow-up (HIGH-2) — RESOLVED FOR ORG-SCOPED ADVISE / PULSE-META PATHS

**Files:** `sable/shared/api.py`, `sable/advise/stage2.py`, `sable/pulse/meta/analyzer.py`

**Status:** Landed for the org-scoped advise synthesis and pulse-meta analysis paths.
Remaining non-org exemption-comment consistency is tracked in Current Open Queue item 6.

**Issue (historical):** The shared wrapper existed, but rollout was incomplete:
- `advise/stage2.py` used `client.messages.create(...)` directly
- `pulse/meta/analyzer.py` called the wrapper without org context, so spend was not logged/gated
- non-org call sites were partly but not uniformly annotated as budget-exempt

**Fix:**
1. Route `advise/stage2.py` through `call_claude(...)`.
2. Decide whether `pulse/meta/analyzer.py` should participate in org budget tracking:
   - if yes, pass `org_id` + `call_type`
   - if no, add an explicit exemption comment and keep it out of the platform budget contract
3. Make exemption comments consistent across the remaining non-org Claude call sites.

**Tests:**
- `advise` path proves wrapper usage when org context exists
- one org-scoped analysis path proves either spend logging or an explicit exemption decision

---

### P4 · Crash-safe writes: roster.yaml + vault notes (CRIT-2 + CRIT-3) — RESOLVED

#### roster/manager.py (CRIT-2)
**File:** `sable/roster/manager.py`, lines 27–36
**Issue:** `save_roster()` uses plain `open(path, "w")` — no lock, no atomic write.

**Fix** (preserve actual signature `save_roster(roster: Roster) -> None`):
```python
import fcntl, os

def save_roster(roster: Roster) -> None:
    path = roster_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = Path(str(path) + ".lock")
    with open(lock_path, "w") as lock_f:
        fcntl.flock(lock_f, fcntl.LOCK_EX)
        data = {
            "version": roster.version,
            "accounts": [a.to_yaml_dict() for a in roster.accounts],
        }
        tmp = path.with_suffix(".yaml.tmp")
        tmp.write_text(yaml.dump(data, default_flow_style=False, allow_unicode=True))
        os.replace(tmp, path)
```

#### vault/notes.py (CRIT-3)
**File:** `sable/vault/notes.py`, lines 33–47 and 94–97
**Issue:** `write_note()` and `save_sync_index()` use `path.write_text()` directly.
Fix: Extract `atomic_write(path, content)` to `sable/shared/files.py` reusing the
`_write_to_temp()` + `os.replace()` pattern already present in `platform_sync.py`.
Replace both `write_text()` calls with `atomic_write()`.

**Test:** Signal-inject mid-write; assert file is either old or new content, never partial.

---

### P5 · Silent fallback in reporting paths (CC-1 / MED-4 / MED-5)

**Files:** `sable/advise/stage1.py`, `sable/vault/search.py`, `sable/vault/sync.py`,
`sable/platform/cli.py`, `sable/pulse/meta/cli.py`, `sable/pulse/account_report.py`

**Issue:** Many paths do `except Exception: result[...] = []` with no log. Real DB failures
look identical to "no data yet."

**Fix pattern:**
```python
# Replace:
except Exception:
    result["pulse_data"] = []

# With:
except Exception as e:
    logger.warning("stage1 pulse read failed: %s", e, exc_info=True)
    result["pulse_data"] = []
    result.setdefault("failed_sources", []).append("pulse")
```

**`pulse/meta/cli.py`** — ✓ done (fallback analysis frontmatter/banner landed)

**All paths hardened — P5 complete:**
- `advise/stage1.py` — ✓ done (all four blocks: warning + exc_info + failed_sources)
- `vault/search.py` — ✓ done (warning + exc_info; failed_sources n/a: returns list not dict)
- `vault/sync.py` — ✓ done (exc_info=True added to supporting-page refresh block)
- `platform/cli.py` — ✓ done (pulse + meta freshness reads upgraded from debug → warning + exc_info)
- `pulse/account_report.py` — ✓ done (`_load_niche_lifts` already has `logger.warning(..., exc_info=True)`)

---

### Historical / Remaining Critical

**AR5-6 · Path traversal in vault_dir() — `shared/paths.py:124` (CRIT-4) — RESOLVED**
Fix:
```python
import re
_ORG_SLUG = re.compile(r'^[a-zA-Z0-9_-]+$')

def vault_dir(org: str = "") -> Path:
    if org:
        if not _ORG_SLUG.match(org):
            raise SableError(INVALID_ORG_ID, f"Invalid org slug: {org!r}")
        d = root / org
        ...
```
Test: `vault_dir("../../tmp")` raises `SableError`, does not create a directory.

**AR5-7 · Missing-entity guard in execute_merge() — `platform/merge.py:61` (CRIT-5) — RESOLVED**
Fix:
```python
source_row = conn.execute(...).fetchone()
target_row = conn.execute(...).fetchone()
if source_row is None:
    raise SableError(ENTITY_NOT_FOUND, f"Source entity {source_id!r} not found")
if target_row is None:
    raise SableError(ENTITY_NOT_FOUND, f"Target entity {target_id!r} not found")
```
Test: `execute_merge()` with nonexistent entity ID → `SableError`, not `TypeError`.

---

### Historical / Remaining High

**AR5-8 · Failed author fetches untracked — `scanner.py:225–234` (HIGH-3) — RESOLVED**
Fix: Add `self._failed_authors: list[str] = []` to Scanner. Append handle on exception.
Include in scan_runs result JSON and surface as CLI warning if non-empty.

**AR5-9 · Tweet cursor string max() — `scanner.py:288` (HIGH-4) — RESOLVED**
Fix:
```python
valid_ids = [int(t["tweet_id"]) for t in normalised
             if t.get("tweet_id") and str(t["tweet_id"]).isdigit()]
latest_id = str(max(valid_ids)) if valid_ids else None
```

**AR5-10 · Deep-mode outsider tweets not persisted — `scanner.py:297–339` (HIGH-5) — RESOLVED VIA TRANSIENT SCOPE**
**Issue:** Current `scanned_tweets` schema has no `source` column, and `upsert_tweet()` does
not store outsider provenance. So "just call `upsert_tweet(..., source='outsider')`" is not
compatible with the current DB contract.

Fix — choose one of these explicitly before implementation:
1. **Preferred:** add a dedicated outsider persistence path:
   - either `scanned_outsider_tweets`
   - or a new nullable `source TEXT DEFAULT 'watchlist'` column on `scanned_tweets`
   If using the second option, add a migration plus `upsert_tweet()` support for `source`.
2. **Smaller scope:** keep outsiders ephemeral for now and mark the feature as non-persistent:
   - update CLI/help/report text to say outsider results are transient
   - do not imply they are stored or included in later baselines

Do not implement persistence without also implementing a schema-level way to distinguish
watchlist tweets from outsider tweets.

**AR5-11 · Corrupted artifact cache rows loop forever — `generate.py:31–61` (HIGH-6) — RESOLVED**
Fix landed: `except (json.JSONDecodeError, KeyError)` block now executes
`conn.execute("UPDATE artifacts SET stale=1 WHERE artifact_id=?", (row["artifact_id"],))`
and `continue`. Corrupt rows are marked stale and skipped on subsequent lookups.

**AR5-12 · No LIMIT on entity sync query — `platform_sync.py:~312` (HIGH-7) — RESOLVED**
Fix: Paginate with `LIMIT 500 OFFSET n` loop. Write files per page before loading the next.
Note: implement P1's sentinel/phase-B consistency model first. Paging introduces partial
page writes that must also be recoverable — the sentinel approach from P1 covers this if
the per-page file writes are added to `temp_writes` before any phase-B renames fire.

**AR5-13 · FFmpeg subtitle path injection — `shared/ffmpeg.py:166` (HIGH-8) — RESOLVED**
Fix:
```python
import re
_FFMPEG_SPECIAL = re.compile(r'[;:\[\]=]')
if _FFMPEG_SPECIAL.search(str(subtitle_path)):
    raise SableError(INVALID_PATH, f"Subtitle path has FFmpeg special chars: {subtitle_path}")
```
Or: escape the path properly per FFmpeg filter-graph escaping rules.

**AR5-14 · Migration partial-apply risk — `platform/db.py:27–40` (HIGH-9)**
**Issue:** `ensure_schema()` calls `conn.executescript(sql_path.read_text())` which
implicitly commits before and after execution. A mid-migration failure can leave the schema
at a partial state without updating `schema_version`, making the migration non-re-runnable.

Fix: Wrap each migration in an explicit transaction and update `schema_version` within the
same transaction. Because `executescript()` can't be used inside a managed transaction
(it always auto-commits), the migration runner must either:
- Split each SQL file into individual statements and execute them one-by-one with
  `conn.execute()` inside `with conn:`, or
- Restructure the SQL files to one statement per file so no splitting is needed.

A simple splitter (split on `;`, strip blank lines) works for the current migration files
but should be validated against each SQL file's content before switching.

---

### Historical / Medium Issues

**AR5-15 · format_baseline() duplicate rows — `pulse/meta/db.py` — RESOLVED**
Fix: `upsert_format_baseline()` performs a plain INSERT — not an upsert. Fix the function
to use `INSERT OR REPLACE` (requires a UNIQUE index) or `ON CONFLICT DO UPDATE`.
The natural key is `(org, format_bucket, period_days)`.

Cleanup migration for existing duplicates (`ALTER TABLE ... ADD UNIQUE` is not valid SQLite;
use `CREATE UNIQUE INDEX` instead):
```sql
DELETE FROM format_baselines
WHERE rowid NOT IN (
    SELECT MAX(rowid) FROM format_baselines GROUP BY org, format_bucket, period_days
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_format_baselines_key
    ON format_baselines (org, format_bucket, period_days);
```

**AR5-16 · has_link pre-filtered before classify_format() — `fingerprint.py:52` — RESOLVED**
Fix: Pass `urls`, `has_image`, `has_video` separately into `classify_format()`. Move
exclusion logic there, not in `_normalise_tweet()`.

**AR5-17 · format_lift unreliable flag not checked at call sites — `normalize.py` — RESOLVED**
Fix: Audit callers of `format_lift`. Gate on `format_lift_reliable` or return `None` when
unreliable, so callers can't use the value without knowing it's a copy of total_lift.

**AR5-18 · Zero-baseline lift deflation — `normalize.py:144–149` — RESOLVED**
Fix: When engagement history is empty, return `format_lift=None, format_lift_reliable=False`
instead of computing against floor denominator of 8.

**AR5-19 · String date cutoff comparison — `scanner.py:131–136` — RESOLVED**
Fix: Make `_parse_twitter_date()` raise on failure. Skip unparseable tweets with a warning
rather than passing them through the `>=` string comparison.

**AR5-20 · Analysis phase has no cost guard — `pulse/meta/cli.py` — RESOLVED**
Fix: Add `max_analysis_cost` config key. Estimate token count before `_run_analysis()`.
Raise or degrade if estimate exceeds cap.

**AR5-21 · Naive UTC datetimes for budget windows — `platform/cost.py`, `platform/merge.py` — RESOLVED**
Fix: Replace every `datetime.utcnow()` with `datetime.now(timezone.utc)`. Ensure SQLite
stored values include UTC offset for unambiguous comparison at week boundaries.

**AR5-22 · Budget `>=` blocks at-exactly-cap — `cost.py:81` — OBSOLETE / REJECTED**
Repo contract now explicitly treats "at cap" as blocked. Keep `>=`.

**AR5-23 · Expired merge candidates unrecoverable — `merge.py:19–23` — RESOLVED**
Fix: Add `reconsider_expired_merges(org_id, conn)` that re-evaluates `status='expired'`
candidates and flips them to `'pending'` if updated confidence now exceeds threshold.

**AR5-24 · INSERT OR IGNORE silent drop — `pulse/db.py` — RESOLVED AT DB LAYER**
Fix: Check `cursor.rowcount` after `INSERT OR IGNORE`. Return `True` if new, `False` if
already existed. Update callers that want new-vs-existing counts.

**AR5-25 · Hardcoded API pricing — `advise/stage2.py`**
Fix: Move to `sable/shared/pricing.py` as a versioned dict:
```python
# last_updated: 2026-03-23
COST_PER_1K_TOKENS = {
    "claude-sonnet-4-6": {"input": 0.003, "output": 0.015},
    ...
}
```

**AR5-26 · Whisper model reloaded per call — `clip/transcribe.py` — RESOLVED**
Fix: Add module-level `_MODEL_CACHE: dict[str, WhisperModel] = {}`.
`_load_model(name)` checks cache before instantiating.

**AR5-27 · Claude JSON parse failure drops full clip batch — `selector.py:342` — RESOLVED**
Fix: `logger.warning("Claude eval parse failed, raw=%r", raw[:500])` before falling back.
Single retry attempt before setting `evaluations = []`.

**AR5-28 · Brainrot loop count unbounded — `brainrot.py:148` — RESOLVED**
Fix:
```python
loops = min(int(target_duration / src_duration) + 2, 30)
if loops == 30:
    logger.warning("Brainrot source clip very short (%.2fs); loop count capped at 30", src_duration)
```

---

### Cross-Cutting

**CC · Exponential backoff for external API calls**
Affected: `scanner.py` (SocialData 429s — async), `stage2.py` (Anthropic — sync),
`selector.py` (Anthropic — sync).

`scanner.py` is async (`asyncio`); using `time.sleep()` there would block the event loop.
Split into two helpers in `sable/shared/retry.py`:

```python
import asyncio, time, random

def retry_with_backoff(fn, max_retries=3, base_delay=1.0):
    """Sync retry. Use for stage2.py, selector.py."""
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            time.sleep(base_delay * (2 ** attempt) + random.uniform(0, 0.5))

async def retry_with_backoff_async(coro_fn, max_retries=3, base_delay=1.0):
    """Async retry. Use for scanner.py."""
    for attempt in range(max_retries):
        try:
            return await coro_fn()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(base_delay * (2 ** attempt) + random.uniform(0, 0.5))
```

**CC · Timezone enforcement sweep — RESOLVED**
Grep: `git grep "utcnow()"`. Replace every instance with `datetime.now(timezone.utc)`.
(AR5-21 covers `cost.py` specifically; this sweep covers all remaining instances.)
Verify SQLite stored strings are ISO8601 with `+00:00`.

**CC · Document undocumented magic constants — RESOLVED**
Add inline `# why:` comments to:
- `normalize.py`: thresholds (5/10/20), lift weights (1.0/0.8/0.5/0.25), fallback baseline (5.0)
- `stage1.py`: engagement weights (likes=1.0, replies=3.0, retweets=4.0, quotes=5.0, bookmarks=2.0, views=0.5)
- `scanner.py`: retry sleep (5s), deep mode query count (3)
No need to move to config unless operator tuning is required.

---

## AR-5 Batch 1 Follow-ups (2026-03-24)

Verified by independent re-run of ruff, mypy, and code inspection after the first implementation
batch (brainrot, transcribe, normalize, pulse/db, magic comments, utcnow sweep).

All five findings below are confirmed real. The batch agent claimed "all clean" but ran
targeted per-file checks rather than `ruff check .` and `mypy sable` repo-wide.

---

### FOLLOW-UP-1 · AR5-18 regression — None arithmetic crash in aggregation (CRIT) — RESOLVED 2026-03-24

**Status:** Landed in current workspace. Keep the notes below as historical context for the
regression that was fixed.

**Historical status at the time of this follow-up:** Partially implemented — regression introduced.

**What was done:** `_compute_fallback()` in `normalize.py` now returns `None` for all lift
fields when `len(author_history) == 0`. That part is correct.

**Regression:** Two downstream consumers treat `total_lift` as a required `float`:
- `weighted_mean_lift()` (`normalize.py:309`): does `t.total_lift * t.author_quality.weight`
- `assess_format_quality()` (`quality.py:90,110–126`): does `0.0 + t.total_lift`,
  `sum(lifts)`, `max(lifts)`, `min(lifts)`, and variance comparisons

Both crash at runtime if a zero-history fallback tweet reaches the aggregation path.
mypy confirms: 9 new type errors in these two functions.

**Fix strategy — harden aggregation, not the None source:**
In `weighted_mean_lift()`: skip tweets where `t.total_lift is None` (or treat as weight=0).
In `assess_format_quality()`:
- `author_lift` accumulation: skip `None` total_lift rather than adding it
- Small-bucket variance check: filter `lifts = [t.total_lift for t in tweets if t.total_lift is not None]`
  and guard `if len(lifts) >= 2:` before calling `max()`/`min()`
- Mixed-quality `fb_avg`/`st_avg`: guard with `if fallback_tweets` and skip None lifts

Do NOT revert the None-for-zero-history change — that's the correct behavior. Harden the callers.

**Test to add:** `tests/test_pulse_meta.py` — build an `AuthorNormalizedTweet` with
`total_lift=None` (zero-history fallback), pass it through `weighted_mean_lift()` and
`assess_format_quality()`, assert no exception raised and result is still meaningful
(fallback tweet is excluded from or down-weighted in aggregation, not causing crash).

---

### FOLLOW-UP-2 · AR5-24 not leveraged — `tracker.py` ignores insert_post bool — RESOLVED (AR-5 batch 2)

`tracker.py` now captures the bool, increments `new_count`, and logs new vs. fetched counts.

**Historical status at time of follow-up:** Implemented but incomplete.

`pulse/db.py:insert_post()` now returns `True` if new, `False` if duplicate. But
`tracker.py:130` calls `db.insert_post(...)` without capturing the return value — the new
capability is dead.

**Fix:** In `tracker.py`, capture the bool and use it:
```python
is_new = db.insert_post(
    post_id=str(post_id),
    account_handle=handle,
    ...
)
# Caller can log/count new vs existing posts if needed.
```
Decide whether the tracker loop should track a `new_count` counter and surface it to the caller.
At minimum, the return value must be captured (even if discarded with `_`) so the bool contract is visible.

**Test to add:** `tests/` — insert same post twice via `insert_post()`. Assert first call returns
`True`, second returns `False`. Assert DB contains exactly one row for that post_id.

---

### FOLLOW-UP-3 · Ruff violations — RESOLVED (AR-5 batch 2)

Ruff went from 28 violations to 0. All F541, F841, E701, and F811 codes cleared across
all newly touched and pre-existing files. Validation gate passed: `ruff check .` exits 0.

---

### FOLLOW-UP-4 · mypy new errors from AR5-18 (9 type errors, 32 files total) — RESOLVED WITH FOLLOW-UP-1

**Context:** mypy baseline before this batch was 118 errors in 43 files.
After batch: 121 errors in 32 files. Batch fixed ~12 pre-existing errors but added 9 new ones.

All 9 new errors in this historical snapshot were caused by the AR5-18 regression
(FOLLOW-UP-1 above). They are now resolved in current code.

Remaining 112 pre-existing mypy errors (in `ffmpeg.py`, `thumbnail.py`, `stage2.py`,
`assembler.py`, `character_explainer/thumbnail.py`, `character_explainer/pipeline.py`,
`vault/cli.py`, `advise/generate.py`, `brainrot.py`) are **not** introduced by this batch
and should be tracked separately, not conflated with AR-5 work.

**Validation gate (must pass before marking AR-5 type-clean):**
```
./.venv/bin/mypy sable   # must show no increase from 112 pre-existing baseline
```

---

### FOLLOW-UP-5 · Missing tests for batch 1 completed items — RESOLVED (AR-5 batch 2)

All four tests now present and passing:
- T1 (`test_model_cache_reuses_instance`) in `tests/test_transcribe.py`
- T2 (`test_loop_to_duration_caps_at_30`) in `tests/test_brainrot.py`
- T3 (`test_insert_post_returns_true_for_new_false_for_duplicate`) in `tests/test_pulse_meta.py`
- T4 (`test_zero_history_fallback_does_not_crash_aggregation`) in `tests/test_pulse_meta.py`

---

## History — Completed Audit Rounds

### Audit Fix Rework — AR-1 through AR-4 (implemented 2026-03-23)

AR-1 through AR-4 were implemented. Two items were deferred at that time:
- **Scanner._estimated_cost instance attribute promotion** — superseded by P2 above.
- **Click-level CLI test for scan exception** — superseded by P2 test above.

---

## Platform Layer — Upcoming Rounds

### Round 2 — Cult Doctor (community health grader) ✓ **Complete** (2026-03-23)
- Cult Grader writes to sable.db after every run via `platform_sync.py` in Sable_Cult_Grader
- Discord playbook generator (`playbook/`) and operator bot (`bot/`) live in Sable_Cult_Grader
- Schema version 3; DB migrations 002+003 extend `sync_runs` and `diagnostic_runs`

### Round 3 — SableTracking integration ✓ **Complete** (2026-03-23)
- `app/platform_sync.py` bridges Google Sheets (contributors + content_log) → `sable.db`
- Async sync runner, `_apply_pending_migrations()`, `SABLE_CLIENT_ORG_MAP` env var config
- 36 tests passing; schema version remains 3

---

## Vault — Non-MVP Features (Phase 2+)

Extracted from vault spec. Not implemented in Phase 1 CLI.

- **Phase 2 — Web UI (`sable serve`)**
  - FastAPI app in `sable/serve/app.py` wrapping all vault functions
  - Cloudflare Tunnel for team/client access
  - Role-based access control via `sable/vault/permissions.py` (currently stub)
  - Token auth middleware + `~/.sable/vault_users.yaml` user store
  - Web views: dashboard, content browser, search, reply suggest, posting log
  - See `docs/ROLES.md` for permission matrix, `docs/ROADMAP.md` for architecture

- **Phase 3 — VPS**
  - Docker + systemd, Postgres backend, multi-org S3 vault storage
  - Webhook receivers for pulse data push + tweet notifications
  - Scheduled sync via cron

- **Phase 4 — Scale**
  - Multi-tenant auth, vault-as-API, real-time enrichment queue (Celery/Redis)
  - Automated gap-fill suggestions triggered by pulse performance data
  - Client portal with read-only dashboard + export access

---

## New Feature Suite — Content Intelligence Loop

These features close the gap between format intelligence (what the niche rewards) and content
production (what the account outputs). All build on existing infrastructure in pulse.db,
meta.db, sable.db, the vault, roster profiles, and the `call_claude()` wrapper.

## Feature Readiness Review (2026-03-24)

No feature below should start until the **Feature Gate** above is satisfied.

### Global spec corrections Claude must apply before implementing any feature below

- command registration happens in `sable/cli.py`, not `sable/commands/__init__.py`
- top-level commands belong in `sable/cli.py`; nested subcommands belong in the owning group
  file such as `sable/pulse/cli.py` or `sable/pulse/meta/cli.py`
- handle-scoped commands should call `require_account()` first and default `--org` from the
  roster account when `--org` is omitted
- `build_account_context()` takes an `Account` object, not a bare handle string
- `pulse.db` uses `posts.id` and `snapshots.id`; sample SQL below that mentions `post_id`
  or `snapshot_id` is conceptual and must be translated to the live schema
- `pulse.db.posts.sable_content_type` is only a coarse production hint (`clip`, `meme`,
  `faceswap`, `text`, `unknown`, plus occasional tool-specific spillover). It is not a
  full format taxonomy and must be mapped to pulse-meta format buckets explicitly
- `meta.db.format_baselines` stores baseline aggregates only; it does **not** store
  `current_lift`, `status`, `momentum`, or `confidence_grade`
  - any feature needing “current niche trend” must reuse existing pulse-meta trend helpers or
    add a small adapter around the current scan + baselines logic
- `load_all_notes()` returns a list of frontmatter dicts with synthetic `_note_path`
  fields; it does **not** return `(note, path)` tuples
- `load_all_notes()` only scans `vault/content/**/*.md`
  - anything written under `digests/`, `playbooks/`, or other top-level vault folders will
    **not** be visible to `vault search` unless the loader and CLI filters are deliberately
    widened with tests
- vault note lifecycle is currently represented by `posted_by` and `suggested_for`
  - there is no canonical `status='posted'` field on content notes today
- content note freshness comes from `assembled_at`; there is no canonical `created_at`
  frontmatter field on synced content notes today
- any feature that reasons about tracker freshness must use the fixed source-time contract
  from Current Open Queue item 3, not `content_items.created_at`
- `search_vault()` is called as
  `search_vault(query, vault_path, org, filters=SearchFilters(...), config=...)`
  - it does **not** accept bare keyword args like `depth="shallow"`
- config access should use `sable.config.get(...)` / `require_key(...)`, not a nonexistent
  `get_config()` helper

### Staged feature order after bug fixes

1. **Stage 2:** `FEATURE-3` (`sable pulse account`) ✓ **Complete** (2026-03-24)
2. **Stage 3:** `FEATURE-1` (`sable write`) ✓ **Complete** (2026-03-25)
   - `FEATURE-2` (`sable score`) ✓ **Complete** (2026-03-25)
3. **Stage 4:** `FEATURE-4` (viral anatomy archive) ✓ **Complete** (2026-03-25), `FEATURE-6` (watchlist digest) ✓ **Complete** (2026-03-25)
   - best implemented as a pair; digest should consume cached anatomy
   - spec maturity: medium-high
4. **Stage 5 (actual delivery order):** `FEATURE-8` (`sable diagnose`) ✓ **Complete** (2026-03-25) — shipped before Stage 4
5. **Stage 6:** `FEATURE-9` (`sable pulse attribution`) ✓ **Complete** (2026-03-26)
6. **Stage 7:** `FEATURE-7` (`sable calendar`) ✓ **Complete** (2026-03-26) — spec rewritten ground-up, all slices landed
7. **Stage 8:** FEATURE-PULSE-META-SKIP-FRESH ✓ Done (2026-03-26), FEATURE-ONBOARD-PREP (--prep variant) ✓ Done (2026-03-26), FEATURE-ADVISE-EXPORT ✓ Done
8. **Stage 9:** `MIGRATION-006` (`discord_pulse_runs` table) ✓ **Complete** (2026-03-26) — Cult Doctor F-DM platform sync fully wired

### Feature delivery rules

- land **one feature at a time** after the Feature Gate is satisfied
- each feature should be split into **2–4 patch sets**, not one-shot:
  1. schema/helpers/contracts + failing tests
  2. core computation/rendering
  3. CLI wiring + persistence/integration
  4. only then default-on automation or extra polish
- if a feature adds a new `meta.db` table, the **first** patch set should land only:
  - `_SCHEMA` update
  - DB helper functions
  - migration/idempotence tests
- do **not** mix new feature work with unresolved Stage 0 / Stage 1 bugfix items
- after each patch set:
  - rerun `pytest`, `ruff`, and `mypy`
  - update this TODO with what landed, what is still blocked, and the exact validation output

### Per-feature completeness / readiness summary

- `FEATURE-3` is **Complete (2026-03-24)**. All slices A+B+C landed.
- `FEATURE-1` is **Complete (2026-03-25)**. Slices A, B, C landed.
- `FEATURE-2` is **Complete (2026-03-25)**.
- `FEATURE-4` is **Complete (2026-03-25)**. All slices A+B+C landed.
- `FEATURE-6` is **Complete (2026-03-25)**. All slices A+B+C landed. 6 tests in `tests/pulse/meta/test_digest.py`.
  - `meta_db_path` and `vault_root` removed from `generate_digest` (were dead — uses `get_conn()`)
  - CLI saves vault separately via `save_digest_to_vault(report, vault_dir(org))`
- `FEATURE-7` is **Complete (2026-03-26)**. All slices A+B+C landed. 12 tests in `tests/calendar/test_planner.py`. 388 passed · 0 ruff.
  - Spec rewritten ground-up: `posted_by` dicts, `assembled_at`, `avg_total_lift` column, `_content_type_to_format_bucket` reused
  - `tests/calendar/` has no `__init__.py` (avoids shadowing stdlib `calendar` module)
- `FEATURE-8` (`sable diagnose`) is **Complete (2026-03-25)**. 359 passed · 0 ruff · 0 mypy.
  - `assembled_at`, `posted_by`, and `topic_signals` all confirmed present in live data.
- `FEATURE-9` (`sable pulse attribution`) is **Complete (2026-03-26)**. All slices A+B+C landed. 12 new tests (4 Slice A + 8 Slice B). 388 passed · 0 ruff · 0 mypy at landing.

**Prerequisite reading before implementing any feature:**
- `sable/pulse/meta/fingerprint.py` — `classify_format()` and `_normalise_tweet()`
- `sable/pulse/meta/normalize.py` — `compute_author_lift()`, `_compute_fallback()`, `weighted_mean_lift()`
- `sable/pulse/meta/db.py` — `scanned_tweets` schema, `format_baselines` schema, `upsert_format_baseline()`
- `sable/pulse/db.py` — `posts` + `snapshots` schema, `insert_post()`
- `sable/shared/api.py` — `call_claude()`, `call_claude_json()`, `build_account_context()`
- `sable/vault/notes.py` — `write_note()`, `read_note()`, `load_all_notes()`
- `sable/vault/search.py` — `search_vault()`, `claude_rank()`
- `sable/roster/manager.py` — `load_roster()`, `require_account()`, `roster_path()`
- `sable/shared/paths.py` — `sable_home()`, `vault_dir()`, `meta_db_path()`, `pulse_db_path()`

**Validation gates after each feature:**
```
./.venv/bin/python -m pytest -q
./.venv/bin/ruff check .
./.venv/bin/mypy sable
```

All three must exit 0. mypy is currently clean; no regressions allowed.

---

### MIGRATION-006 · `discord_pulse_runs` table — required by Cult Doctor F-DM

**Status:** ✓ Complete (2026-03-26). Schema v6 live. Cult Grader `sync_after_pulse_run` wired and tested.

**What landed:**
- `sable/db/migrations/006_discord_pulse.sql` — creates `discord_pulse_runs` table + index, bumps schema to 6
- `sable/platform/discord_pulse.py` — `upsert_discord_pulse_run()` + `get_discord_pulse_runs()`
- `tests/platform/test_discord_pulse_runs.py` — 5 tests (upsert, idempotency, get newest-first, migration, schema version)
- Sable_Cult_Grader `platform_sync.py` — `sync_after_pulse_run(config, pulse)` (fire-and-forget, two-level ImportError guard)
- Sable_Cult_Grader `diagnose.py` — `cmd_discord_pulse()` calls `sync_after_pulse_run` after archive save
- Sable_Cult_Grader `tests/platform_sync/test_sync.py` — 4 new tests in `TestSyncAfterPulseRun`

**Validation (2026-03-26):** 392 passed · 2 pre-existing failures (unrelated TweetMetrics schema drift in `TestIntegrationRealArchive`)

**Context:** Sable_Cult_Grader is adding F-DM (Continuous Discord Monitoring / Discord Pulse). After each pulse run, when `sable_org` is set on the project config, `platform_sync.py` in Cult Grader writes a row to `discord_pulse_runs` in `sable.db`.

**Schema version:** bumped from 5 → 6.

#### Migration file to create

`sable/db/migrations/006_discord_pulse.sql`:

```sql
CREATE TABLE IF NOT EXISTS discord_pulse_runs (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id                TEXT NOT NULL,
    project_slug          TEXT NOT NULL,
    run_date              TEXT NOT NULL,           -- ISO date YYYY-MM-DD
    wow_retention_rate    REAL,                    -- NULL on first pulse run (no prior window)
    echo_rate             REAL,
    avg_silence_gap_hours REAL,
    weekly_active_posters INTEGER,
    retention_delta       REAL,                    -- NULL on first run
    echo_rate_delta       REAL,                    -- NULL on first run
    created_at            TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_discord_pulse_runs_org_date
    ON discord_pulse_runs (org_id, run_date);

UPDATE schema_version SET version = 6 WHERE version < 6;
```

#### DB helper additions (`sable/db/platform.py` or `sable/platform/db.py` — whichever owns sable.db writes)

Add two functions alongside the existing diagnostic_runs / sync_runs helpers:

```python
def upsert_discord_pulse_run(
    conn: sqlite3.Connection,
    org_id: str,
    project_slug: str,
    run_date: str,
    wow_retention_rate: float | None,
    echo_rate: float | None,
    avg_silence_gap_hours: float | None,
    weekly_active_posters: int | None,
    retention_delta: float | None,
    echo_rate_delta: float | None,
) -> None:
    """Insert or replace a discord pulse run row. Idempotent on (org_id, project_slug, run_date)."""
    ...

def get_discord_pulse_runs(
    conn: sqlite3.Connection,
    org_id: str,
    project_slug: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """Return recent pulse run rows for an org, newest first."""
    ...
```

Idempotency: `INSERT OR REPLACE` keyed on `(org_id, project_slug, run_date)` — add a UNIQUE constraint on those three columns (or handle at the Python layer with an upsert).

#### Tests required

`tests/platform/test_discord_pulse_runs.py` (new file):
- `test_upsert_creates_row` — write a row, confirm it exists
- `test_upsert_is_idempotent` — writing twice for the same (org, slug, date) produces one row
- `test_get_discord_pulse_runs_returns_newest_first`
- `test_migration_creates_table_and_index` — call `_apply_pending_migrations()` on a fresh DB, confirm table + index exist
- `test_schema_version_bumped_to_6`

#### Delivery order

1. Write `006_discord_pulse.sql`
2. Add `upsert_discord_pulse_run()` + `get_discord_pulse_runs()` helpers + tests
3. Verify `_apply_pending_migrations()` picks up the new file automatically (no changes needed there if it glob-sorts migration files)
4. Confirm all existing tests still pass (migration is additive — no schema breakage)

Do NOT add any CLI command for pulse runs in this repo. The write path is owned by Cult Grader's `platform_sync.py`; the read path is future SablePlatform work. This migration is infrastructure only.

---

### FEATURE-3 · `sable pulse account` — Account-Level Format Lift

**Priority:** Implement first. Required by Feature 7 (calendar).
**Status:** All slices complete (2026-03-24). Slice A + B + C landed.
**Completeness:** Medium-low. Valuable feature, but the original draft had real schema drift.
**Hard blockers:** Current Open Queue items 1 and 3 — both resolved.

**Implementation slices (do in order):**
1. **Slice A — live data contract + tests** ✓ **Done**
   - `sable/pulse/account_report.py`: `FormatLiftEntry`, `AccountFormatReport`, `_classify_post`,
     `_compute_account_baseline`, `_engagement_score`, `_divergence_signal`, `_load_posts_with_snapshots`,
     `_load_follower_count`, `compute_account_format_lift`, `render_account_report`
   - `tests/pulse/test_account_report.py`: 35 tests — empty history, missing snapshots, org fallback,
     classify_post mapping, baseline computation, lift formula, window filtering, handle normalization,
     render output
   - `_load_niche_lifts` stubbed to return `{}` — full meta.db trend pipeline is Slice B
   - Validation: `274 passed · 0 ruff · 98 mypy` (no regression)
2. **Slice B — niche baseline integration** ✓ **Done**
   - implement `_load_niche_lifts()`: connect meta.db, run `analyze_all_formats()` with correct signature
   - wire divergence computation into entries when niche data is available
   - render terminal output with niche column when present
   - Validation: `279 passed · 0 ruff · 98 mypy` (no regression)
3. **Slice C — CLI integration** ✓ **Done**
   - add `sable pulse account`
   - make `--org` optional and default from roster when available
   - no persistence or caching in v1

**Post-implementation audit findings (2026-03-24):**

*Real issues — LOW severity:*

- **`_load_niche_lifts` ignores `days` param** (`account_report.py:177`): always queries
  the last 30 days from meta.db regardless of the `days` argument passed to
  `compute_account_format_lift`. If called with `days=7`, account data is 7 days but
  niche data is 30 days — semantic mismatch. Acceptable for v1 where default is 30d,
  but should be threaded through in Slice C or a future pass.

- **`_load_follower_count` is dead code** (`account_report.py:149`): defined but never
  called. The spec mentioned follower-relative normalization as optional; the
  implementation uses raw engagement throughout. Either wire it in or delete it.

- **Silent `except Exception` in `_load_niche_lifts`** (`account_report.py`) — ✓ resolved:
  `logger.warning(..., exc_info=True)` is in place at the except block.

*Stale / misleading:*

- **Section header comment** (`account_report.py:158`): still reads "Slice B — stubbed for
  Slice A" — should be updated to reflect the real implementation.

- **Test file docstring** (`test_account_report.py:1`): says "Slice A: data model, readers,
  helpers" — Slice B integration tests now live in the same file.

- **`test_divergence_execution_gap_with_niche_data` docstring** (`test_account_report.py:594`):
  says "Account thread" but the setup inserts `clip` posts (→ `short_clip`). Thread/clip
  mismatch in the docstring.

*Coverage gaps:*

- **No test: meta.db tweets older than 30 days excluded** — the `posted_at >= ?` SQL
  filter in `_load_niche_lifts` is not covered by any test.

- **No test: `niche_confidence` value after Slice B wiring** — should be `"C"` (confidence
  grade C because quality gates always fail with `baseline_days_available=0`). Not
  asserted in any Slice B test.

- **No test: empty scanned_tweets after org filter** — `_load_niche_lifts` returns `{}`
  when no rows match the org+window query. Only the nonexistent-path case is tested.

- **`_classify_post` thread-detection gap** (known V1 limitation): for `sable_content_type='text'`,
  always passes `is_thread=False` to `classify_format()` because pulse.db has no thread
  marker. Text threads will be miscategorized as `standalone_text`. Not a bug in v1 but
  should be documented in Slice C help text.

**Purpose:** Applies the same normalized lift computation used for watchlist accounts to
the managed account's own posting history. Reveals what formats actually work for the
specific account (vs what works in the niche generally), and flags divergence between them.

**Command syntax:**
```
sable pulse account @handle [--days 30] [--org ORG]
```

If `--org` is omitted, default to the roster account org. If no org is available, still
run the account-only report and skip divergence-to-niche analysis cleanly.

**Files already created (Slices A+B):**
- `sable/pulse/account_report.py` — all computation logic (279 tests passing)
- `tests/pulse/test_account_report.py` — 40 tests

**Remaining file to modify (Slice C):**
- `sable/pulse/cli.py` — add `account` subcommand (following pattern of existing subcommands)

**No new database tables.** Reads pulse.db (posts + snapshots) and meta.db
(`scanned_tweets` plus baselines/trend-helper inputs).

**Computation steps in `account_report.py`:**

1. **Load posts with their most-recent snapshot engagement:**
   ```sql
   SELECT p.id, p.text, p.posted_at, p.sable_content_type,
          s.likes, s.retweets, s.replies, s.views, s.bookmarks, s.quotes
   FROM posts p
   LEFT JOIN snapshots s ON (
       p.id = s.post_id
       AND s.id = (
           SELECT MAX(s2.id) FROM snapshots s2 WHERE s2.post_id = p.id
       )
   )
   WHERE p.account_handle = ? AND p.posted_at >= ?
   ORDER BY p.posted_at DESC
   ```
   - use the canonical `@handle` contract from Stage 0 item 1
   - if a post has no snapshot yet, keep it in the post count but treat engagement as `0`
   - if follower-relative normalization is attempted, read the latest `account_stats` row
     separately; do not try to join it into the post query in a way that duplicates rows

2. **Classify each post by format bucket:**
   Call `sable/pulse/meta/fingerprint.py::classify_format()`. Posts don't have the same
   tweet-dict structure as meta.db tweets, so map before calling:
   - `sable_content_type = 'clip'` → default to `short_clip`; only upgrade to `long_clip`
     when a real duration signal exists from sidecar/vault metadata
   - `sable_content_type = 'meme'` → `single_image`
   - `sable_content_type = 'explainer'` → `long_clip`
   - `sable_content_type = 'faceswap'` → `short_clip`
   - `sable_content_type = 'text'` or `unknown` → build a minimal tweet-dict with `text`,
     `has_image=False`, `has_video=False`, `urls=[]`, `is_retweet=False`,
     `is_quote_tweet=False`, then pass to `classify_format()`
   - do **not** assume `sable_content_type` is already a pulse-meta format bucket

3. **Compute account engagement rate baseline:**
   For this account, compute median engagement per post across all posts in the window.
   Use the same engagement formula as `normalize.py`: `likes + 3*replies + 4*retweets +
   5*quotes + 2*bookmarks + 0.5*views`. Divide by follower count if available from
   `account_stats` table, otherwise use raw engagement. The key is author-relative normalization.

4. **Compute per-format lift:**
   For each format bucket, compute mean of (post_engagement / account_baseline) across all
   posts in that bucket. Require minimum 2 posts in a bucket before reporting a lift score.
   Buckets with < 2 posts should show `None` lift with label "insufficient data (N post)".

5. **Load niche format baselines for divergence:**
   Do **not** query nonexistent `current_lift / status / momentum` columns from
   `format_baselines`.
   Preferred approach:
   - load the latest scan's `scanned_tweets` for the org
   - fetch 30d / 7d baselines via `sable/pulse/meta/baselines.py`
   - reuse `sable/pulse/meta/trends.py::analyze_all_formats()` to obtain:
     - `current_lift`
     - `trend_status`
     - `momentum`
     - `confidence`
   If no org is provided or no recent scan/baselines exist, skip divergence analysis cleanly.

6. **Compute divergence signal per format:**
   - If account_lift >= 1.5 AND niche_lift >= 1.5 → `DOUBLE DOWN`
   - If account_lift <= 0.8 AND niche_lift >= 1.5 → `EXECUTION GAP`
   - If account_lift >= 1.5 AND niche_lift <= 0.8 → `ACCOUNT DIFFERENTIATION`
   - If both <= 0.8 → `AVOID`
   - Otherwise → `NEUTRAL`

**Output format (printed to console and optionally saved):**
```
@handle — Format Lift (last 30d, 47 posts, org: tig)

  standalone_text  ████████████  2.4x  niche: 2.3x  → DOUBLE DOWN
  short_clip       █████████     1.8x  niche: 1.7x  → DOUBLE DOWN
  thread           ████          0.9x  niche: 1.7x  → EXECUTION GAP
  single_image     ██            0.5x  niche: 1.1x  → AVOID
  quote_tweet      [insufficient data: 1 post]

  Top formats by account lift: standalone_text (2.4x), short_clip (1.8x)
  Niche surging but unused by this account: long_clip
```

**Dataclass models:**
```python
@dataclass
class FormatLiftEntry:
    format_bucket: str
    account_lift: float | None
    niche_lift: float | None
    niche_trend_status: str | None
    niche_confidence: str | None
    post_count: int
    divergence_signal: str  # DOUBLE DOWN / EXECUTION GAP / AVOID / NEUTRAL / ACCOUNT DIFFERENTIATION

@dataclass
class AccountFormatReport:
    handle: str
    org: str
    days: int
    total_posts: int
    entries: list[FormatLiftEntry]
    missing_niche_formats: list[str]  # formats surging in niche but never used by account
    generated_at: str
```

**Functions to implement:**
```python
def compute_account_format_lift(
    handle: str,
    org: str,
    days: int,
    pulse_db_path: Path,
    meta_db_path: Path | None = None,
) -> AccountFormatReport: ...

def _classify_post(post: dict) -> str:
    """Map pulse.db post row to format_bucket string."""

def _compute_account_baseline(posts: list[dict]) -> float:
    """Median engagement across posts. Returns 1.0 as floor to avoid division by zero."""

def render_account_report(report: AccountFormatReport) -> str:
    """Return formatted console string."""
```

**Tests (`tests/pulse/test_account_report.py`):**
- Build in-memory pulse.db with 10 posts (3 standalone_text, 3 short_clip, 2 thread, 2 single_image)
  and their snapshots. Assert `compute_account_format_lift()` returns correct lift per bucket.
- Seed pulse rows using the real producer contract (`@handle`), not bare handles.
- Test divergence: inject meta.db with thread at niche_lift=1.7x; account thread at 0.9x.
  Assert `FormatLiftEntry.divergence_signal == "EXECUTION GAP"` for thread bucket.
- Test minimum data guard: bucket with 1 post → `account_lift=None`, correct "insufficient data" label.
- Test missing niche formats: if meta.db has `long_clip` surging but no pulse.db posts use it,
  assert `long_clip` in `report.missing_niche_formats`.
- Test empty pulse.db: `compute_account_format_lift()` returns report with `total_posts=0`,
  no exception raised.
- Test org fallback: when `--org` is omitted, the command uses `Account.org`; when both are
  missing, it still renders account-only output without divergence fields.
- Test `_classify_post` maps `sable_content_type='clip'` → `'short_clip'`, `'meme'` → `'single_image'`.
- Test `render_account_report()` produces non-empty string with handle in output.

---

### FEATURE-1 · `sable write` — Tweet Writer

**Status:** Slices A, B, C complete (2026-03-25). FEATURE-1 fully shipped.
**Completeness:** Medium. The product shape is good; the draft needed live-code corrections.
**Hard blockers:** Feature Gate, `FEATURE-3`, and Stage 0 item 4 if vault topic search is used.

**Implementation slices (do in order):**
1. **Slice A — context/trend assembly + tests** ✓ **Done**
   - `sable/write/generator.py`: `TweetVariant`, `_load_format_trends`, `_select_best_format`, `_get_format_context`, `_get_vault_context`
   - `tests/write/test_generator.py`: 6 tests
   - Validation: `292 passed · 0 ruff · 97 mypy` (no regression)
2. **Slice B — Claude generation core** ✓ **Done**
   - `generate_tweet_variants()`: prompt assembly, Claude call, JSON parsing, variant validation
   - `sable/write/generator.py`: adds `generate_tweet_variants()` + 3 imports
   - `tests/write/test_generator.py`: 8 new tests (14 total)
   - Validation: `300 passed · 0 ruff · 97 mypy` (no regression)
3. **Slice C — CLI wiring** ✓ **Done**
   - register top-level `sable write` command in `sable/cli.py`
   - keep v1 console-only; do not add artifact persistence in the same patch

**Purpose:** Generates ready-to-post tweet copy for an account, using current format trends,
account profile, and vault context as input. Eliminates the blank page. Does NOT auto-post.

**Command syntax:**
```
sable write @handle [--format standalone_text] [--topic "defi yields"] [--source-url URL]
            [--variants 3] [--org ORG]
```

**New files to create:**
- `sable/write/__init__.py`
- `sable/write/generator.py` — all generation logic
- `sable/commands/write.py` — CLI entrypoint (thin Click wrapper)
- `tests/write/test_generator.py`

**Existing files to modify:**
- `sable/cli.py` — register `write` top-level command

**No new database tables.** Reads meta.db (format_baselines, scanned_tweets). Does not
persist output in v1 — operator pastes chosen variant into their posting workflow.

**Data assembled before the Claude call:**

1. **Account context:** resolve the roster account, then call
   `sable/shared/api.py::build_account_context(account)`.
   Correct live flow:
   - `acc = require_account(handle)`
   - `resolved_org = org or acc.org`
   - `context = build_account_context(acc)`
   Returns concatenated YAML persona + tone/interests/context/notes profile content.

2. **Current format trends:** Query meta.db:
   Do **not** query nonexistent `current_lift / status / momentum / confidence_grade` columns.
   Preferred live shape:
   - reuse the same niche-trend adapter defined for `FEATURE-3`
   - take the top 3–5 `TrendResult` entries by `current_lift`
   - include `current_lift`, `trend_status`, `momentum`, and `confidence`
   If no org or no recent meta data exists, skip trend context and generate from profile only.

3. **Structural examples** (for the chosen format, or top-format if none chosen):
   ```sql
   SELECT text, total_lift, author_handle
   FROM scanned_tweets
   WHERE org = ? AND format_bucket = ? AND total_lift >= 2.5
         AND posted_at >= datetime('now', '-30 days')
   ORDER BY total_lift DESC
   LIMIT 5
   ```
   These are real high-performing tweets shown to Claude as structural models, NOT as content
   to copy. Include them in the prompt as "examples of what's landing right now."

4. **Vault reference (optional):** If `--topic` is provided, run a quick vault search
   (`search_vault(topic, vault_path, org, filters=SearchFilters(...))`) and include the top-1
   result summary as background context. Skip gracefully if vault is empty or unavailable.
   - use `SearchFilters(depth="intro")` or another real filter value; there is no
     `depth="shallow"` parameter in the live API
   - do not wire this until Stage 0 item 4 (`vault/search.py` large-result path) is fixed

**Claude prompt structure:**

System prompt:
```
You are a ghost-writer for a crypto Twitter account. The account profile is:

{account_context}

Write tweet variants that sound exactly like this account — not generic crypto content.
```

User prompt:
```
Format target: {format_bucket} (currently {status}, {current_lift}x average lift in this niche)

Examples of what's performing at {format_bucket} right now (study structure, not content):
{examples_block}

Topic to write about: {topic or "choose from account interests"}
{source_tweet_block if quote_tweet}

Generate {num_variants} tweet variants. For each:
- Write the tweet text (respect Twitter's 280-char limit for standalone; 280 per tweet for threads)
- Identify the structural move you're making (e.g. "contrarian claim + specific number")
- Rate format fit 1-10 based on how well it matches the example structure patterns

Return JSON:
{
  "variants": [
    {
      "text": "...",
      "structural_move": "...",
      "format_fit_score": 8.5,
      "notes": "optional one-liner about the approach"
    }
  ]
}
```

**Functions to implement:**
```python
@dataclass
class TweetVariant:
    text: str
    structural_move: str
    format_fit_score: float
    notes: str

def generate_tweet_variants(
    handle: str,
    org: str,
    format_bucket: str | None,
    topic: str | None,
    source_url: str | None,
    num_variants: int,
    meta_db_path: Path | None,
    vault_root: Path | None,
) -> list[TweetVariant]: ...

def _get_format_context(
    org: str,
    format_bucket: str,
    conn: sqlite3.Connection,
) -> tuple[str, list[dict]]:
    """Returns (trend_summary_string, structural_examples_list)."""

def _select_best_format(org: str, conn: sqlite3.Connection) -> str:
    """Return the highest-ranked active format from the live trend helper. Falls back to 'standalone_text'."""
```

**CLI output format:**
```
Generating 3 variants for @handle (standalone_text, topic: defi yields)
Using format trend: standalone_text surging at 2.3x (confidence A, last 7d)

── Variant 1 · Format fit: 9.0 ──────────────────────────────────────
Everyone's watching ETH gas. Nobody's watching funding rates.

When perp funding flips negative across 3 majors simultaneously, that's not noise.
That's the market telling you something.

Structure: contrarian misdirection → specific signal → implication
──────────────────────────────────────────────────────────────────────

── Variant 2 · Format fit: 8.0 ──────────────────────────────────────
...
```

**Tests (`tests/write/test_generator.py`):**
- Mock `call_claude_json`; assert it receives account context, structural examples, and topic.
- Assert 3 variants returned when `num_variants=3`, each has non-empty `text` and `structural_move`.
- Test format auto-selection: when no `--format` given, `_select_best_format()` returns the
  highest-ranked active bucket from the live trend helper.
- Test graceful fallback: when meta.db is empty, `generate_tweet_variants()` still returns
  variants (profile-only context, no crash).
- Test format_fit_score parsed correctly from Claude JSON response.
- Test 280-char limit note is in the system prompt for standalone_text format.
- Test that structural examples are NOT present in prompt when meta.db has no high-lift tweets
  (graceful omission, not crash).
- Test missing account: `require_account()` failure surfaces as a clean CLI error before any
  Claude call is attempted.

---

### FEATURE-2 · `sable score` — Hook Scorer

**Status:** Complete (2026-03-25).
**Completeness:** Medium-high for a standalone scorer. Integration into `sable write` should
be a second patch, not the first.
**Hard blockers:** Feature Gate; best done after `FEATURE-1` CLI shape is stable.

**Implementation slices (do in order):**
1. **Slice A — cache table + DB helpers + tests** ✓ **Done**
2. **Slice B — standalone scoring command** ✓ **Done**
3. **Slice C — `sable write --score` integration** ✓ **Done** (6 tests in `tests/write/test_write_score.py`)

**Post-implementation note:**
- `score_draft(draft, handle, format_bucket, patterns)` is the actual function name (not `score_hook` as originally specced)
- `get_hook_patterns(org, format_bucket)` owns its own DB connection internally (does not accept `conn` parameter)
- Slice C landed alongside Slice B: `sable write --score` flag wires `score_draft()` per variant with SableError fallback
- 18 tests total: 12 in `test_scorer.py`, 6 in `test_write_score.py`

**Purpose:** Scores a draft tweet's hook against structural patterns extracted from recent
high-performing watchlist posts. Usable standalone before posting, and as a pre-flight gate
inside `sable write`.

**Command syntax:**
```
sable score @handle --text "your draft tweet text" [--format standalone_text] [--org ORG]
```

**New files to create:**
- `sable/write/scorer.py` — pattern extraction + scoring logic
- `sable/commands/score.py` — top-level CLI entrypoint
- `tests/write/test_scorer.py`

**Existing files to modify:**
- `sable/cli.py` — register `score` top-level command
- `sable/pulse/meta/db.py` — add `hook_pattern_cache` table to `_SCHEMA` and migration
- `sable/commands/write.py` — optional only if/when adding a later `--score` integration

**New DB table in `meta.db`:**
```sql
CREATE TABLE IF NOT EXISTS hook_pattern_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    org TEXT NOT NULL,
    format_bucket TEXT NOT NULL,
    patterns_json TEXT NOT NULL,
    generated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_hook_patterns_key
    ON hook_pattern_cache (org, format_bucket);
```

Add this table to `pulse/meta/db.py::_SCHEMA`. Add `upsert_hook_patterns()` and
`get_hook_patterns()` DB functions to `pulse/meta/db.py`.

**Cache policy:** Re-generate patterns if cached entry is > 24 hours old OR if a newer
**successful** scan has completed since the last pattern generation.
- compare against `scan_runs.completed_at`, not `started_at`
- ignore failed scans (`claude_raw LIKE 'FAILED:%'`) when deciding invalidation
- this avoids thrashing the cache on failed or still-running scans

**Two-step process:**

**Step 1 — Pattern extraction** (Claude call, cached):
Pull top-20 tweets with `total_lift >= 2.5` for the format in last 30d. Claude call:
```
Here are 20 tweets that significantly outperformed their author's average engagement.
All are {format_bucket} format.

{tweet_list}

Identify 6-8 structural hook patterns that appear across these high performers.
For each pattern: name it, describe it in one sentence, give one example fragment.

Return JSON: { "patterns": [{"name": "...", "description": "...", "example": "..."}] }
```

**Step 2 — Scoring call** (Claude call, not cached):
```
Account voice profile:
{tone.md excerpt — first 200 chars only to keep prompt small}

High-performing hook patterns in {format_bucket} right now:
{patterns_list}

Draft tweet:
{draft_text}

Score this draft 1-10 on:
1. Hook strength (does it compel the read?)
2. Pattern match (does it use one of the known high-performing patterns?)
3. Voice fit (does it sound like the account?)

Return JSON:
{
  "grade": "B+",
  "score": 7.5,
  "matched_pattern": "contrarian opener",
  "voice_fit": 8,
  "flags": ["hook could be shorter", "second sentence is the real hook — move it first"],
  "suggested_rewrite": "..." // optional, include only if score < 7
}
```

**Functions to implement:**
```python
@dataclass
class HookPattern:
    name: str
    description: str
    example: str

@dataclass
class HookScore:
    grade: str        # A+ / A / B+ / B / C+ / C / D
    score: float      # 1-10
    matched_pattern: str | None
    voice_fit: int
    flags: list[str]
    suggested_rewrite: str | None

def get_hook_patterns(
    org: str,
    format_bucket: str,
    meta_db_conn: sqlite3.Connection,
) -> list[HookPattern]:
    """Return cached patterns or generate fresh if stale."""

def score_hook(
    draft: str,
    handle: str,
    format_bucket: str,
    patterns: list[HookPattern],
) -> HookScore: ...
```

**Tests (`tests/write/test_scorer.py`):**
- Pattern generation: given 5 high-lift tweets in meta.db, `get_hook_patterns()` calls Claude,
  stores patterns in `hook_pattern_cache`, returns non-empty list.
- Cache hit: call `get_hook_patterns()` twice. Assert Claude called exactly once (mock counter).
- Cache staleness: insert cache row with `generated_at` 25 hours ago. Assert patterns regenerated.
- Cache invalidation by new successful scan: insert a newer successful `scan_runs.completed_at`
  and assert regeneration occurs.
- Failed scan does **not** invalidate cache: insert a newer failed scan row and assert the
  cached patterns are still reused.
- Score: mock Claude returning grade="B+", score=7.5. Assert `HookScore` populated correctly.
- Score below 7: assert `suggested_rewrite` is present in returned `HookScore`.
- Integration with `sable write`: after implementing Feature 1, assert `sable write` output
  includes a hook score for each variant if `--score` flag passed.
- Edge case: format with < 5 high-lift tweets in meta.db → patterns generated from available
  data (no crash if fewer than 20 examples available).

---

### FEATURE-9 · `sable pulse attribution` — Content Attribution Report

**Status:** Done. All 3 slices landed. 12 new tests (4 Slice A + 8 Slice B), 376 total passing.
**Gate:** Feature Gate satisfied. Ready to implement — no remaining blockers.
**Completeness:** High. Full spec in `~/Downloads/Slopper_ContentAttribution_Prompt.md`.

**Purpose:** Answers "what fraction of this account's engagement came from Sable-produced
content, and did Pulse Meta-informed content outperform the baseline?" Deterministic
aggregation over existing pulse.db + meta.db data. No new tables, no Claude calls.

**Implementation slices (do in order):**
1. **Slice A — format_baselines time-series migration**
   - `sable/pulse/meta/db.py`: drop unique index on `(org, format_bucket, period_days)`;
     add non-unique time-series index; change `upsert_format_baseline` from INSERT OR
     REPLACE to plain INSERT; add `get_format_baselines_as_of(org, as_of_str, period_days=7)`
     helper; add `prune_format_baselines(org, keep_n=90)` to bound table growth
   - `tests/pulse/meta/test_db.py` (new or extend): time-series accumulation, as_of lookup,
     pruning, backward-compat for existing `get_format_baselines()` callers
2. **Slice B — ContentAttribution dataclass + compute function**
   - New file: `sable/pulse/attribution.py`
   - `ContentAttribution` dataclass + `compute_attribution(handle, days, pulse_db_path,
     meta_db_path)` function
   - 8 tests in `tests/pulse/test_attribution.py` (in-memory SQLite, all edge cases)
3. **Slice C — CLI + strategy brief integration**
   - `sable/pulse/cli.py`: add `sable pulse attribution @handle [--days N] [--format md|json]`
   - `sable/advise/stage1.py`: add `## Content Attribution` section (≥5 Sable posts gate)
   - Optional: `sable/vault/dashboard.py` + `sable/vault/templates/index.md.j2`

**Key design decisions (corrections from original spec):**
- CLI lives in `sable/pulse/cli.py`, not a nonexistent `sable/commands/pulse.py`
- SQL uses `s.id = (SELECT MAX(s2.id) ...)` latest-snapshot pattern (matches account_report.py)
- Engagement formula is weighted: `likes*1 + replies*3 + retweets*4 + quotes*5 + bookmarks*2 + views*0.5` (matches `_compute_lift` in stage1.py)
- Meta-informed classification requires Slice A; uses `get_format_baselines_as_of(org, post.posted_at)` not current-state baselines
- `clip` → format_bucket: check `sable_content_path + ".meta.json"` for `duration`; ≤60s → `short_clip`, >60s → `long_clip`; missing file → `short_clip`
- `## Content Attribution` section in stage1 sits after `## Post Performance`, before `## Pulse Meta Trends`
- Vault dashboard integration touches Jinja2 template `sable/vault/templates/index.md.j2`

---

### FEATURE-4 · Viral Anatomy Archive

**Status:** Complete (2026-03-25). All three slices landed.
**Completeness:** Done.
**Hard blockers:** None.

**Implementation slices:**
1. **Slice A — `viral_anatomies` table + analysis helper + tests** ✓ Done
2. **Slice B — vault note writing** ✓ Done
3. **Slice C — post-scan integration** ✓ Done (hook in `cli.py`)

**Post-implementation notes:**
- `anatomy.py` uses `analyze_viral_tweet()` (not `analyze_tweet()` as specced)
- `run_anatomy_enrichment(org, vault_root=None, max_per_run=10, min_lift=10.0)` — `vault_root` defaults to `vault_dir(org)` when `None`
- `text` field added to `ViralAnatomy` dataclass (needed for vault note body; not in original spec)
- Post-scan hook in `cli.py` calls `run_anatomy_enrichment(org)` — defaults handle path resolution
- Test count: 14 tests in `tests/pulse/meta/test_anatomy.py`

**Purpose:** When any watchlist account posts something with >= 10x author-relative lift,
auto-archive a structural breakdown as a vault note. Over time, builds a searchable pattern
library of what actually goes viral in the niche.

**Spec correction:** do **not** make this default-on in the first patch. First land the
helper, DB table, vault note writer, and tests. Then wire it into `pulse meta scan` once
failure behavior is proven safe.

**New files to create:**
- `sable/pulse/meta/anatomy.py` — analysis logic + vault note writing
- `tests/pulse/meta/test_anatomy.py`

**Existing files to modify:**
- `sable/pulse/meta/cli.py` — call anatomy enrichment after scan completes
- `sable/pulse/meta/db.py` — add `viral_anatomies` table to `_SCHEMA`
- `sable/vault/cli.py` — only if exposing `--type viral_anatomy` via the existing search CLI

**New DB table in `meta.db`:**
```sql
CREATE TABLE IF NOT EXISTS viral_anatomies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    org TEXT NOT NULL,
    tweet_id TEXT NOT NULL,
    author_handle TEXT NOT NULL,
    total_lift REAL NOT NULL,
    format_bucket TEXT NOT NULL,
    anatomy_json TEXT NOT NULL,
    analyzed_at TEXT NOT NULL,
    UNIQUE(org, tweet_id)
);
```

Add to `pulse/meta/db.py::_SCHEMA`. Add `save_anatomy()` and `get_unanalyzed_viral_tweets()`
functions to `db.py`.

**Anatomy JSON schema (stored in `anatomy_json` column):**
```json
{
  "hook_structure": "contrarian claim + specific number",
  "hook_length_words": 8,
  "first_sentence": "Nobody talks about this but...",
  "emotional_register": "confident",
  "topic_cluster": "DeFi yield farming",
  "has_cta": false,
  "cta_type": null,
  "retweet_bait": true,
  "retweet_bait_element": "invites disagreement",
  "is_thread": false,
  "thread_length": null
}
```

**Claude prompt for anatomy (one call per tweet, keep small):**
```
Analyze this crypto Twitter post. It achieved {lift}x its author's average engagement.

Post:
"{tweet_text}"

Return JSON with these exact fields:
- hook_structure: string (describe the structural pattern of the first sentence)
- hook_length_words: int
- first_sentence: string (the actual first sentence)
- emotional_register: one of [confident, anxious, excited, contemptuous, neutral, urgent]
- topic_cluster: string (1-3 words describing the topic)
- has_cta: bool
- cta_type: one of [implicit, explicit, null]
- retweet_bait: bool
- retweet_bait_element: string or null (e.g. "invites reply", "controversial claim")
- is_thread: bool
- thread_length: int or null
```

**Post-scan enrichment logic in `cli.py` (after helper is proven stable):**
```python
# After scan result is logged, before returning:
from sable.pulse.meta.anatomy import run_anatomy_enrichment
run_anatomy_enrichment(
    org=org,
    meta_db_path=meta_db_path(org),
    vault_root=vault_dir(org),
    max_per_run=config.get("max_anatomy_per_scan", 10),
    min_lift=config.get("anatomy_min_lift", 10.0),
)
```

**Vault note path:** `~/.sable-vault/{org}/content/viral_anatomy/{tweet_id}.md`
- this is important because `load_all_notes()` only scans `vault/content/**`
- if you instead write these notes outside `content/`, `vault search` will not see them
  unless the loader is explicitly widened and tested

**Vault note frontmatter:**
```yaml
---
id: viral_{tweet_id}
type: viral_anatomy
author: "@defichad"
format: standalone_text
lift: 9.3
hook_structure: "contrarian opener + specific timeline"
topic_cluster: "L2 fees"
analyzed_at: "2026-03-24T14:30:00+00:00"
---
```

Body: the full tweet text, followed by the anatomy fields as a structured markdown section.

**Vault search integration:** if you want `sable vault search --type viral_anatomy`, update:
- `sable/vault/cli.py` `--type` choices to include `viral_anatomy`
- any tests or docs that currently describe the content-type choices as only
  `clip | meme | faceswap | explainer`

**Functions to implement in `anatomy.py`:**
```python
@dataclass
class ViralAnatomy:
    tweet_id: str
    author_handle: str
    total_lift: float
    format_bucket: str
    hook_structure: str
    hook_length_words: int
    first_sentence: str
    emotional_register: str
    topic_cluster: str
    has_cta: bool
    cta_type: str | None
    retweet_bait: bool
    retweet_bait_element: str | None
    is_thread: bool
    thread_length: int | None
    analyzed_at: str

def run_anatomy_enrichment(
    org: str,
    meta_db_path: Path,
    vault_root: Path,
    max_per_run: int = 10,
    min_lift: float = 10.0,
) -> int:
    """Returns count of anatomies generated this run."""

def analyze_tweet(tweet: dict, org: str) -> ViralAnatomy:
    """Single Claude call to produce anatomy for one tweet."""

def write_anatomy_vault_note(anatomy: ViralAnatomy, vault_root: Path) -> Path:
    """Write vault note. Returns path written."""
```

**Cost guard:** Each anatomy call is ~150 input tokens + ~100 output tokens using
Haiku (~$0.000063/call). 10 calls = ~$0.00063/scan.
- still pass `org_id=org` and a real `call_type` (for example `pulse_meta_anatomy`) through
  `call_claude_json()`
- do **not** treat org-scoped anatomy analysis as budget-exempt
- `max_per_run` remains the hard cap regardless

**Tests (`tests/pulse/meta/test_anatomy.py`):**
- `test_analyze_tweet`: mock `call_claude_json` returning valid anatomy JSON. Assert
  `ViralAnatomy` dataclass populated with correct fields.
- `test_run_anatomy_enrichment_deduplication`: pre-populate `viral_anatomies` table with
  tweet_id=123. Call `run_anatomy_enrichment()` with that tweet in scanned_tweets. Assert
  Claude NOT called again for tweet_id=123.
- `test_max_per_run_cap`: populate meta.db with 15 tweets at >=10x lift. Assert only
  `max_per_run=10` anatomy calls made.
- `test_zero_viral_tweets_graceful`: meta.db has no tweets at >=10x. `run_anatomy_enrichment()`
  returns 0, no exception.
- `test_vault_note_written`: after `write_anatomy_vault_note()`, assert file exists at
  expected path and frontmatter contains `type: viral_anatomy`, `lift`, `format` fields.
- `test_vault_note_atomic`: mock `os.replace` to raise after tmp write. Assert original
  note (if it existed) is not corrupted. (Reuse `atomic_write` from `sable/shared/files.py`.)
- `test_post_scan_anatomy_failure_does_not_corrupt_scan_result`: once CLI wiring is added,
  inject an anatomy failure after a successful scan and assert the scan itself still
  completes with a logged warning.

---

### FEATURE-6 · `sable pulse meta digest` — Watchlist Intelligence Digest

**Status:** Complete (2026-03-25). All three slices landed in a prior session.
**Post-implementation notes:**
- `meta_db_path` and `vault_root` removed from `generate_digest` (were dead — uses `get_conn()`)
- CLI saves vault separately via `save_digest_to_vault(report, vault_dir(org))`
- 6 tests in `tests/pulse/meta/test_digest.py`

**Implementation slices (do in order):**
1. **Slice A — digest selection + cached anatomy consumption**
2. **Slice B — report rendering + optional save**
3. **Slice C — CLI wiring**

**Purpose:** Weekly curated report of the most structurally interesting posts from the
78-account watchlist. Each entry includes anatomy (structural breakdown + what to steal).
Saved as a vault report and printed to console.

**Command syntax:**
```
sable pulse meta digest --org tig [--period 7d] [--top 10] [--save]
```

**New files to create:**
- `sable/pulse/meta/digest.py` — digest generation logic
- `tests/pulse/meta/test_digest.py`

**Existing files to modify:**
- `sable/pulse/meta/cli.py` — add `digest` subcommand

**Vault note path:** `~/.sable-vault/{org}/digests/watchlist_digest_{YYYY-MM-DD}.md`

**Selection logic:**
```sql
SELECT st.text, st.author_handle, st.total_lift, st.format_bucket, st.tweet_id,
       va.anatomy_json
FROM scanned_tweets st
LEFT JOIN viral_anatomies va ON (va.tweet_id = st.tweet_id AND va.org = st.org)
WHERE st.org = ?
  AND st.total_lift >= 3.0
  AND st.posted_at >= ?
ORDER BY st.total_lift DESC
LIMIT ?
```
- compute the cutoff string in Python (for example `f"-{period_days} days"`) or precompute an
  ISO cutoff timestamp, then bind it directly
- do not rely on `? || ' days'` string concatenation in SQL

**Anatomy integration:** If `va.anatomy_json IS NOT NULL`, use the cached anatomy (no Claude
call). If NULL, call `anatomy.analyze_tweet()` inline. This means Feature 4 feeds Feature 6 —
running a scan before digest generation will pre-cache the analyses.

**Claude call for non-anatomy posts (one call per post, small):**
```
This crypto Twitter post achieved {lift}x average engagement.

Post by @{author}:
"{tweet_text}"

In 3 sentences: (1) What structural move is it making? (2) What should we steal from it?
(3) What's the hook pattern in one phrase?

Return JSON: {"analysis": "...", "steal": "...", "hook_pattern": "..."}
```

**Digest output format:**
```markdown
## Watchlist Digest — Week of Mar 24, 2026

*10 posts with 3x+ lift from 78 watched accounts · Generated 2026-03-24*

---

### 1. @defichad — 9.3x lift — standalone_text

> Nobody talks about this but ETH L2 sequencer fees are going to zero in 18 months.
> [continue...]

**Hook pattern:** Contrarian + specific timeline
**What to steal:** The "nobody talks about X but Y will Z in N months" frame works for
any DeFi macro narrative where you have a specific directional claim.

---

### 2. @fejau_inc — 7.1x lift — thread

> Three things that will define crypto in Q2 2025: [thread excerpt]

**Hook pattern:** Numbered list + quarter-specific framing
**What to steal:** "N things that will define X in [specific time window]" is reliably
high-curiosity when the N is credible and time-bounded.

---
```

**Dataclass models:**
```python
@dataclass
class DigestEntry:
    rank: int
    author_handle: str
    total_lift: float
    format_bucket: str
    tweet_text: str
    hook_pattern: str
    analysis: str
    steal: str

@dataclass
class DigestReport:
    org: str
    period_days: int
    generated_at: str
    entries: list[DigestEntry]
    total_posts_considered: int  # how many tweets in period before top-N filter
```

**Functions to implement in `digest.py`:**
```python
def generate_digest(
    org: str,
    period_days: int,
    top_n: int,
    meta_db_path: Path,
    vault_root: Path | None,
) -> DigestReport: ...

def _get_digest_posts(
    org: str,
    period_days: int,
    top_n: int,
    conn: sqlite3.Connection,
) -> list[dict]: ...

def _analyze_post_for_digest(post: dict) -> tuple[str, str, str]:
    """Returns (hook_pattern, analysis, steal). Uses cached anatomy if available."""

def render_digest(report: DigestReport) -> str: ...

def save_digest_to_vault(report: DigestReport, vault_root: Path) -> Path: ...
```

**Persistence note:** saving the digest under `digests/` is fine for a report artifact, but
that location is **not** part of `load_all_notes()` and therefore not searchable through the
existing content search path. Treat the digest as a report, not as content inventory.

**Tests (`tests/pulse/meta/test_digest.py`):**
- `test_top_n_filtering`: populate meta.db with 20 posts with varying lifts >= 3.0.
  `_get_digest_posts(top_n=10)` returns exactly 10, highest lift first.
- `test_anatomy_cache_used`: insert a tweet in both `scanned_tweets` and `viral_anatomies`.
  `_analyze_post_for_digest()` reads from anatomy_json, does NOT call Claude.
- `test_anatomy_cache_miss_calls_claude`: tweet in `scanned_tweets` but not `viral_anatomies`.
  Assert Claude called exactly once.
- `test_empty_period`: no posts with lift >= 3.0 in period. `generate_digest()` returns
  `DigestReport` with empty `entries`, no exception.
- `test_vault_note_saved`: `save_digest_to_vault()` creates file at expected path with
  correct frontmatter (`type: digest`, `org`, `period_days`, `generated_at`).
- `test_render_output`: `render_digest()` produces non-empty string with correct header and
  each entry's author handle visible.
- Any inline analysis miss should pass `org_id=org` and a distinct `call_type`
  (for example `pulse_meta_digest`) through the shared Claude wrapper.

---

### FEATURE-7 · `sable calendar` — Content Calendar

**Status:** ✓ Complete (2026-03-26). 388 passed · 0 ruff.
**Completeness:** Full. Slices A+B+C implemented against live codebase.

**Implementation slices (do in order):**
1. **Slice A — deterministic inputs + tests**
   - posting history helper
   - vault inventory helper with real note semantics
   - trend summary helper
2. **Slice B — planning core + rendering**
3. **Slice C — CLI wiring + optional save path**

**Purpose:** Given an account and time horizon, generates a concrete posting schedule that
balances format diversity, niche trend alignment, and what's already ready in the vault.

**Command syntax:**
```
sable calendar @handle --days 7 [--formats-target 4] [--org ORG] [--save]
```

**New files to create:**
- `sable/calendar/__init__.py`
- `sable/calendar/planner.py` — calendar logic
- `sable/commands/calendar.py` — CLI entrypoint
- `tests/calendar/test_planner.py`

**Existing files to modify:**
- `sable/cli.py` — register `calendar` top-level command

**No new database tables.** Reads pulse.db, meta.db, vault filesystem.

**Three inputs assembled before the Claude call:**

1. **Posting history** (last 14d from pulse.db):
   ```sql
   SELECT p.posted_at, p.sable_content_type, s.likes, s.retweets, s.views
   FROM posts p
   LEFT JOIN snapshots s ON (p.id = s.post_id AND s.id = (
       SELECT MAX(s2.id) FROM snapshots s2 WHERE s2.post_id = p.id
   ))
   WHERE p.account_handle = ? AND p.posted_at >= datetime('now', '-14 days')
   ORDER BY p.posted_at DESC
   ```
   Compute: posts per day average, format distribution over 14d, days since last post per
   **format bucket** after mapping `sable_content_type` through the same helper used by
   `FEATURE-3`.

2. **Vault inventory** (unposted content assigned to this account):
   ```python
   notes = load_all_notes(vault_root / org)
   ready = [
       {
           "note_id": n.get("id"),
           "path": n.get("_note_path"),
           "type": n.get("type"),
           "format": n.get("format"),
           "topic": n.get("topic"),
           "assembled_at": n.get("assembled_at"),
       }
       for n in notes
       if n.get("type") in ("clip", "meme", "explainer", "faceswap")
       and not n.get("posted_by")
       and (
           n.get("account") == handle
           or handle in (n.get("suggested_for") or [])
       )
   ]
   ```
   - there is no canonical `status` field; use `posted_by` emptiness plus
     `account` / `suggested_for` membership instead
   - if recency matters, use `assembled_at`, not a nonexistent `created_at` frontmatter field

3. **Format trends** from meta.db (same query as Feature 1):
   reuse the live trend helper / `FEATURE-3` adapter; do not query nonexistent
   `current_lift` columns from `format_baselines`.

**Claude call:**

System: minimal (no account profile needed for scheduling logic)

User:
```
Account: @{handle}, org: {org}
Planning horizon: {days} days starting {start_date}
Format diversity target: at least {formats_target} distinct formats

Posting history (last 14d):
{history_summary}

Content ready in vault:
{vault_inventory_list}

Current niche format trends:
{trends_summary}

Generate a {days}-day posting calendar. For each day, suggest 1-2 slots.
For each slot, use vault content when available (mark action as "post_ready").
For slots needing new content, mark action as "create" with a topic suggestion.
Do not schedule declining formats (lift < 0.8x) more than once per week.

Return JSON:
{
  "days": [
    {
      "date": "YYYY-MM-DD",
      "day_name": "Monday",
      "slots": [
        {
          "format_bucket": "...",
          "topic_suggestion": "...",
          "action": "post_ready" | "create",
          "vault_note_id": "..." | null,
          "rationale": "..."
        }
      ]
    }
  ],
  "summary": {
    "formats_covered": [...],
    "vault_items_scheduled": N,
    "creation_tasks": N
  }
}
```

**Dataclass models:**
```python
@dataclass
class CalendarSlot:
    format_bucket: str
    topic_suggestion: str
    action: str              # "post_ready" | "create"
    vault_note_id: str | None
    rationale: str

@dataclass
class CalendarDay:
    date: str
    day_name: str
    slots: list[CalendarSlot]

@dataclass
class CalendarPlan:
    handle: str
    org: str
    days: list[CalendarDay]
    formats_covered: list[str]
    vault_items_scheduled: int
    creation_tasks: int
    generated_at: str
```

**Functions to implement:**
```python
def build_calendar(
    handle: str,
    org: str,
    days: int,
    formats_target: int,
    pulse_db_path: Path,
    meta_db_path: Path | None,
    vault_root: Path | None,
) -> CalendarPlan: ...

def _get_posting_history(handle: str, days: int, conn: sqlite3.Connection) -> dict: ...

def _get_vault_inventory(handle: str, org: str, vault_root: Path) -> list[dict]: ...

def render_calendar(plan: CalendarPlan) -> str: ...
```

**Output format:**
```
@handle — 7-Day Content Calendar (Mon Mar 25 → Sun Mar 31)

Mon Mar 25
  ① standalone_text · "perp funding rate inversion" · CREATE
    Why: standalone_text surging at 2.3x; account hasn't posted text-only in 4 days
  ② [optional 2nd slot if vault has content ready]

Tue Mar 26
  ① short_clip · "L2 scaling explained" · POST READY → clips/l2_scaling_032024.mp4
    Why: clip in vault assigned to this account, topic aligned with niche signals

...

Summary: 7 formats across 7 days · 3 vault pieces scheduled · 4 new creation tasks
```

**Tests (`tests/calendar/test_planner.py`):**
- `test_vault_content_scheduled`: add 3 unposted vault notes for @handle; assert at least
  2 slots have `action="post_ready"` in returned plan.
- `test_format_diversity`: with `formats_target=4`, assert `len(plan.formats_covered) >= 4`.
- `test_declining_format_capped`: inject meta.db with `single_image` at lift=0.6x.
  Assert `single_image` appears at most once in 7-day plan.
- `test_empty_vault`: `_get_vault_inventory()` with no vault directory → returns `[]`,
  no exception.
- `test_empty_pulse_db`: `_get_posting_history()` with no posts → returns empty dict,
  calendar still generated using Claude with "no history" context.
- `test_render_calendar`: `render_calendar()` produces non-empty string with handle and
  day names.
- `test_get_vault_inventory_uses_posted_by_and_suggested_for`: prove the helper excludes
  already-posted notes and includes notes suggested for the handle even when `account`
  differs.
- if `--save` is implemented, save under a report/planning path such as
  `playbooks/calendar_<handle>_<date>.md` using `atomic_write()`; do not put calendars into
  `content/` unless they are intentionally part of searchable inventory.

---

### FEATURE-8 · `sable diagnose` — Full Account Audit

**Status:** Complete (2026-03-25). 12 tests · 0 ruff · 0 mypy.
**Completeness:** All five audit sections implemented and tested.

**Implementation slices (do in order):**
1. **Slice A — deterministic section helpers + tests** ✓ **Done**
2. **Slice B — report assembly + rendering** ✓ **Done**
3. **Slice C — CLI wiring + artifact save path** ✓ **Done**

**Post-implementation notes:**
- `save_diagnosis_artifact(report, org)` — no `conn` parameter; function opens its own sable.db connection
- All 5 audit sections match spec: format portfolio, topic freshness, vault utilization, cadence, engagement trend
- 12 tests in `tests/diagnose/test_runner.py` — all spec tests landed
- Helper `_norm_handle()` and `_age_days()` added as private utilities (not in spec, necessary for correctness)

**Purpose:** Backward-looking audit of one managed account. Identifies structural problems
(format over-indexing, topic gaps, vault waste, cadence issues) that the weekly brief
doesn't surface. Not a forward plan — a diagnosis.

**Command syntax:**
```
sable diagnose @handle [--org ORG] [--days 30]
```

**New files to create:**
- `sable/diagnose/__init__.py`
- `sable/diagnose/runner.py` — all audit logic
- `sable/commands/diagnose.py` — CLI entrypoint
- `tests/diagnose/test_runner.py`

**Existing files to modify:**
- `sable/cli.py` — register `diagnose` top-level command

**No new database tables.** Reads pulse.db, meta.db, sable.db, vault filesystem.
Saves diagnosis as an artifact in sable.db (`artifact_type='account_diagnosis'`).
- if persistence is implemented, prefer creating a lightweight `diagnose` job and inserting
  the artifact through the existing jobs/artifacts flow rather than inventing a second save path

**Five audit sections:**

**Section 1 — Format portfolio health:**
Use Feature 3 logic (`compute_account_format_lift()`). Flag:
- Over-indexed: any single format accounts for > 50% of posts → WARNING
- Primary format declining: if account's top-format has niche_lift < 0.8x → WARNING
- Format gap: niche has ≥ 1 surging format (lift >= 1.5x) never used by account → INFO

**Section 2 — Topic freshness:**
- Extract account's recent topics: tokenize last 20 post texts (basic bigram extraction;
  prefer nouns and ticker symbols). Compute top-5 account topics by frequency.
- Load niche topic signals from meta.db `topic_signals` table (top-10 by `avg_lift * unique_authors`).
- Flag: niche has topic in top-5 signals not present in account's last-20 posts → INFO
- Flag: account's top-1 topic not in niche top-10 signals → INFO (possible differentiation,
  not necessarily bad)
- Note: do NOT use Claude for topic extraction. Use simple regex tokenizer.

**Section 3 — Vault utilization:**
```python
all_notes = load_all_notes(vault_root / org)
account_notes = [
    n for n in all_notes
    if n.get("account") == handle or handle in (n.get("suggested_for") or [])
]
unposted = [n for n in account_notes if not n.get("posted_by")]
stale_unposted = [n for n in unposted if age_days(n.get("assembled_at")) > 7]
```
Flag: `len(stale_unposted) > 0` → "N pieces of content older than 7 days not yet posted" → WARNING
Flag: any unposted note has `topic` matching a niche top-5 signal → "Unposted content on hot
topic '{topic}' is sitting unused" → WARNING
- there is no canonical vault `status` field in live notes
- use `assembled_at`, not a nonexistent `created_at`, for stale inventory checks

**Section 4 — Posting cadence:**
From pulse.db:
```sql
SELECT DATE(posted_at) as post_date, COUNT(*) as post_count
FROM posts
WHERE account_handle = ? AND posted_at >= datetime('now', '-30 days')
GROUP BY DATE(posted_at)
ORDER BY post_date
```
- Average posts per day over window
- Max posts in a single day
- Number of days with zero posts in window
- Longest dry spell (consecutive days with no posts)

Flag: `avg_posts_per_day > 3` → "High posting rate may dilute per-post engagement" → INFO
Flag: `avg_posts_per_day < 0.5` → "Low activity: averaging less than 1 post every 2 days" → WARNING
Flag: `longest_dry_spell >= 5` → "Longest dry spell: {N} days" → WARNING

**Section 5 — Engagement trend:**
From pulse.db snapshots, compute rolling 7d average engagement for last 4 weeks.
Flag: week-over-week engagement drop > 20% for two consecutive weeks → "Engagement declining
for 2+ weeks" → WARNING.
If fewer than 10 posts in window, skip this section with "insufficient data" note.

**Output format (console + saved to sable.db artifact):**
```
Diagnosis: @handle (last 30d) — Generated 2026-03-24

═══ Format Portfolio ════════════════════════════════════════════
  ✅ standalone_text dominant (48%) — currently surging in niche (aligned)
  ⚠  thread: niche rising (1.7x) but you're flat (0.9x) — execution gap
  ⚠  short_clip: niche surging (2.1x) — you've never posted this format

═══ Topic Freshness ═════════════════════════════════════════════
  ℹ  Niche trending: "solana infra" — not in your last 20 posts
  ℹ  Your top topic "ETH gas" ranks #12 in niche signals (moderate alignment)

═══ Vault Utilization ══════════════════════════════════════════
  ⚠  7 unposted pieces older than 7 days
  ⚠  2 unposted clips on "L2 scaling" — currently in niche top-5 signals

═══ Posting Cadence ════════════════════════════════════════════
  ✅ 1.2 posts/day average (healthy)
  ⚠  Longest dry spell: 6 consecutive days (Mar 10–15)

═══ Engagement Trend ═══════════════════════════════════════════
  ⚠  Engagement dropped 28% week-over-week (weeks ending Mar 17, Mar 24)

─── Summary ────────────────────────────────────────────────────
  3 warnings, 2 info items
  Saved as diagnosis artifact {artifact_id}
```

**Dataclass models:**
```python
from enum import Enum

class FindingSeverity(Enum):
    WARNING = "warning"
    INFO = "info"
    OK = "ok"

@dataclass
class Finding:
    section: str
    severity: FindingSeverity
    message: str
    detail: str | None = None

@dataclass
class DiagnosisReport:
    handle: str
    org: str
    days: int
    generated_at: str
    findings: list[Finding]
    artifact_id: str | None = None  # set after saving to sable.db
```

**Functions to implement:**
```python
def run_diagnosis(
    handle: str,
    org: str,
    days: int,
    pulse_db_path: Path,
    meta_db_path: Path | None,
    vault_root: Path | None,
    sable_db_path: Path,
) -> DiagnosisReport: ...

def _audit_format_portfolio(handle, org, days, pulse_db_path, meta_db_path) -> list[Finding]: ...
def _audit_topic_freshness(handle, org, pulse_db_path, meta_db_path) -> list[Finding]: ...
def _audit_vault_utilization(handle, org, vault_root, meta_db_path) -> list[Finding]: ...
def _audit_posting_cadence(handle, pulse_db_path, days) -> list[Finding]: ...
def _audit_engagement_trend(handle, pulse_db_path) -> list[Finding]: ...

def render_diagnosis(report: DiagnosisReport) -> str: ...

def save_diagnosis_artifact(report: DiagnosisReport, conn: sqlite3.Connection, org: str) -> str:
    """Saves to sable.db artifacts table. Returns artifact_id."""
```

**Tests (`tests/diagnose/test_runner.py`):**
- `test_format_over_indexing`: 80% of posts are standalone_text → WARNING finding in section 1.
- `test_format_execution_gap`: niche thread lift=1.7x (from meta.db), account thread lift=0.9x
  → "execution gap" WARNING finding.
- `test_format_gap`: niche has short_clip surging, no short_clip posts in pulse.db for @handle
  → "never used" INFO finding.
- `test_topic_gap`: meta.db has "solana infra" as top signal, not in last 20 post texts
  → INFO finding.
- `test_vault_stale_unposted`: 5 vault notes for @handle with `assembled_at` 10 days ago and
  empty `posted_by` → WARNING with count=5.
- `test_vault_hot_topic_unposted`: vault note with `topic="L2 scaling"` matches meta.db
  topic signal → WARNING.
- `test_cadence_dry_spell`: pulse.db has no posts for 7 consecutive days → WARNING.
- `test_cadence_low_activity`: 5 posts in 30 days (avg < 0.2/day) → WARNING.
- `test_engagement_trend_declining`: week-over-week snapshots show 30% drop for 2 weeks
  → WARNING.
- `test_all_clear`: healthy account data → 0 warnings, only OK/INFO findings, no exception.
- `test_artifact_saved`: `save_diagnosis_artifact()` writes to sable.db; confirm row in
  artifacts with correct `artifact_type='account_diagnosis'` and org.
- `test_insufficient_data_graceful`: pulse.db has 3 posts (< 10 threshold for engagement
  trend) → section 5 returns INFO "insufficient data", no crash.

---

### FEATURE-ADVISE-EXPORT · MED · `sable advise --export`

**Status:** ✓ Complete (2026-03-26). Tests pass.
**Gate:** Feature Gate satisfied. Independent of any other open feature — can be implemented
in a single session.

**What:** Add an `--export` flag to `sable advise` that writes the full strategy brief
(exactly as rendered to terminal) to `./output/advise_<org>_<YYYY-MM-DD>.md` using the
existing `atomic_write()` utility from `sable/shared/files.py`.

**Why:** Operators need to share briefs asynchronously (Slack, async review) without
copy-pasting from terminal output. This is an operator-facing flag — no field stripping,
no client-sanitization.

**Files to touch:**
- `sable/advise/generate.py` — add `--export` flag to the `generate_brief()` entrypoint;
  after rendering the terminal string, call `atomic_write()` to write it to the output path
- `sable/shared/files.py` — `atomic_write()` already exists; no changes needed unless the
  output directory creation requires a guard (add `output_path.parent.mkdir(parents=True,
  exist_ok=True)` before the write if not already present)

**Command syntax:**
```
sable advise tig --export
# produces: ./output/advise_tig_2026-03-26.md
```

**Expected outcome:** Running `sable advise tig --export` writes
`./output/advise_tig_<YYYY-MM-DD>.md` with identical content to what is printed to
terminal. The file is created atomically (temp → replace). Running without `--export`
behaves exactly as before.

**Constraints:**
- Do NOT strip `sable_verdict`, cost data, or operator notes — the exported file is the
  full operator brief, not a client-readable version.
- Do NOT implement a separate `--client-brief` variant as part of this item.
- Output directory is `./output/` relative to the working directory (not `~/.sable/`).
- Date in filename is the generation date in `YYYY-MM-DD` format (local date is fine).
- Use `atomic_write()` from `sable/shared/files.py` — do not open/write directly.

**Tests:**
- Mock `atomic_write`; assert it is called with a path matching
  `output/advise_<org>_<date>.md` and content equal to the rendered terminal string.
- Assert running without `--export` does NOT call `atomic_write`.
- Assert the output path parent directory is created if absent.

**Gotchas:** The rendered string and the file content must be byte-for-byte identical —
do not re-render or post-process before writing. Confirm `atomic_write` signature before
wiring (check `sable/shared/files.py`).

---

### FEATURE-PULSE-META-SKIP-FRESH · MED · `sable pulse meta scan --skip-if-fresh` + `status`

**Status:** ✓ Done (2026-03-26). --skip-if-fresh and status subcommand fully implemented.
**Gate:** Feature Gate satisfied. Independent of other open features.

**What:**
(a) Add `--skip-if-fresh N` flag to `sable pulse meta scan` that skips the scan if the
last successful scan for this org completed within the last N hours.
(b) Add `sable pulse meta status` subcommand that prints a table of org / last_scan_at /
scan_count for all orgs in the meta.db `scan_runs` table.

**Why:** Operators re-run scans out of habit, burning SocialData spend unnecessarily ($0.002
per request). `--skip-if-fresh` prevents redundant API calls. `status` gives operators a
fast way to see when scans last ran without querying the DB manually.

**Files to touch:**
- `sable/pulse/meta/commands.py` — add `--skip-if-fresh N` to the `scan` command; add new
  `status` subcommand
- `sable/pulse/meta/db.py` — `get_latest_successful_scan_at(org)` already exists; confirm
  its return type and use it directly. For `status`, add
  `get_scan_summary_all_orgs() -> list[dict]` returning rows with `org`, `last_scan_at`,
  `scan_count`.

**Expected outcomes:**

`--skip-if-fresh`:
```
sable pulse meta scan tig --skip-if-fresh 12
# if last successful scan was 3h ago:
Scan skipped: last scan 3h ago (within 12h window)
# exits 0
```
If the last successful scan was more than N hours ago (or no scan exists), proceeds
normally.

`status`:
```
sable pulse meta status
# prints:
org      last_scan_at              scan_count
tig      2026-03-26T08:14:22+00:00     47
psy      2026-03-25T21:03:11+00:00     12
```

**Critical constraint:** `--skip-if-fresh` must bail out BEFORE `create_scan_run()` is
called. If the skip check happens after the scan row is created, an orphaned scan row with
no completion is written to meta.db. The check must be the first thing that runs after
argument parsing, before any DB write.

**Tests:**
- `test_skip_if_fresh_skips_when_recent`: insert a successful `scan_runs` row 3h ago.
  Assert `create_scan_run()` is NOT called when `--skip-if-fresh 12` is set.
- `test_skip_if_fresh_runs_when_stale`: insert a successful `scan_runs` row 15h ago.
  Assert scan proceeds normally when `--skip-if-fresh 12` is set.
- `test_skip_if_fresh_runs_when_no_history`: no scan rows in DB. Assert scan proceeds
  normally (no history = not fresh).
- `test_skip_exit_code_is_zero`: confirm the skip path exits 0, not 1.
- `test_status_table`: populate scan_runs with 2 orgs, multiple rows each. Assert
  `status` output contains correct org names, most-recent `completed_at`, and correct
  scan counts.
- `test_status_empty_db`: no scan rows. Assert `status` prints an empty table or a
  "no scans yet" message, no exception.

**Gotchas:** `get_latest_successful_scan_at()` likely returns an ISO string or `None`.
Confirm the return type and do the timestamp arithmetic in Python (parse to datetime,
compute `datetime.now(timezone.utc) - last_scan_at`, compare to `timedelta(hours=N)`).
Do not use string comparison for time arithmetic.

---

### FEATURE-ONBOARD-PREP · MED · `sable onboard --prep`

**Status:** ✓ Done. Implemented 2026-03-26.
**Gate:** Feature Gate satisfied. Independent of other open features.

**Clarification (2026-03-26):** There are two distinct `onboard` features:
1. **6-step prospect_yaml pipeline** — `sable onboard <prospect.yaml>` — ✓ **Complete**. Implemented in `sable/commands/onboard.py` as `run_onboard()`. Takes a prospect YAML and runs a full 6-step onboarding pipeline. This is already shipped.
2. **Simple `--prep` stub-creator** — `sable onboard --prep <handle> <org>` — ✓ **Complete** (2026-03-26). Implemented as `_run_prep()` + `--prep`/`--handle`/`--org-slug` flags in `sable/commands/onboard.py`. 5 tests in `tests/onboard/test_onboard.py` (tests 16–20).

**What (--prep stub-creator only):** New `--prep` flag on `sable onboard` that:
(a) Creates `~/.sable/profiles/@<handle>/` with four stub files — `tone.md`,
`interests.md`, `context.md`, `notes.md` — each containing guiding questions to prompt
the operator filling them in.
(b) Adds the org to `pulse.db` via `migrate()` + `create_org()` (ensuring the schema
exists before any insert).

**Why:** Onboarding new accounts (PSY Protocol, Flow L1) currently requires manually
creating the profile directory and stub files, then separately ensuring pulse.db is ready.
This command makes onboarding repeatable and ensures the DB is in the correct state before
any other `sable` command is run for the new account.

**Files to touch:**
- `sable/commands/onboard.py` — extend existing file; add `--prep` flag as an alternative
  mode alongside the existing prospect_yaml pipeline
- `sable/pulse/db.py` — use `migrate()` + `create_org()` (confirm these exist and their
  signatures before wiring)

**Command syntax:**
```
sable onboard --prep @psy_handle psy
```

**Stub file content (guiding questions, not blank files):**

`tone.md`:
```markdown
# Tone

<!-- Describe this account's voice. Examples:
- Confident and direct. Never hedges.
- Uses crypto-native slang but stays readable.
- Technical when explaining mechanisms; plain English for takes.
-->
```

`interests.md`:
```markdown
# Interests

<!-- List the topics this account posts about. Examples:
- DeFi yields and risk management
- L2 scaling narratives
- On-chain data interpretation
-->
```

`context.md`:
```markdown
# Account Context

<!-- Background on who this account represents. Examples:
- Founder at XYZ protocol. Background in TradFi before going on-chain.
- Anonymous. Known for contrarian macro takes.
-->
```

`notes.md`:
```markdown
# Operator Notes

<!-- Running notes for Sable operators. Examples:
- Avoid mentioning competitors by name.
- Client prefers threads over standalone text for complex topics.
-->
```

**Expected outcome:**
```
sable onboard --prep @psy_handle psy
# creates:
~/.sable/profiles/@psy_handle/tone.md
~/.sable/profiles/@psy_handle/interests.md
~/.sable/profiles/@psy_handle/context.md
~/.sable/profiles/@psy_handle/notes.md
# adds org "psy" to pulse.db
# prints: "Profile created: ~/.sable/profiles/@psy_handle/"
```

**Idempotency:** Second run must print `"Profile already exists, skipping"` and NOT
overwrite any existing files. The `create_org()` call should be idempotent (INSERT OR
IGNORE or equivalent) — running twice does not error.

**Tests:**
- `test_prep_creates_profile_directory`: assert all 4 stub files created at correct paths.
- `test_prep_stub_content`: assert each stub file contains the section header and at least
  one comment line (not blank).
- `test_prep_idempotent_no_overwrite`: run `--prep` twice. Assert second run does NOT
  overwrite the files (check modification time or inject sentinel content before re-run).
- `test_prep_prints_skip_message_on_second_run`: assert stdout contains "already exists"
  on second run.
- `test_prep_calls_migrate_before_create_org`: mock `migrate()` and `create_org()`; assert
  `migrate()` is called before `create_org()`.
- `test_prep_handle_normalization`: `@psy_handle` and `psy_handle` (no leading @) both
  produce directory `@psy_handle` (with @).

**Gotchas:**
- Call `migrate()` on pulse.db BEFORE any insert — do not assume the schema exists.
- Profile directory name must include the leading `@` (e.g. `@psy_handle`), matching the
  pattern used by all existing profile lookups in the codebase.
- Use `field(default_factory=list)` pattern for any new dataclasses introduced.
- Guard against re-running on an already-initialized profile by checking whether the
  directory exists BEFORE creating any files.
- Do NOT use `create_org()` from sable.db platform layer — this is `pulse.db` org
  registration. Confirm which module owns the pulse.db org create helper.

---

### Shared Infrastructure Notes

**All features must follow these patterns (already established in codebase):**

- API keys loaded from env vars or `~/.sable/config.yaml` — never hardcoded
- Claude calls use `sable/shared/api.py::call_claude_json()` or `call_claude()`
- org-scoped Claude calls pass `org_id` and a meaningful `call_type`
- non-org call sites annotated with `# budget-exempt: <reason>` comment
- File writes use `sable/shared/files.py::atomic_write()` for any markdown/JSON output
- Config values accessed via `sable.config.get(...)`, `load_config()`, or `require_key()`
- keep DB access consistent with the surrounding module
  - local helper modules can own short-lived connections
  - CLI orchestration can pass an existing connection when the repo already follows that pattern
  - do **not** invent a second DB-access style inside the same feature
- All `except Exception` blocks must `logger.warning(...)` — no silent swallows
- `load_all_notes()` only covers `vault/content/**`
  - if a feature expects search/discovery through existing vault tooling, write notes there or
    widen the loader and CLI deliberately with tests

**New modules (`write/`, `calendar/`, `diagnose/`) should follow existing module pattern:**
- `__init__.py` (empty or exports)
- Main logic file (generator.py, planner.py, runner.py)
- CLI command module in `sable/commands/`
- registration in `sable/cli.py`
- Tests in `tests/{module_name}/`

**Pulse/meta DB migrations:** Features 2 and 4 add tables to `meta.db`. These must be
added to `pulse/meta/db.py::_SCHEMA` string so `migrate()` creates them automatically.
Do NOT add them as separate migration files — meta.db uses `_SCHEMA` executescript, not
the migration runner used by sable.db.

---

### Validation Checklist (run after each patch set, and again after each feature)

Do **not** wait until the whole feature suite is “done.” Run this after every feature slice.

```bash
# Full test suite — must stay green, no regressions
./.venv/bin/python -m pytest -q

# Lint — must stay at 0 violations
./.venv/bin/ruff check .

# Type check — must stay at 0 errors
./.venv/bin/mypy sable

# Smoke test: new commands registered and help strings visible
sable write --help
sable score --help
sable pulse account --help
sable pulse meta digest --help
sable calendar --help
sable diagnose --help

# Smoke test: commands handle missing data gracefully
sable write @nonexistent_handle 2>&1 | grep -i "not found\|no account"
sable pulse account @handle --days 30  # with empty pulse.db — should print "no data"
sable diagnose @handle  # with empty dbs — should print report with "insufficient data" notes
```

---

## Simplify / Dead Code (AR-6 batch, 2026-03-26)

Small, low-risk cleanup items. Each can be implemented in isolation. Run full validation
after each one. These do NOT require a feature gate — they can be done at any time.

### ✓ Done — SIMPLIFY-DEAD-ATOMIC-WRITE · `vault/platform_sync.py`

**What:** `_atomic_write()` is defined in `sable/vault/platform_sync.py` but has zero call
sites anywhere in the codebase. The active pattern in the same file is `_write_to_temp()`.

**Why:** Dead code increases cognitive load and risks being accidentally called instead of
the live utility in `sable/shared/files.py`. Removing it reduces confusion.

**Files:** `sable/vault/platform_sync.py`

**Fix:**
1. `grep -r "_atomic_write"` (or `rg _atomic_write`) across the repo to confirm zero call
   sites before deleting.
2. Remove the `_atomic_write()` function definition (~11 lines).
3. The active `_write_to_temp()` function is unaffected — do NOT touch it.

**Expected outcome:** `_atomic_write` does not exist in the codebase. `ruff` and `mypy`
still pass. No test references `_atomic_write`.

**Gotchas:** Confirm no test imports or calls `_atomic_write` before removing. If any test
does reference it, update the test to use `_write_to_temp` or `atomic_write` from
`sable/shared/files.py` instead.

---

### ✓ Done — SIMPLIFY-HANDLE-NORM-TODO · `shared/utils.py` (or nearest normalization site)

**What:** Handle normalization (strip leading `@`, lowercase) is duplicated inline at 20+
sites across the codebase. This item does NOT implement the extraction — it only adds a
tracked TODO comment at one representative site.

**Why:** If the normalization logic ever changes, all 20+ inline sites must be found and
updated. A single tracked comment makes the consolidation findable and scoped.

**Files:** `sable/shared/utils.py` (or the most central existing normalization site in the
codebase if `utils.py` does not exist — check `sable/shared/paths.py` or
`sable/advise/stage1.py` for `_norm_handle`)

**Fix:** Add the following comment at one representative normalization site:
```python
# TODO(codex): consolidate handle normalization into sable/shared/utils.py
# Pattern: strip leading @, lowercase. Currently duplicated 20+ sites inline.
# Implement as normalize_handle(h: str) -> str. Low risk, high cosmetic value.
```

**Expected outcome:** The comment exists at exactly one location. No code is changed, no
function is extracted.

**Gotchas:** Do NOT implement the extraction now — that is explicitly out of scope.
Do NOT touch other modules to add the same comment — one site only. The extraction itself
violates AGENTS.md ("do not refactor untouched modules") and must wait for a dedicated
multi-file refactor pass.

---

### ✓ Done — SIMPLIFY-DIAGNOSE-THRESHOLD-CONSTANTS · `diagnose/runner.py`

**What:** Three analytically opaque float thresholds in `sable/diagnose/runner.py` are
hardcoded with no names, making their meaning unclear to future maintainers.

**Why:** Named module-level constants make thresholds self-documenting and easier to
calibrate without hunting through logic blocks.

**Files:** `sable/diagnose/runner.py`

**Fix:**
1. Read `sable/diagnose/runner.py` first to confirm the exact values and the context they
   appear in.
2. Extract these three constants to module level (top of file, after imports):
   - `_FORMAT_OVERINDEX_RATIO = 0.50` — used in the format over-index detection logic
     (Section 1: flags when any single format accounts for > 50% of posts)
   - `_NICHE_LIFT_FLOOR = 0.8` — minimum niche_lift threshold (Section 1: "primary format
     declining" check)
   - `_ENGAGEMENT_DROP_THRESHOLD = 0.80` — week-over-week engagement drop trigger
     (Section 5: flags when engagement drops > 20% for two consecutive weeks, i.e. ratio
     falls below 0.80)
3. Replace the three bare float literals with these constant names.

**Expected outcome:** The three float literals are replaced with named constants. All
existing tests still pass. `ruff` and `mypy` still pass at 0.

**Gotchas:**
- Read the file first — confirm exact values before extracting. If the actual values in
  the live code differ from the values listed above, extract what is actually there (the
  names above describe intent, not a prescription to change values).
- The cadence bounds (`3.0`, `0.5`) and window sizes (`7`, `28`) are already
  contextually clear from adjacent message strings — do NOT extract those.
- Do not extract any other constants not listed here. Scope is exactly these three.
