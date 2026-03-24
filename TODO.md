# TODO

## Audit Remediation — AR-5

Sourced from `codit.md` full-codebase audit, then refreshed against the live code on
2026-03-24 using the `AGENTS.md` / `docs/QA_WORKFLOW.md` / `docs/PROMPTS.md` /
`docs/THREAT_MODEL.md` review lens.

This file now mixes:
- the current open queue that still matters
- historical AR-5 notes kept for context
- follow-up validation notes from the first implementation batch

Do not assume every item below is still open. Use the **Current Open Queue** first.

Validation snapshot from the 2026-03-24 reconciliation pass:
- `./.venv/bin/python -m pytest -q` → `205 passed`
- `./.venv/bin/ruff check .` → `28` violations
- `./.venv/bin/mypy sable` → `96` errors in `27` files

Validation snapshot after AR-5 batch 2 (2026-03-24):
- `./.venv/bin/python -m pytest -q` → `216 passed`
- `./.venv/bin/ruff check .` → `0` violations
- `./.venv/bin/mypy sable` → `102` errors in `27` files (all pre-existing; no new errors introduced)

---

## Codebase Quality Accounting (Current)

### What is actually healthy

- Core test suite is green: `205` tests passing.
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

### What is still structurally weak

- cross-repo tracking freshness / async contract remains unresolved.
  - strategy + vault readers still use ingestion-time `created_at`
  - this repo still cannot prove the Tracking sync boundary contract from local code alone
- AI spend / prompt-size controls are still uneven outside the org-gated advise/meta flows.
  - selector prompt size is still unbounded before the Claude call
  - `sable/character_explainer/script.py` budget-exempt annotation still missing
- validation is not at a full maintainer-clean baseline.
  - tests green (216 passing)
  - lint clean (ruff 0 violations)
  - mypy red (102 pre-existing errors; no batch-2 regressions)

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

1. Fix output-trustworthiness defects before feature work.
2. Eliminate brief artifact partial writes.
3. Settle the SableTracking freshness / sync contract.
4. Tighten AI spend / prompt-size policy and explicit exemption comments.
5. Only then spend time on lower-signal cleanup or new capability work.

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

## Current Open Queue (2026-03-24 Reconciled Super List)

Reconciled against:
- the original AR-5 refresh in this file
- the later Claude audit pasted into chat
- the live code after the latest fixes

Only items below remain open after direct source re-read.
The following findings were valid but are now resolved in current code and moved to history:
- `pulse/meta` downstream `None`-lift crash in `weighted_mean_lift()` / `assess_format_quality()`
- vault pulse-report partial-sync gap in `platform_sync.py`
- `advise/stage2.py` wrapper bypass and `pulse/meta/analyzer.py` missing `org_id`
- `advise/generate.py` partial-write safety (items 1 — RESOLVED AR-5 batch 2)
- `advise/stage1.py` silent parse fallbacks (item 2 — RESOLVED AR-5 batch 2)
- `advise/generate.py` deterministic data caveats block (item 3 — RESOLVED AR-5 batch 2)
- `tracker.py` insert_post bool not captured (FOLLOW-UP-2 — RESOLVED AR-5 batch 2)
- ruff lint violations: 28 → 0 (FOLLOW-UP-3 — RESOLVED AR-5 batch 2)
- missing T1/T2/T3/T4 tests (FOLLOW-UP-5 — RESOLVED AR-5 batch 2)

### 1. CRIT · `advise/generate.py` partial-write safety — RESOLVED (AR-5 batch 2)

Temp→swap→restore pattern with backup file implemented. Tests added covering DB failure
with and without prior file on disk. Marked resolved; keep notes in history section.

### 2. HIGH · `advise/stage1.py` silent parse fallbacks — RESOLVED (AR-5 batch 2)

