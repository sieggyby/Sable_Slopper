# Sable Slopper — Code Audit
**Date:** 2026-03-23
**Scope:** Full codebase — pulse, meta, advise, platform, vault, clip, roster, shared
**Method:** Static analysis + exploratory read of all source files
**Note:** This is a findings document only. No code was modified.

---

## Validation Snapshot

Validation was not run as part of this audit. Before beginning fixes, establish the baseline:

```
./.venv/bin/python -m pytest -q
./.venv/bin/ruff check .
./.venv/bin/mypy sable
```

Per a concurrent review, the repo is currently at: `200 passed / 40 ruff failures / 100 mypy errors`.
Tests are green; linting and typechecking are not. New work should not increase either failure count.

---

## Section 1 — Critical Issues

Data loss, hard production crashes, security exposure, or cost controls that don't fire.

---

### CRIT-1 · `roster/manager.py:28` — Race condition on roster.yaml writes

**File:** `sable/roster/manager.py`, line 28 (confirmed by in-code TODO comment)

Every mutation function (`add_account`, `update_account`, `remove_account`,
`append_tweet`, `update_learned_preferences`) follows the pattern:
```
load_roster() → modify in memory → save_roster()
```
`save_roster()` does a plain `open(path, "w")` write with no file locking. Two concurrent
CLI invocations (e.g., a background scan alongside a manual `roster update`) will silently
clobber each other's changes.

```python
# TODO(codex): no file lock on roster.yaml — concurrent writes will lose data
```

**Production impact:** Silent account data loss. Added accounts vanish. Learned preferences
from a scan run are clobbered by a concurrent roster edit.

**Suggested fix:**
- Wrap the read-modify-write cycle with `fcntl.flock()` (advisory lock).
- Pair with temp-write + `os.replace()` so the write is both serialized and crash-safe.

**Test to add:**
- Launch two concurrent processes calling `add_account()` simultaneously; assert no data from
  either write is lost.

---

### CRIT-2 · `vault/notes.py:47` — Non-atomic note write (file corruption on crash)

**File:** `sable/vault/notes.py`, lines 33–47 and 94–97

`write_note()` calls `path.write_text(content)` directly. `save_sync_index()` on line 97 has
the same issue. An OOM kill, disk-full event, or `kill -9` mid-write leaves a truncated file
on disk.

```python
# TODO(codex): non-atomic write — crash mid-write will corrupt the file; fix with tmp+os.replace
```

`platform_sync.py` already implements the correct pattern via `_atomic_write()` /
`_write_to_temp()` + `os.replace()`. `notes.py` does not.

**Production impact:** Partial frontmatter writes make notes unreadable. The sync index can
silently reset to `{}` on the next load. Downstream vault parsing breaks.

**Suggested fix:**
- Reuse the `_atomic_write()` / `_write_to_temp()` + `os.replace()` pattern from
  `platform_sync.py`. Apply to both `write_note()` and `save_sync_index()`.

**Test to add:**
- Crash-simulate mid-write via signal injection; assert the resulting file is either the old
  version or the new version, never a partial write.

---

### CRIT-3 · `platform/merge.py:61` — NoneType crash on missing entity before merge

**File:** `sable/platform/merge.py`, lines 57–65

`execute_merge()` fetches both entities then immediately subscripts them:

```python
source_row = conn.execute("SELECT * FROM entities WHERE entity_id=?", ...).fetchone()
target_row = conn.execute("SELECT * FROM entities WHERE entity_id=?", ...).fetchone()

if source_row["org_id"] != target_row["org_id"]:   # line 61 — crashes if either is None
```

If either entity_id doesn't exist, `fetchone()` returns `None` and `None["org_id"]` raises
`TypeError`. No guard validates both rows exist before the cross-org check.

**Production impact:** A stale or already-merged entity ID crashes merge execution with an
opaque `TypeError` instead of a structured `SableError`.

**Suggested fix:**
- Validate both rows are not `None` before the cross-org check.
- Raise `SableError(ENTITY_NOT_FOUND, ...)` for each missing entity.

**Test to add:**
- Call `execute_merge()` with a nonexistent entity ID; assert a `SableError` with a meaningful
  code, not `TypeError`.

---

