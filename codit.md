# Sable Slopper — Codit Code Audit
**Date:** 2026-03-23
**Scope:** Full codebase, with extra focus on recent changes in `advise`, `pulse meta`, `platform`, `vault`, and shared LLM/cost surfaces
**Method:** Static analysis, targeted verification of high-risk paths, and validation runs
**Note:** This is a findings document only. No code was modified as part of the audit.

---

## Validation Snapshot

- `./.venv/bin/python -m pytest -q` → `200 passed`
- `./.venv/bin/ruff check .` → `40` failures
- `./.venv/bin/mypy sable` → `100` errors

The repo is materially healthier than earlier in the day, but it is still not at a clean
validation baseline. Tests are green; linting and typechecking are not.

---

## At A Glance

| Area | Current read |
|---|---|
| Open Tier 1 risk | Partial vault sync after phase-B rename, crash-unsafe local writes, path traversal in `vault_dir()`, and still-misleading failed scan rows |
| Recently improved | `advise` shared client path, `platform_ok -> degraded`, `artifacts.degraded`, safer phase-A vault sync, non-zero partial scan counts |
| Validation state | `pytest` green, `ruff` red, `mypy` red |
| Biggest strategic gap | Claude cost tracking and budget enforcement are still not unified across the repo |

---

## Section 1 — Critical Issues

These are issues that can cause data loss, misleading persisted state, writes outside the
intended directory, or hard production failures in common flows.

---

### CRIT-1 · `vault/platform_sync.py` — Partial-sync window still exists after phase-B rename

**File:** `sable/vault/platform_sync.py`, lines 432-479

The recent two-phase write fix is real and valuable. Generation no longer overwrites final
files during phase A. However, the sync still renames staged files into final paths before
all later work has succeeded:

- final `os.replace()` happens at line 432
- pulse report copy happens at lines 436-455
- old artifact deletion happens at lines 457-470
- new artifact insert happens at lines 473-478
- commit happens at line 479

If anything fails after line 432, the filesystem may already contain the new generation
while the database still reflects the old artifact set or a partially updated state.

**Production impact:** Operators can end up with a vault tree that looks current while the
database metadata and job history say something else. This is still a partial-pipeline
failure mode on a Tier 1 surface.

**Suggested fix:**
- Stage `meta_report.md` into the same temp-write set as the other generated files.
- Delay all final-path swaps until every post-generation step that can fail has been prepared.
- If a fully staged design is too large, add compensating failure handling that marks the job
  as failed and records that filesystem state may be newer than DB state.

**Test to add:**
- Inject a failure after phase-B rename but before artifact-row insertion and assert the run
  does not leave swapped files with stale artifact metadata.

---

### CRIT-2 · `roster/manager.py` — Concurrent writes can silently lose roster data

**File:** `sable/roster/manager.py`, lines 27-36

Every write path follows:

`load_roster() -> mutate in memory -> save_roster()`

`save_roster()` writes `roster.yaml` directly with no file lock:

```python
with open(path, "w") as f:
    yaml.dump(data, f, ...)
```

The code itself acknowledges this with:

`# TODO(codex): no file lock on roster.yaml — concurrent writes will lose data`

**Production impact:** Two CLI processes updating the roster at the same time can clobber each
other. Learned preferences, tweet-bank additions, or account edits can disappear silently.

**Suggested fix:**
- Add an advisory file lock around read-modify-write operations.
- Pair that with atomic temp-write + replace so the write is both serialized and crash-safe.

**Test to add:**
- Concurrent writer test or a smaller unit around a locking helper proving the second writer
  cannot overwrite the first without re-reading fresh state.

---

### CRIT-3 · `vault/notes.py` — Non-atomic note writes can corrupt files on crash

**File:** `sable/vault/notes.py`, lines 33-47 and 94-97

`write_note()` uses `path.write_text(...)` directly. `save_sync_index()` does the same for
`_sync_index.json`. A crash, OOM kill, disk-full event, or forced termination can leave a
truncated file on disk.

The code already documents this risk:

`# TODO(codex): non-atomic write — crash mid-write will corrupt the file; fix with tmp+os.replace`

**Production impact:** Partial frontmatter writes can make notes unreadable and break downstream
vault parsing. The sync index can also become unreadable and silently reset to `{}` on the next load.