All 3 bare-except blocks now emit `logger.warning(...)` with `org_id` context, set
appropriate degraded flags, and append to `failed_sources`. Tests in
`tests/advise/test_stage1.py` cover all 3 paths. Marked resolved.

### 3. HIGH · Advise brief deterministic data caveats block — RESOLVED (AR-5 batch 2)

`generate.py` now derives a `## Data Caveats` block from `data_quality`, `meta_stale`,
and `failed_sources` and prepends it to `brief_body` before file write. Tests in
`tests/advise/test_advise.py` verify presence/absence of the block. Marked resolved.

### 4. HIGH · SableTracking contract alignment: async wrapper + source-time freshness

**Files:** `sable/commands/tracking.py`, `sable/advise/stage1.py`,
`sable/vault/platform_sync.py`

There are two related cross-repo contract issues with SableTracking:

1. **Wrapper contract verification:** Slopper currently calls `sync_to_platform(org_id)` as if
   it were synchronous in `sable/commands/tracking.py`. The implementation lives in the
   external Tracking repo (`app.platform_sync`), so this repo cannot prove alone whether the
   function is sync or async. If Tracking currently exports `async def sync_to_platform(...)`,
   the Slopper wrapper is wrong and needs a local sync shim (`asyncio.run(...)` or equivalent).

2. **Freshness semantics:** Slopper currently treats `content_items.created_at` as the source
   content timestamp in strategy/vault consumers. That is wrong for synced or backfilled
   tracker content, because local ingestion time can be much newer than the source post time.
   Confirmed current readers:
   - `sable/advise/stage1.py` filters and orders tracker content by `created_at`
   - `sable/vault/platform_sync.py` orders and displays tracker content by `created_at`

**Required coordination with Tracking:**
- agree on the source-time field for tracker content, e.g.:
  - a first-class `published_at` / `source_created_at` column, or
  - a stable key in `metadata_json`
- clarify whether `created_at` means ingestion time only
- clarify whether `sync_to_platform()` is sync or async at the contract boundary

**Slopper-side follow-up once the contract is settled:**
- update the tracking CLI wrapper if Tracking exports an async sync entrypoint
- update strategy/vault readers to use the agreed source-time field for cutoff/order/display
- keep `created_at` for local ingestion/audit semantics only
- extend consumers to ingest richer tracker metadata where useful:
  - `url`
  - `platform`
  - other source metadata beyond `body`/summary

**Tests:**
- wrapper test: if `sync_to_platform()` is async, CLI still completes and records counts
- tracker freshness test: backfilled content with old `published_at` but new local `created_at`
  does not appear artificially fresh in `assemble_input()`
- vault sync test: tracker items are ordered/displayed by source publish time, not ingestion time
- metadata propagation test: once contract lands, `url` / `platform` survive into strategy or
  vault consumers without relying on ad hoc JSON parsing at every call site

### 5. HIGH · Explicit log/error secret scrubbing audit

This repo does not currently have a confirmed runtime secret leak matching the external audit,
but the risk class is valid here and still under-specified. We already require `.env`
gitignore and no secret interpolation in outputs; we do **not** yet have a focused pass on:
- exception logging in platform / vault / advise / pulse-meta flows
- whether upstream client/library exceptions can embed auth material
- whether any persisted local logs or reports could capture keys from config/env-derived state

**Scope for the next audit/fix pass:**
- search all explicit logging/traceback persistence paths
- confirm that no config dict, header dict, or client repr with keys/tokens is persisted
- add redaction where runtime error persistence exists

**Tests / checks:**
- synthetic exception containing `ANTHROPIC_API_KEY=test-secret` is redacted before persistence
- no generated artifact or error log path stores raw key-looking values

### 6. MED · AI spend / prompt-size controls remain uneven outside the org-gated paths

**Files:** `sable/clip/selector.py`, `sable/clip/thumbnail.py`,
`sable/character_explainer/script.py`, `sable/shared/api.py`