### CRIT-4 · `advise/generate.py:121–132` — Cost cap bypassed in degraded mode

**File:** `sable/advise/generate.py`, lines 121–132 and 167–178

The per-brief cost cap check (lines 167–178) only fires when `not budget_exceeded`. In the
flow where `degrade_mode == "fallback"`, `budget_exceeded` is set to `True` before the cap
check runs — meaning the cap is skipped entirely in degraded mode.

Additionally, the budget estimate uses `len(summary_text) // 4` (4 chars/token). For
structured content with short words, actual token count runs 30–50% higher, making the cap
meaningless even when it does run.

**Production impact:** Briefs generated during budget-degraded conditions consume tokens
without any cap enforcement. Cost overruns unchecked.

**Suggested fix:**
- Restructure the cap check so it runs independently of `budget_exceeded` state.
- Replace the `len // 4` estimate with `anthropic.count_tokens()` or apply a 1.5× safety
  multiplier.

**Test to add:**
- Enter degraded/fallback mode with `budget_exceeded=True` and assert the per-brief token cap
  still fires at the configured threshold.

---

### CRIT-5 · `shared/paths.py:124` — Path traversal via org parameter in vault_dir()

**File:** `sable/shared/paths.py`, line 124

```python
def vault_dir(org: str = "") -> Path:
    ...
    if org:
        d = root / org    # no sanitization
        d.mkdir(parents=True, exist_ok=True)
        return d
```

`org` is taken directly from user input (CLI arguments, roster YAML) with no validation. An
org string of `../../etc` resolves outside the vault root and `mkdir` creates directories
elsewhere on disk.

`platform_sync.py` has `_is_inside_vault_root()` as a guard, but `vault_dir()` itself — called
from many places — does not.

**Production impact:** A misconfigured or deliberately crafted `org_id` writes files outside
the vault directory. Affects every caller of `vault_dir()`.

**Suggested fix:**
- Validate `org` against a strict slug pattern (`^[a-zA-Z0-9_-]+$`) before using it as a path
  component. Or resolve the candidate path and reject anything that doesn't start with the
  vault root.

**Test to add:**
- Call `vault_dir("../../tmp")` and similar traversal strings; assert rejection, not directory
  creation outside the vault.

---

## Section 2 — High Severity Issues

Incorrect analysis results, silent data loss in subflows, cost-control blind spots, or
fragile behavior in real operator workflows.

---

### HIGH-1 · `platform/cost.py:33` — Naive UTC datetime for weekly budget windows

**File:** `sable/platform/cost.py`, line 33

```python
now = datetime.datetime.utcnow()          # deprecated naive datetime
y, w, _ = now.isocalendar()
week_start = datetime.datetime.fromisocalendar(y, w, 1)  # also naive
```

`utcnow()` is deprecated in Python 3.12+ and returns a timezone-naive object. The resulting
`week_start` string is compared against SQLite `datetime('now')` values in
`cost_events.created_at`. At ISO week boundaries or on machines with clock offset, the naive
comparison drifts.

**Production impact:** Weekly spend calculation can be wrong at week boundaries. Budget
enforcement may block legitimate runs or miss actual overages.

**Suggested fix:**
- Replace `datetime.utcnow()` with `datetime.now(timezone.utc)` throughout `cost.py`.
- Store and compare as ISO8601 strings with explicit `+00:00` offset.

**Test to add:**
- Compute weekly spend at an ISO week boundary and assert the window is correct regardless of
  system timezone.

---

### HIGH-2 · `pulse/meta/scanner.py:232–234` — Failed author fetches silently excluded

**File:** `sable/pulse/meta/scanner.py`, lines 232–234

```python
except Exception as e:
    console_warn(f"Failed to fetch {handle}: {e}")
    continue
```

No failed-author list or count is persisted in the scan result or scan row. The caller
receives a result that looks like a complete scan.

**Production impact:** A scan of 50 accounts where 25 fail silently appears to have run
successfully. Trend analysis is computed on half the watchlist with no audit trail.

**Suggested fix:**
- Collect failed handles into a `failed_authors` list during the scan loop.
- Persist that list in `scan_runs` or the result dict.
- Surface a visible degraded-state warning in the CLI and report output.