**Suggested fix:**
- Reuse the temp-write + `os.replace()` pattern already present in `platform_sync.py`.
- Apply it to both note writes and sync-index writes.

**Test to add:**
- Crash-simulation or helper-level test that writes through a temp path and proves the final
  file is either old or new, never partial.

---

### CRIT-4 · `shared/paths.py` — `vault_dir(org)` allows path traversal

**File:** `sable/shared/paths.py`, lines 115-126

`vault_dir()` concatenates the user-supplied `org` directly into the target path:

```python
d = root / org
d.mkdir(parents=True, exist_ok=True)
return d
```

There is no validation that `org` is a simple slug rather than `../../elsewhere`.

**Production impact:** A malformed or malicious `org_id` can cause vault writes outside the
intended vault root. That affects any caller using `vault_dir()` directly, not just platform sync.

**Suggested fix:**
- Validate `org` against a strict slug format before using it as a path component.
- Or resolve the candidate path and reject anything that escapes the configured vault root.

**Test to add:**
- Assert that `vault_dir("../../tmp")` or equivalent invalid input is rejected.

---

### CRIT-5 · `platform/merge.py` — Missing-entity merge crashes with `NoneType`

**File:** `sable/platform/merge.py`, lines 57-65

`execute_merge()` fetches source and target rows, then immediately subscripts them:

```python
source_row = ...
target_row = ...
if source_row["org_id"] != target_row["org_id"]:
```

If either lookup returns `None`, the function crashes with `TypeError` instead of raising a
structured `SableError`.

**Production impact:** A stale or already-merged entity ID can crash merge execution with an
opaque runtime error rather than a user-meaningful failure.

**Suggested fix:**
- Validate both rows exist before the cross-org guard.
- Raise a specific `SableError` for missing source/target entities.

**Test to add:**
- Call `execute_merge()` with a missing entity ID and assert a structured error, not `TypeError`.

---

## Section 2 — High Severity Issues

These produce misleading analysis, silent data loss in subflows, cost-control blind spots,
or fragile behavior in real operator workflows.

---

### HIGH-1 · `pulse/meta` failed scan rows still under-report cost and novelty

**Files:** `sable/pulse/meta/cli.py`, lines 214-218; `sable/pulse/meta/db.py`, lines 162-168

The recent fix preserves `tweets_collected` on generic scan failure by reading partial tweets
from the DB before calling `fail_scan_run()`. That is a real improvement.

But failed rows still persist:
- `tweets_new = 0`
- `estimated_cost = 0.0`

on the generic exception path.

**Production impact:** Scan history is still partly false. Operators see a failed run with real
partial tweet collection but zero novelty and zero cost, which understates both spend and work.

**Suggested fix:**
- Promote `estimated_cost` and `tweets_new` from local variables in `Scanner.run()` to instance
  attributes readable after exceptions.
- Pass those values into `fail_scan_run()` from the CLI exception path.

**Test to add:**
- Mid-scan exception after at least one successful fetch/insert, then assert the failed row
  preserves non-zero `estimated_cost` and correct partial `tweets_new`.

---

### HIGH-2 · Shared Claude surfaces still bypass repo-level budget and cost logging

**Files:** `sable/shared/api.py`, `sable/clip/selector.py`, `sable/character_explainer/script.py`, `sable/vault/search.py`, `sable/vault/suggest.py`, `sable/pulse/recommender.py`, `sable/meme/generator.py`, `sable/wojak/generator.py`

The platform brief path now uses `check_budget()` and `log_cost()`. Most of the rest of the
repo still does not. Representative direct call surfaces:

- `sable/shared/api.py:93`
- `sable/clip/selector.py:340`
- `sable/clip/selector.py:516`
- `sable/character_explainer/script.py:65`
- `sable/character_explainer/script.py:106`

**Production impact:** The repo now has budget controls, but only for part of the LLM surface.
Clip selection, vault ranking, recommenders, explainers, memes, and wojak generation can still
consume spend without common accounting or gating.

**Suggested fix:**
- Add one repo-standard Claude wrapper that can:
  - enforce org budgets when org context exists
  - log cost when `sable.db` is available
  - provide consistent degrade/retry behavior
- Route shared Claude callers through that wrapper.

**Test to add:**
- One non-platform LLM path should have a budget/cost-accounting test proving it either logs spend
  or is explicitly exempt.