Confirmed current gaps:
- `select_clips()` builds `windows_text` from **all** detected windows before any cap
- `_evaluate_variants_batch()` evaluates **all** candidate clips before `max_clips` trims
  the final result
- some intentionally org-exempt Claude call sites still lack an explicit
  `# budget-exempt:` comment:
  - `sable/clip/thumbnail.py`
  - `sable/character_explainer/script.py`

**Fix strategy:**
- add a pre-LLM cap or batching rule for the initial window-selection prompt
  (`max_windows_per_llm_batch` or equivalent)
- add a pre-variant-eval cap or batching rule so `max_clips` is not the first limit applied
  after all variants have already been sent to Claude
- merge / de-dupe batch results before final scoring
- annotate every intentionally org-exempt Claude call site with a consistent reason, or pass
  `org_id` where the call is actually org-scoped

**Tests:**
- a transcript with 40+ windows is split into bounded-size LLM batches rather than one
  monolithic prompt
- variant-eval prompt size is bounded before the final `max_clips` trim
- targeted grep/test proves each non-org Claude call site is either explicitly budget-exempt
  or passes `org_id`

### 7. MED · Validation debt is now a tracked backlog, not a green baseline

The repo is test-green but not lint-clean or type-clean. Current repo-wide snapshot:
- `pytest` → `205 passed`
- `ruff` → `28` violations
- `mypy` → `96` errors in `27` files

Keep using repo-wide commands as the source of truth. No batch should be described as “clean”
unless those repo-wide commands also exit `0`.

### 8. LOW · `pulse/linker.py::auto_link_posts()` is still a feature-shaped stub

**File:** `sable/pulse/linker.py`

`auto_link_posts()` still fetches unlinked DB rows and then always returns `[]` with a comment
that manual linking is the primary path. This is not a production break, but it is misleading
maintainer-facing surface area: it looks like a real auto-linker while behaving as a permanent
stub.

**Fix options:**
- either implement a minimal caption-similarity linker
- or rename/re-scope the function / CLI surface so the placeholder nature is explicit

**Tests:**
- if kept as placeholder, test and doc should state that it is intentionally no-op
- if implemented, add duplicate / threshold / false-positive tests before exposing it as live

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
`sable/platform/cli.py`, `sable/pulse/meta/cli.py`

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

Priority order within this item:
1. `advise/stage1.py` — four DB read blocks (86–129, 156–199, 243–269, 270–279)
2. `vault/search.py` — Claude→keyword fallback
3. `vault/sync.py` — lines 251–265
4. `platform/cli.py` — lines 101–129

`pulse/meta/cli.py` fallback analysis frontmatter/banner has already landed. Remaining work
under this item is the other silent fallback paths listed above.

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

**AR5-11 · Corrupted artifact cache rows loop forever — `generate.py:31–61` (HIGH-6)**
Fix: On JSON parse failure for a cache row, mark it stale so the stale=0 filter excludes
it on the next cache lookup:
```python
except (json.JSONDecodeError, KeyError):
    conn.execute("UPDATE artifacts SET stale=1 WHERE artifact_id=?", (row["artifact_id"],))
    continue
```
Adding a separate `corrupt` column is an option if distinguishing "stale" (outdated) from
"unreadable" (malformed JSON) matters for reporting, but requires a migration and is heavier
than necessary if the product doesn't need that distinction.

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

### Round 2 — Cult Doctor (community health grader) (2026-03-23)
- Read `sable.db` entities/tags per org to produce health scores
- Write `diagnostic_runs` rows + `artifacts` (playbook, strategy brief)
- CLI: `sable cult-doctor run <org_id>`

### Round 3 — SableTracking integration (2026-03-23)
- Bridge SableTracking Discord data → `sable.db` entities + handles
- Write `sync_runs` rows per ingest
- Trigger `mark_artifacts_stale()` on new data arrival
- CLI: `sable tracking sync <org_id>`

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