**Test to add:**
- Simulate one failing author fetch in a scan; assert the result contains `failed_authors`
  with the handle and the scan row reflects partial completion.

---

### HIGH-3 · `pulse/meta/scanner.py:288` — Tweet ID max() via string comparison

**File:** `sable/pulse/meta/scanner.py`, line 288

```python
latest_id = max(str(t.get("tweet_id", "")) for t in normalised)
```

Twitter snowflake IDs are numeric but compared as strings. If any tweet has
`tweet_id = None`, `str(None)` = `"None"` which lexicographically sorts after most numeric
strings, corrupting the cursor.

**Production impact:** Corrupted cursor causes next scan to miss tweets or re-fetch duplicates
for that author.

**Suggested fix:**
- Filter out tweets where `tweet_id` is `None` or non-numeric before the cursor calculation.
- Compare as integers: `max(int(t["tweet_id"]) for t in normalised if t.get("tweet_id"))`.

**Test to add:**
- Mix valid snowflake IDs with a `None` tweet_id in the input; assert the correct numeric
  maximum is returned as the cursor.

---

### HIGH-4 · `pulse/meta/scanner.py:298–327` — Deep mode outsider results never persisted

**File:** `sable/pulse/meta/scanner.py`, lines 298–327 and 336

`outsider_results` collects and classifies tweets from non-watchlist accounts, appends them
to the result dict — but `upsert_tweet()` is never called on them. The data is discarded
after the run.

**Production impact:** Deep mode is presented as collecting adjacent-market signal, but the
collected tweets are lost after the process exits. The feature is effectively half-implemented.

**Suggested fix:**
- Call `upsert_tweet()` on each outsider result, writing to a dedicated `source="outsider"`
  bucket.
- If persistence is intentionally deferred, strip the collection code and document that the
  feature is incomplete.

**Test to add:**
- Deep-mode run with mocked keyword results; assert outsider tweets appear in the DB after
  the run.

---

### HIGH-5 · `advise/generate.py:31–61` — Corrupted artifact rows loop forever in cache

**File:** `sable/advise/generate.py`, lines 31–61

`_check_cache()` iterates artifact rows ordered by recency. For each row, it attempts
`json.loads(metadata_json)` → `json.loads(inner["input_refs_json"])`. If either JSON field
is malformed, the exception is caught with `continue` — but the row stays in the DB flagged
as a valid artifact. Every subsequent run re-fetches the same row, fails to parse it, and
silently skips it.

**Production impact:** A corrupted artifact row permanently bypasses the cache on every run,
forcing a fresh Claude call each time. Cost accumulates silently.

**Suggested fix:**
- When JSON parse fails on an artifact row, mark it with a `corrupt = 1` flag (or delete it).
- Exclude corrupt rows from all future cache lookups.

**Test to add:**
- Insert a malformed artifact row; assert subsequent runs skip it without retrying and do use
  the cache for valid rows.

---

### HIGH-6 · `vault/platform_sync.py:~388` — Entity ID used directly as filename without validation

**File:** `sable/vault/platform_sync.py`, line ~388

```python
note_path = entities_dir / f"{eid}.md"
```

`eid` is a UUID from the database, fine in normal operation. But if `eid` were ever set to a
string with path separators (e.g., from a migration or manual insert), the constructed path
would write outside `entities_dir`.

**Production impact:** Low probability in practice, but a manual DB insertion or migration
error could create an exploitable path.

**Suggested fix:**
- Validate `entity_id` matches a UUID regex before constructing the path.
- Raise a `SableError` for non-UUID values.

**Test to add:**
- Insert an entity with `entity_id = "../../evil"` and assert the path construction is
  rejected.

---

### HIGH-7 · `vault/platform_sync.py:~312` — No LIMIT on entity query; OOM risk for large orgs

**File:** `sable/vault/platform_sync.py`, line ~312

The entity query fetches ALL entities for an org with no LIMIT. For large deployments, this
loads all rows into memory simultaneously before writing any files.

**Production impact:** For orgs with many entities, sync can exhaust available memory.

**Suggested fix:**
- Paginate the entity query using `LIMIT`/`OFFSET`. Write files per page.

**Test to add:**
- Sync with a synthetic large entity set and assert peak memory stays bounded.

---