---

### HIGH-3 · `pulse/meta/scanner.py` — Failed author fetches are silently excluded from scans

**File:** `sable/pulse/meta/scanner.py`, lines 225-234

When `_fetch_author_tweets_async()` fails for an account, the scanner logs a warning and
continues:

```python
except Exception as e:
    console_warn(f"Failed to fetch {handle}: {e}")
    continue
```

There is no persisted failed-author list or failed-author count in the scan result or scan row.

**Production impact:** A scan can look complete even when a significant portion of the watchlist
was skipped due to upstream failures. Trend analysis and recommendations then operate on a silently
partial sample.

**Suggested fix:**
- Track failed handles in the scanner result.
- Persist that into scan metadata or `claude_raw`/`result_json` equivalent.
- Surface a visible degraded-state warning at the CLI/report layer.

**Test to add:**
- Simulate a scan where one author fetch fails and assert the result/report records that the run
  was incomplete.

---

### HIGH-4 · `pulse/meta/scanner.py` — Author cursor uses string `max()` over tweet IDs

**File:** `sable/pulse/meta/scanner.py`, line 288

The latest tweet ID for a profile cursor is computed as:

```python
latest_id = max(str(t.get("tweet_id", "")) for t in normalised)
```

That compares IDs lexicographically as strings rather than as numeric snowflakes, and it also
allows values like `"None"` to win if malformed input slips through.

**Production impact:** A bad cursor can cause future incremental scans to miss tweets or refetch
duplicates for an author.

**Suggested fix:**
- Validate `tweet_id` before cursor calculation.
- Compare IDs numerically, not lexicographically.

**Test to add:**
- Mixed valid/invalid tweet IDs, or different-length IDs, should still yield the correct cursor.

---

### HIGH-5 · `pulse/meta/scanner.py` — Deep-mode outsider tweets are analyzed but never persisted

**File:** `sable/pulse/meta/scanner.py`, lines 297-339

Deep mode classifies outsider tweets and appends them to `outsider_results`, but never calls
`upsert_tweet()` or stores them anywhere durable.

**Production impact:** Deep mode appears to collect adjacent-market signal, but that signal is lost
after the process exits. The feature is effectively analysis-only and non-reproducible.

**Suggested fix:**
- Either persist outsider tweets to a dedicated table or explicitly mark the feature as ephemeral.
- If persistence is not desired, the CLI/report output should say so.

**Test to add:**
- Deep-mode run should either persist outsider rows or assert that the UI/report clearly marks them
  as transient only.

---

### HIGH-6 · `shared/ffmpeg.py` — Subtitle path is injected directly into filter-graph syntax

**File:** `sable/shared/ffmpeg.py`, line 166

The subtitle path is interpolated directly into the FFmpeg filter graph:

```python
filter_graph += f";{current}ass={subtitle_path}[out]"
```

FFmpeg filter graphs treat `:`, `;`, `[`, `]`, and `=` as structural characters. A subtitle path
containing any of these can break parsing or change interpretation.

**Production impact:** Valid files with special characters in their paths can cause clip assembly
to fail with opaque FFmpeg parse errors.

**Suggested fix:**
- Escape subtitle paths for filter-graph syntax or use a safer FFmpeg invocation strategy.
- Reject unsafe subtitle paths with a clear application error if escaping is not reliable.

**Test to add:**
- Use a subtitle file path containing special characters and assert robust handling.

---

### HIGH-7 · `platform/db.py` — Migration failure can leave the schema partially applied

**File:** `sable/platform/db.py`, lines 27-40

`ensure_schema()` applies each migration via `conn.executescript(...)` without explicit wrapping
or recovery logic around the migration sequence. If a migration fails midway, the DB can be left
partially updated and eligible to fail again on the next run.

**Production impact:** A failed migration can strand the local database in a hard-to-recover state.

**Suggested fix:**
- Wrap each migration in a clear transaction boundary and surface a precise migration failure error.
- Add a migration smoke test that verifies failure leaves the DB in a recoverable state.

**Test to add:**
- Inject a broken migration in test and assert the schema version / table state remains recoverable.

---

## Section 3 — Medium Severity Issues

These are important correctness, observability, or performance issues that do not immediately
destroy state, but they degrade trust and maintainability.