### HIGH-8 · `shared/ffmpeg.py:166` — Subtitle path injected into filter_graph string

**File:** `sable/shared/ffmpeg.py`, line 166

```python
filter_graph += f";{current}ass={subtitle_path}[out]"
```

FFmpeg filter graph syntax treats `;`, `[`, `]`, `:`, and `=` as structural characters. A
subtitle path containing any of these malforms the filter graph, causing silent wrong output
or a cryptic FFmpeg parse error.

**Production impact:** Clip assembly fails on subtitle paths with special characters. Error is
an FFmpeg parse error, not a clear application error.

**Suggested fix:**
- Escape special filter-graph characters in `subtitle_path` before interpolation, or
  restructure to use the `-vf` option with `shlex`-safe quoting.
- Reject unsafe paths with a clear application error if escaping is not reliable.

**Test to add:**
- Subtitle file path containing `[`, `]`, `;`, or `=`; assert robust handling.

---

### HIGH-9 · `advise/stage1.py` — Multiple broad exception catches masking real DB errors

**File:** `sable/advise/stage1.py`, lines 86–129, 156–199, 243–269, 270–279

Four distinct database query blocks use `except Exception: pass` or
`except Exception: result[...] = []` with no logging. A corrupted `pulse.db` looks identical
to "no pulse data yet." A locked `sable.db` looks identical to "no entities yet."

**Production impact:** Database errors are invisible. Operators see "data unavailable" in
briefs without knowing whether it's expected emptiness or a real failure.

**Suggested fix:**
- Replace bare fallbacks with `except Exception as e: logger.warning("stage1 %s read failed: %s", source_name, e)`.
- Add a `failed_sources` list to the result dict so degraded briefs record which sources
  actually failed.

**Test to add:**
- Inject a `sqlite3.OperationalError` into each DB read block; assert the stage1 result
  records which source failed rather than silently degrading.

---

### HIGH-10 · `platform/db.py:27–40` — Failed migration leaves schema partially applied

**File:** `sable/platform/db.py`, lines 27–40

`ensure_schema()` applies migrations linearly with no rollback. If migration N+1 fails
midway, the schema is partially updated. The `schema_version` UPDATE may not have run yet,
leaving the migration eligible to re-run — but the partial state causes it to fail again.

**Production impact:** A failed migration strands the local database in a hard-to-recover
state. No rollback path. No clear distinction between "never applied" and "partially applied."

**Suggested fix:**
- Wrap each migration in an explicit `BEGIN`/`COMMIT` transaction so failure leaves the
  schema version unchanged and the migration is cleanly re-runnable.

**Test to add:**
- Inject a SQL error mid-migration; assert schema version is unchanged and the next
  `ensure_schema()` call completes cleanly.

---

## Section 3 — Medium Severity Issues

Incorrect results in edge cases, silent analytical debt, or degraded output quality without
crashing.

---

### MED-1 · `pulse/meta/fingerprint.py:52` — has_link pre-filtered; link+image misclassified

**File:** `sable/pulse/meta/fingerprint.py`, line 52

In `_normalise_tweet()`, `has_link` is set to `bool(urls) and not has_video and not has_image`.
By the time a tweet reaches `classify_format()`, image+link tweets already have `has_link = False`
and fall through to `mixed_media` instead of `link_share`.

**Production impact:** Link-sharing tweets that include a preview image are misclassified.
Format-bucket analytics and recommendations are subtly wrong.

**Suggested fix:** Pass raw `urls`, `has_image`, and `has_video` into `classify_format()`
separately and do the exclusion logic there, not in `_normalise_tweet()`.

---

### MED-2 · `pulse/meta/normalize.py:152–164` — format_lift falls back to total_lift when data is thin

**File:** `sable/pulse/meta/normalize.py`, lines 152–164

When an author has fewer than 5 tweets of the same format, `format_lift` silently equals
`total_lift`. The `format_lift_reliable=False` flag exists but callers don't uniformly check it.

**Production impact:** Format-specific lift recommendations look real but are a copy of total
lift for infrequent formats.

**Suggested fix:** At every call site that uses `format_lift`, gate on `format_lift_reliable`
first. Consider returning `None` rather than the misleading value when the flag is False.

---

### MED-3 · `pulse/meta/normalize.py:144–149` — Zero-baseline authors get deflated lift scores

**File:** `sable/pulse/meta/normalize.py`, lines 144–149

For new authors with zero engagement history, the min_denom floor computes a baseline of 8,
making a tweet with 5 likes score `0.625` — below average. The floor prevents division by
zero but misrepresents the signal.

**Production impact:** First-scan high-performing tweets appear below average. Recommendations
for new accounts are systematically pessimistic.

**Suggested fix:** When history is empty, return `format_lift_reliable=False` with a `None`
lift value rather than computing against an arbitrary floor denominator.

---

### MED-4 · `pulse/meta/scanner.py:131–136` — String date comparison allows old tweets through

**File:** `sable/pulse/meta/scanner.py`, lines 131–136

The cutoff filter uses `posted_at >= cutoff` where both are ISO strings. If
`_parse_twitter_date()` fails and returns the raw string, the comparison is lexicographic,
not chronological.

**Production impact:** Malformed tweet dates flood the scan with old content or silently
exclude recent tweets.

**Suggested fix:** Make `_parse_twitter_date()` raise on failure rather than return the raw
string. Filter tweets with unparseable dates before the cutoff comparison.

---

### MED-5 · `pulse/meta/cli.py` — Analysis phase has no cost guard

**File:** `sable/pulse/meta/cli.py`, `_run_analysis()`

The `meta_scan` command enforces `max_cost` on collection. But `_run_analysis()` — which calls
Claude for format analysis, trend synthesis, and recommendations — has no equivalent cap.

**Production impact:** Switching to a larger model in config could cause analysis runs to cost
5–10× more without any cap triggering.

**Suggested fix:** Add a pre-analysis token estimate and a configurable `max_analysis_cost`
cap separate from the scan collection cap.

---

### MED-6 · `pulse/meta/cli.py` — Fallback analysis not marked degraded in the written report

**File:** `sable/pulse/meta/cli.py`, lines 388–394

When Claude analysis fails, the code falls back to quantitative-only trends with a console
warning. The written report has no frontmatter or body marker indicating fallback rendering.

**Production impact:** A saved report looks identical to a Claude-powered report. Clients act
on quantitative-only analysis with no indication of quality degradation.

**Suggested fix:** Add a `degraded: true` frontmatter field and a visible banner in the report
body when fallback rendering was used.

---

### MED-7 · `platform/cost.py:81` — `>=` semantics: at-budget treated as exceeded

**File:** `sable/platform/cost.py`, line 81

```python
if spend >= cap:
    raise SableError(BUDGET_EXCEEDED, ...)
```

An org that spent exactly the cap is blocked from all further AI calls for the rest of the
week with no warning.

**Production impact:** Budget precision edge cases permanently block work. No "soft warning"
mode before hard cutoff.

**Suggested fix:** Change to `>` for the hard block. Add a separate soft-warning check at
~90% of cap.

---

### MED-8 · `platform/merge.py:19–23` — Expired candidates never re-evaluated

**File:** `sable/platform/merge.py`, lines 19–23

Candidates with `confidence < 0.70` are created with `status = "expired"`. There is no path
to transition them back to `"pending"` after more data accumulates. `get_pending_merges()`
filters on `status = 'pending'` only.

**Production impact:** A candidate created with thin data is permanently excluded from merge
consideration. The only fix is a manual DB update.

**Suggested fix:** Add a `reconsider_expired_merges()` function that re-evaluates `status = 'expired'`
candidates when a confidence update would push them above the threshold.

---

### MED-9 · `platform/merge.py:20` — UUID canonical ordering via string comparison

**File:** `sable/platform/merge.py`, line 20

```python
if entity_a_id > entity_b_id:
    entity_a_id, entity_b_id = entity_b_id, entity_a_id
```

UUID string ordering is lexicographic, not semantic. `INSERT OR IGNORE` means a re-submitted
pair in the opposite order silently no-ops with no feedback.

**Production impact:** Low practical risk within Python, but confusing to debug if a pair ever
appears with inconsistent ordering across systems.

**Suggested fix:** Add a comment documenting that ordering is lexicographic-by-string and
intentional. Low priority given Python string comparison is consistent within the repo.

---