---

### MED-1 · `pulse/meta/cli.py` — Analysis phase still has no explicit cost guard

**File:** `sable/pulse/meta/cli.py`, `_run_analysis()` lines 373-395

The scan command enforces a collection-time `max_cost`, but the later Claude analysis and
recommendation phase does not have an equivalent cap.

**Production impact:** Analysis spend can drift upward independently of scan spend if models or
prompt size change.

**Suggested fix:**
- Add an analysis-phase estimate or hard cap separate from scan collection cost.
- Record whether fallback analysis was used for cost reasons.

---

### MED-2 · `pulse/meta/cli.py` + `reporter.py` — Fallback analysis is not clearly marked in the written report

**Files:** `sable/pulse/meta/cli.py`, lines 373-395; `sable/pulse/meta/reporter.py`, lines 292-368

When Claude analysis fails, the CLI falls back to quantitative-only analysis with a console warning.
The written vault report does not appear to carry a degraded/fallback marker in frontmatter or body.

**Production impact:** A saved report can look like a full strategist synthesis even when it is
fallback-only.

**Suggested fix:**
- Add a frontmatter field or visible section in the saved report indicating fallback mode.

---

### MED-3 · `clip/transcribe.py` — Whisper model is loaded fresh on every transcription

**File:** `sable/clip/transcribe.py`, lines 27-29 and 52

`_load_model()` instantiates `WhisperModel(...)` every call and there is no model cache.

**Production impact:** Batch transcription pays model-load cost repeatedly, slowing runs and
thrashing memory.

**Suggested fix:**
- Cache model instances by model name within the process.

---

### MED-4 · `advise/stage1.py` — Broad exception swallowing still masks real data failures

**File:** `sable/advise/stage1.py`, multiple blocks

The recent degraded-state work improved one important path, but stage 1 still catches broad
exceptions in pulse, meta, and platform reads and frequently degrades to empty/no-data behavior.

**Production impact:** Operators still cannot reliably distinguish "no data yet" from "DB path is
broken or query failed" without deeper debugging.

**Suggested fix:**
- Keep degraded-state behavior, but log or record which source actually failed.

---

### MED-5 · `vault/search.py` and similar paths — Claude failures often degrade silently to local heuristics

**Files:** `sable/vault/search.py` and related vault recommendation paths

Example:

```python
except Exception:
    return keyword fallback
```

This is reasonable for resilience, but the caller often gets no explicit signal that the result
quality dropped from Claude-ranked to keyword-ranked.

**Production impact:** Lower-quality results can be mistaken for full-quality results.

**Suggested fix:**
- Return a result metadata flag indicating fallback mode.

---

### MED-6 · `advise/generate.py` — Corrupted cache rows are skipped forever and force repeated regeneration

**File:** `sable/advise/generate.py`, lines 31-61

`_check_cache()` iterates recent `twitter_strategy_brief` artifacts and attempts to parse
`metadata_json` and nested `input_refs_json`. If a row is malformed, the code catches the error
and silently `continue`s to the next row.

That is resilient, but the bad row remains in the database indefinitely and will be retried on
every subsequent cache lookup.

**Production impact:** A corrupted artifact row permanently disables cache hits for that entry and
can cause repeated avoidable Claude calls until the DB row is manually cleaned up.

**Suggested fix:**
- Mark corrupted cache rows stale or invalid when detected.
- Or at minimum log the bad artifact ID/path so an operator can repair it.

**Test to add:**
- Insert an artifact row with malformed `metadata_json` and assert the system either marks it stale
  or reports it clearly instead of silently re-skipping forever.

---

### MED-7 · `clip/selector.py` — Claude JSON parse failure silently drops a whole evaluation batch

**File:** `sable/clip/selector.py`, lines 340-350

Variant evaluation does this:

```python
raw = call_claude_json(...)
try:
    evaluations = json.loads(raw)
    ...
except json.JSONDecodeError:
    evaluations = []
```

If Claude returns malformed JSON, rate-limit prose, or any non-list response, the entire batch is
quietly treated as empty evaluation data.

**Production impact:** Usable clips can be discarded or downgraded without any operator signal. A
Claude failure looks like "no good duration choices" rather than "the evaluator broke."