### MED-10 · `vault/platform_sync.py:~339` — Content items fetched without ORDER BY

**File:** `sable/vault/platform_sync.py`, line ~339

Content items for entities are fetched without `ORDER BY`. SQLite row order is not guaranteed.
Different syncs may return different orderings on the same data.

**Production impact:** Entity note content sections shuffle between syncs without any data
change. Diffs between vault versions are noisy.

**Suggested fix:** Add `ORDER BY created_at ASC` to the content items query.

---

### MED-11 · `pulse/meta/db.py` — upsert_format_baseline() accumulates duplicate rows

**File:** `sable/pulse/meta/db.py`, `upsert_format_baseline()`

The function inserts baseline rows without `ON CONFLICT` deduplication. Each analysis run
appends new rows for the same org/format combination.

**Production impact:** Baseline computations drift as old rows accumulate. Table grows without
bound. Query performance degrades.

**Suggested fix:** Add `ON CONFLICT (org, format) DO UPDATE SET ...` to the insert. Add a
periodic vacuum migration to clear old rows.

---

### MED-12 · `pulse/db.py` — INSERT OR IGNORE silently discards duplicates

**File:** `sable/pulse/db.py`, `insert_post()`

`INSERT OR IGNORE` is used without checking `cursor.rowcount`. Callers cannot distinguish
"post was new and inserted" from "post already existed and was skipped."

**Production impact:** Sync operations have no way to report accurate counts of new vs.
existing posts.

**Suggested fix:** Check `cursor.rowcount` after `INSERT OR IGNORE` and return a boolean
indicating whether the insert was new or skipped.

---

### MED-13 · `advise/stage2.py` — Hardcoded API pricing rates become stale

**File:** `sable/advise/stage2.py`, cost calculation section

Cost per token is hardcoded per model with no version comment. Anthropic has changed pricing
multiple times. Every cost log entry will record the wrong USD amount after a price change.

**Production impact:** Cost logs systematically wrong after any Anthropic price change. Budget
enforcement enforces wrong thresholds.

**Suggested fix:** Move model pricing to a versioned constant in `shared/pricing.py` with a
`# last updated: YYYY-MM-DD` comment.

---

### MED-14 · `clip/transcribe.py` — Whisper model loaded fresh every call

**File:** `sable/clip/transcribe.py`, `_load_model()`

`WhisperModel` is instantiated fresh on every call. The model is 1–2 GB depending on size.
For a batch of 10 clips, the model is loaded and unloaded 10 times.

**Production impact:** Transcription throughput is severely limited by model load overhead.

**Suggested fix:** Cache `WhisperModel` instances in a module-level dict keyed by model name.
Load lazily on first call, reuse on subsequent calls within the same process.

---

### MED-15 · `clip/selector.py:342–350` — Claude JSON parse failure silently drops batch

**File:** `sable/clip/selector.py`, lines 342–350

```python
except json.JSONDecodeError:
    evaluations = []
```

If Claude returns malformed JSON, the entire batch evaluation is discarded silently. No log
records what Claude actually returned.

**Production impact:** Claude failures during clip evaluation are invisible. All clips in the
batch are lost when Claude returns non-list JSON.

**Suggested fix:** Log the raw Claude response at WARNING level before setting
`evaluations = []`. Add a single retry before discarding.

---

### MED-16 · `clip/brainrot.py:148` — Excessive stream_loop count for short source clips

**File:** `sable/clip/brainrot.py`, line 148

```python
loops = int(target_duration / src_duration) + 2
```

For a 0.5-second source and a 45-second target, `loops` = 92. FFmpeg seek overhead scales
with loop count. No upper-bound check or warning.

**Production impact:** Very short brainrot clips cause disproportionately slow encoding.

**Suggested fix:** Cap `loops` at a reasonable maximum (e.g., 30) and log a warning when the
source clip is short enough to exceed it.

---

## Section 4 — Low / Cosmetic Issues

Technical debt, observability gaps, and fragile patterns that don't produce incorrect
behavior in normal operation.

---

**LOW-1 · `pulse/meta/fingerprint.py:61` — assert used for runtime validation**
`assert bucket in FORMAT_BUCKETS` is silently disabled under Python `-O`. Invalid format
buckets are written to the database with no error.

**LOW-2 · `pulse/meta/normalize.py:36–77` — Author quality thresholds undocumented**
Scoring thresholds (5, 10, 20 tweets) and lift weights (1.0, 0.8, 0.5, 0.25) are magic
numbers with no comments explaining their derivation.

**LOW-3 · `pulse/meta/normalize.py:235–237` — Per-follower fallback baseline hardcoded**
`_compute_fallback()` uses a hardcoded 0.5%-per-1000-followers engagement rate with no config
key. Wrong for any account with a different typical rate.

**LOW-4 · `advise/stage1.py:37–44` — _compute_lift() engagement weights undocumented**
Weights (likes=1.0, replies=3.0, retweets=4.0, quotes=5.0, bookmarks=2.0, views=0.5) are
hardcoded without justification. These drive the "posts" section of every strategy brief.

**LOW-5 · `pulse/cli.py` — --followers default of 1000 is wrong for all real accounts**
Multiple pulse commands default `--followers` to 1000. No warning that this is a placeholder.
Any account with a different follower count computes wrong ER silently.

**LOW-6 · `vault/notes.py:74–75` — load_all_notes silently skips corrupted files**
`except Exception: pass` — a vault with one corrupted note silently returns all others. No
count of skipped files, no log. Operators can't detect partial vault reads.

**LOW-7 · `clip/selector.py:368,386` — print() in library code**
`print()` used instead of a logging framework for clip kill/extend decisions. Output only
appears on stdout, not in log files or log aggregation.

**LOW-8 · `shared/api.py` — Global Anthropic client is not thread-safe**
`get_client()` uses a module-level `_client` global with a simple None check and no mutex.
Two threads calling simultaneously could both create clients. Makes test isolation harder.

**LOW-9 · `.env` file exists with API keys on disk**
`/Users/sieggy/Projects/Sable_Slopper/.env` contains API credentials. It is in `.gitignore`
and not tracked by git. Keys should be rotated if the machine is ever shared or compromised.
Consider migrating to `~/.sable/config.yaml`, already the intended config location.

**LOW-10 · `pulse/meta/cli.py:436` — Duplicate import statement**
`render_report, write_vault_report` imported at two locations in the same file. No functional
impact.

---

## Section 5 — Cross-Cutting Concerns

Patterns repeated across multiple modules that amplify the impact of single-file bugs.

---

### CC-1 · Silent exception swallowing (pervasive)

The most consistent reliability smell in the codebase:

```python
except Exception:
    pass
# or
except Exception:
    result["some_field"] = []
```

Found in: `stage1.py`, `vault/notes.py`, `vault/sync.py`, `pulse/meta/cli.py`,
`clip/assembler.py`, `clip/thumbnail.py`, `clip/selector.py`, `face/optimize.py`,
`platform/cli.py`, `pulse/meta/db.py`.

None of these log the exception. Production failures become invisible. The fix is consistent:
`logger.warning("...", exc_info=True)` before the fallback assignment.

---

### CC-2 · Timezone consistency

The codebase mixes three conventions:
- `datetime.utcnow()` (naive, deprecated) — `platform/cost.py`, `platform/merge.py`
- `datetime.now(timezone.utc)` (aware, correct) — `roster/manager.py`, `stage1.py`
- SQLite `datetime('now')` (UTC, stored as naive string) — migrations

Naive and aware datetimes compared at DST boundaries or week boundaries produce undefined
results. Enforce one convention: `datetime.now(timezone.utc)` everywhere, stored as ISO8601
with `+00:00`.

---

### CC-3 · Hardcoded constants without config or documentation

Analytically significant constants hardcoded with no config key and no comment:
- `normalize.py`: quality thresholds (5, 10, 20), lift weights (1.0–0.25), fallback baseline
- `stage1.py`: engagement metric weights (1.0, 3.0, 4.0, 5.0, 2.0, 0.5)
- `stage2.py`: token pricing rates per model
- `scanner.py`: retry sleep (5 s), deep mode query count (3), cost per request
- `clip/brainrot.py`: loop count formula (`+2`)

These should be documented with their reasoning or moved to config.

---

### CC-4 · No retry / backoff for external API calls