**Suggested fix:**
- Log the malformed response context or surface a warning.
- Consider preserving the unparsed raw response in debug output for auditability.

**Test to add:**
- Force `call_claude_json()` to return malformed JSON and assert the selector emits a degraded-state
  warning rather than silently proceeding as if no evaluations were available.

---

### MED-8 · `platform/cost.py` — Weekly budget windows still use naive UTC datetime arithmetic

**File:** `sable/platform/cost.py`, lines 31-49

`get_weekly_spend()` uses `datetime.datetime.utcnow()` and other naive datetime objects to compute
ISO week boundaries. The code works most of the time, but it is already generating deprecation
warnings under the current test run.

**Production impact:** Budget-window math is more fragile than it needs to be, and the warning
noise makes it easier to ignore future time-related regressions.

**Suggested fix:**
- Switch to timezone-aware UTC datetimes consistently.
- Keep the SQLite comparison format explicit and tested around week boundaries.

---

### MED-9 · `pulse/meta/scanner.py` — Lookback filtering falls back to string comparison on malformed dates

**Files:** `sable/pulse/meta/scanner.py`, lines 82-96 and 130-136

`_parse_twitter_date()` returns the original raw string if neither the Twitter-format parse nor
the ISO parse succeeds. Later, lookback filtering does:

```python
posted_at = _parse_twitter_date(...)
if posted_at >= cutoff:
    filtered.append(t)
```

If `posted_at` is an unparsed raw string, the comparison is lexicographic rather than chronological.

**Production impact:** Malformed or shape-changed upstream dates can allow old tweets through the
lookback filter or exclude recent ones incorrectly.

**Suggested fix:**
- Make `_parse_twitter_date()` return `None` on parse failure instead of the raw string.
- Skip or explicitly quarantine unparseable tweets rather than comparing them as strings.

**Test to add:**
- Feed a malformed `created_at` value and assert the tweet is rejected or flagged, not admitted
  through a string comparison path.

---

### MED-10 · `pulse/meta/db.py` — Format baselines accumulate duplicate rows over time

**File:** `sable/pulse/meta/db.py`, lines 354-363

`upsert_format_baseline()` is not actually an upsert. It performs a plain insert:

```python
INSERT INTO format_baselines (...)
VALUES (...)
```

with no uniqueness constraint or conflict handling on `(org, format_bucket, period_days, computed_at window)`.

**Production impact:** Baseline rows accumulate indefinitely for the same org/format/period
combination. Queries that read "recent baselines" stay correct only if every consumer remembers to
limit or filter by recency. Table growth and stale-row confusion increase over time.

**Suggested fix:**
- Decide whether this table is meant to be history or current state.
- If current state, add a uniqueness key and real upsert behavior.
- If history is intentional, rename the function away from `upsert_*` and document consumer rules.

**Test to add:**
- Write the same baseline twice and assert either one row is replaced or multiple rows are expected
  and correctly handled by readers.

---

### MED-11 · `vault/platform_sync.py` — Full entity set is loaded eagerly with no size guard

**File:** `sable/vault/platform_sync.py`, lines 308-353

Sync loads all non-archived entities for an org into memory, then issues additional per-entity
queries for handles, tags, notes, and content items before writing anything:

```python
entities = [dict(r) for r in conn.execute(...).fetchall()]
```

There is no pagination, batching, or explicit upper bound.

**Production impact:** For larger orgs, vault sync can become memory-heavy and increasingly slow.
This is not an immediate bug for small datasets, but it is a real scaling risk on a central command.

**Suggested fix:**
- Decide whether vault sync is intentionally "small org only".
- If not, batch or stream entities and generate notes incrementally.
- At minimum, log entity counts and warn when sync size exceeds an expected threshold.

---

### MED-12 · `advise/stage2.py` — Anthropic pricing is hardcoded in application logic

**File:** `sable/advise/stage2.py`, lines 49-55

`synthesize()` computes cost using hardcoded per-million-token rates for Sonnet and Haiku.
Those values can drift when Anthropic pricing changes.

**Production impact:** Cost logs and budget reasoning become stale silently after any pricing change.
That can make operator decisions and future budget enforcement wrong even if the code keeps working.

**Suggested fix:**
- Move model pricing into config or a centralized pricing table with an update date.
- Keep one authoritative source for pricing assumptions used by cost logs and budget checks.

---