`_fetch_author_tweets_async()` retries once on 429 with a 5-second sleep.
`stage2.py` `synthesize()` has zero retry logic. `clip/selector.py` Claude calls have zero
retry logic. A transient network hiccup causes hard failure in the middle of a scan or brief.

Exponential backoff with jitter is standard practice. None is implemented anywhere.

---

### CC-5 · Cost tracking decoupled from API call surface

`log_cost()` must be called manually after each Claude API call. No wrapper or decorator
records cost automatically. A new call site added without `log_cost()` is permanently
invisible to budget enforcement.

The platform brief path does this correctly. `clip/selector.py`, `character_explainer/script.py`,
`vault/search.py`, `vault/suggest.py`, `pulse/recommender.py`, `meme/generator.py`, and
`wojak/generator.py` do not.

**Recommendation:** Centralize Anthropic access behind one wrapper that logs and gates spend
where appropriate. Route all Claude call sites through it.

---

### CC-6 · Test coverage gaps in critical paths

Untested or under-tested areas:
- `roster/manager.py` concurrent write behavior
- `vault/notes.py` crash-during-write corruption
- `platform/merge.py` missing-entity crash
- `platform/cost.py` week boundary calculations at DST transitions
- `clip/selector.py` Claude parse failure path
- `pulse/meta/scanner.py` partial-failure scan result shape

---

## Section 6 — Positive Notes

Several patterns in the codebase are already done right and should inform where fixes land:

- **Atomic write pattern exists and works.** `platform_sync.py` already implements
  `_atomic_write()` / `_write_to_temp()` + `os.replace()` correctly. CRIT-2 is about
  extending it to `notes.py`, not inventing it.

- **`_is_inside_vault_root()` shows path-safety awareness.** The guard exists in
  `platform_sync.py`. CRIT-5 is about applying the same thinking to `vault_dir()` itself.

- **The `SableError` structured error system is used consistently** in the platform layer.
  The merge.py crash (CRIT-3) is the exception, not the rule.

- **Cost infrastructure is in place.** `check_budget()`, `log_cost()`, and the `cost_events`
  table are implemented and working for the brief path. CC-5 is a coverage gap, not a
  missing design.

- **`datetime.now(timezone.utc)` is used correctly** in `roster/manager.py` and `stage1.py`.
  HIGH-1 / CC-2 are inconsistencies to bring into line, not a codebase-wide failure.

---

## Short Priority Order

1. **Crash-safe local writes** — CRIT-1 (roster), CRIT-2 (vault notes). Affects every run.
   One reusable helper covers both.
2. **Path traversal** — CRIT-5. Security issue; one-line slug validation.
3. **Missing-entity crash** — CRIT-3. Hard crash on a common real-world operation.
4. **Cost cap in degraded mode** — CRIT-4. Silent spend overrun.
5. **Stage1 silent DB error masking** — HIGH-9. Debugging is impossible without this.
6. **Centralize Claude budget enforcement** — CC-5 / HIGH-2 (shared surfaces). Cost integrity
   across the full LLM surface.
7. **Scanner partial-failure transparency** — HIGH-2 (scanner), HIGH-3, HIGH-4. Analysis
   integrity depends on knowing what actually ran.
8. **Persist deep-mode outsider results** — HIGH-4. Half-implemented feature.
9. **Corrupted artifact cache loop** — HIGH-5. Silent cost accumulation.
10. **Reduce silent exception swallowing** — CC-1. Foundational observability for everything
    above.

---

## Files Audited

| Module | Files |
|--------|-------|
| pulse/meta | db.py, cli.py, scanner.py, fingerprint.py, normalize.py |
| pulse | db.py, cli.py |
| advise | stage1.py, generate.py, stage2.py, template_fallback.py |
| vault | platform_sync.py, notes.py, search.py |
| platform | db.py, cost.py, jobs.py, merge.py, errors.py |
| shared | paths.py, api.py, ffmpeg.py |
| roster | manager.py |
| clip | brainrot.py, selector.py, transcribe.py, assembler.py, cli.py |

## Issue Count Summary

| Severity | Count |
|----------|-------|
| Critical | 5 |
| High | 10 |
| Medium | 16 |
| Low | 10 |
| Cross-cutting | 6 |
| **Total** | **47** |