## Section 4 — Cross-Cutting Concerns

These are patterns repeated across the repo that amplify the impact of single-file bugs.

---

### CC-1 · Silent exception swallowing is still pervasive

This remains one of the strongest recurring reliability smells in the repo. It appears in:

- `sable/advise/stage1.py`
- `sable/vault/platform_sync.py`
- `sable/vault/sync.py`
- `sable/platform/cli.py`
- `sable/vault/search.py`

The recent `degraded` work improved one path, but the larger pattern remains: many failures are
turned into empty results or quiet fallback behavior without a durable signal.

**Recommendation:** Prefer one of:
- explicit degraded flags
- narrowly scoped exception handling
- structured warnings/logging

---

### CC-2 · Cost tracking is still decoupled from the actual API call surface

The platform layer now has `cost_events`, `check_budget()`, and `log_cost()`. The repo-wide
Claude surface still does not consistently flow through them.

**Recommendation:** Centralize Anthropic access behind one wrapper that can log and gate spend
where appropriate.

---

### CC-3 · Validation debt is still high enough to hide new regressions

Current state:
- tests pass
- Ruff fails
- mypy fails

This makes it harder to treat "all checks pass" as a meaningful signal for future branches.

**Recommendation:** Decide whether Ruff/mypy are advisory or gating. If gating, clean recently
changed modules first instead of boiling the ocean.

---

### CC-4 · Security and path-safety checks are still inconsistent

The codebase has started to grow more filesystem-sensitive features, but path validation remains
uneven across modules:

- `vault_dir(org)` accepts raw user-facing `org` values
- FFmpeg subtitle paths are interpolated directly into filter-graph syntax
- entity and artifact paths rely heavily on "should be well-formed" assumptions

**Recommendation:** Standardize path sanitization rules for:
- org IDs
- filenames derived from DB/user data
- paths embedded in shell/filter syntax

---

### CC-5 · Retry and backoff behavior is inconsistent across external API surfaces

The codebase has some narrow retry behavior, but not a repo-level strategy:

- `pulse/meta/scanner.py` retries one `429` once after a fixed 5-second sleep
- shared Anthropic paths generally do not retry
- other external integrations rely on caller-specific behavior or fail immediately

**Why this matters:** Transient upstream failures are handled very differently depending on which
command the user happened to run. That creates uneven reliability and makes cost behavior harder to predict.

**Recommendation:** Define one policy for:
- which errors are retryable
- how many retries are allowed
- whether retries count against budget
- how degraded fallback should be surfaced after retries fail

---

## Section 5 — Positive Notes

Several recent fixes are real improvements and should not be discounted:

- `advise` now uses the shared Anthropic client instead of bypassing repo config.
- `platform_ok` now affects degraded brief state.
- `degraded` is now queryable in the `artifacts` table, not just frontmatter.
- `pulse meta` no longer leaves fully fake all-zero scan rows on generic failure.
- vault sync is safer than before because phase A no longer overwrites final files.

The remaining issues are narrower than they were before the recent patch series. The codebase is
moving in the right direction, but several Tier 1 reliability and cost issues are still open.

---

## Section 6 — Recently Improved / Partially Fixed

These are areas where recent work materially improved the repo, but should not be mistaken for
"fully solved":

- `pulse meta` failure handling is better than before:
  `tweets_collected` is now recoverable on generic failure, but `tweets_new` and `estimated_cost`
  are still wrong on that path.
- `vault/platform_sync.py` is safer than before:
  phase A no longer overwrites final files, but post-rename failures can still desync filesystem
  and DB state.
- `advise` degraded-state handling is better than before:
  `platform_ok` now flows into `degraded`, but stage 1 still swallows many real read failures.
- `artifacts.degraded` is now queryable:
  this is a real product improvement, not just frontmatter decoration.

This section matters because the repo has recently improved enough that older findings need to be
re-read in context. Some are still open, but no longer in their original form.

---

## Short Priority Order

1. Close the remaining partial-sync window in `vault/platform_sync.py`.
2. Finish truthful failed-scan persistence in `pulse/meta`.
3. Centralize Claude budget/cost handling across the repo.
4. Fix crash-safe writes and concurrency on local state files (`roster.yaml`, vault notes).
5. Reduce silent fallback behavior in user-facing/reporting paths.
