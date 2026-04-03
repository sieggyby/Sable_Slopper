# TODO

---

## Validation Snapshot

- `./.venv/bin/python -m pytest -q` → `634 passed`
- `./.venv/bin/ruff check .` → 0
- `./.venv/bin/mypy sable` → 0

---

## Structural Debt

### AI spend observability gap

Non-org Claude call sites (content generation flows like clip/thumbnail/write without
`--org`) remain intentionally budget-exempt. Spend is not observable in a single place
for these flows. Org-scoped advise/meta paths are fully gated.

**When to fix:** When a second active client makes cost attribution important.

### Stale test schemas

Some tests still encode stale producer/consumer schemas that don't match the live
contracts. Lint and mypy are clean; the issue is semantic correctness of test fixtures.

---

## Phase 2 — `sable serve` FastAPI Backend

**Status:** NOT STARTED
**Consumer:** SableWeb (Next.js portal, separate repo at `~/Projects/SableWeb`)
**Reference:** `docs/ROADMAP.md` Phase 2 section, `docs/ROLES.md`, `docs/SCHEMA_INVENTORY.md`
**Why now:** SableWeb is transitioning from hardcoded mock data to live data. SableWeb reads sable.db directly for entity/diagnostic/action data, but vault inventory, pulse performance, and meta intelligence data live in Slopper's databases (pulse.db, meta.db) and must be exposed via HTTP.

---

### Architecture

```
SableWeb (Next.js)
    │
    │  HTTP (localhost:8420)
    │  Authorization: Bearer <service-token>
    ▼
sable serve (FastAPI)
    │
    ├── pulse.db   (posts, snapshots, account_stats)
    ├── meta.db    (scanned_tweets, format_baselines, topic_signals)
    └── vault/     (markdown content notes in ~/.sable/vault/)
```

**Key constraints:**
- Read-only API. No write endpoints in Phase 2.
- Service-to-service auth only. SableWeb authenticates users; `sable serve` validates a shared token.
- Org-scoped. Every endpoint takes an `org` parameter and queries only that org's data.
- Same machine. SableWeb and `sable serve` run on the same host. No CORS needed (proxied).

---

### File Structure

```
sable/serve/
├── __init__.py          ← exists (stub docstring)
├── app.py               ← FastAPI app factory, lifespan, CORS
├── auth.py              ← token auth dependency
├── routes/
│   ├── __init__.py
│   ├── vault.py         ← vault inventory + content browser
│   ├── pulse.py         ← posting log, snapshots, format performance
│   └── meta.py          ← topic signals, format baselines, watchlist health
└── deps.py              ← shared dependencies (DB connections, path resolution)
```

---

### Dependencies To Add

```
# pyproject.toml [project.optional-dependencies]
serve = ["fastapi>=0.115", "uvicorn[standard]>=0.32"]
```

Optional dependency group — `pip install -e ".[serve]"`. Does not affect CLI-only usage.

---

### CLI Entry Point

Add `serve` command to `sable/cli.py`:

```python
@cli.command()
@click.option("--host", default="127.0.0.1")
@click.option("--port", default=8420, type=int)
@click.option("--reload", is_flag=True, help="Auto-reload on file changes (dev only)")
def serve(host: str, port: int, reload: bool):
    """Start the Sable API server (Phase 2)."""
    import uvicorn
    uvicorn.run("sable.serve.app:create_app", host=host, port=port, reload=reload, factory=True)
```

---

### Auth (`sable/serve/auth.py`)

```python
from fastapi import Depends, HTTPException, Request
from sable.config import get as get_config

def verify_token(request: Request):
    """Validate service-to-service Bearer token."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Missing token")
    token = auth[7:]
    expected = get_config("serve.token")  # from ~/.sable/config.yaml
    if not expected:
        raise HTTPException(500, "serve.token not configured")
    if token != expected:
        raise HTTPException(403, "Invalid token")
```

Config key: `serve.token` in `~/.sable/config.yaml`. Generate with `python -c "import secrets; print(secrets.token_hex(32))"`.

---

### Endpoints

#### Vault Routes (`sable/serve/routes/vault.py`)

**GET `/api/vault/inventory/{org}`**

Returns vault content inventory for an org: total produced, posted, unused, by-format breakdown, unused assets list, recent posted with performance.

Source: `load_all_notes()` from `sable/vault/search.py`, filtered by org. Cross-reference with `pulse.db posts` for posted status and engagement.

Response shape (matches SableWeb `ContentPipeline` ops type):
```json
{
  "total_produced": 52,
  "total_posted": 38,
  "total_unused": 14,
  "stale_threshold_days": 14,
  "by_format": [
    {"format": "meme", "produced": 30, "posted": 19, "unused": 11}
  ],
  "unused_assets": [
    {"title": "...", "format": "meme", "produced_at": "2026-03-03", "age_days": 18}
  ],
  "recent_posted": [
    {"title": "...", "format": "meme", "produced_at": "...", "posted_at": "...",
     "performance": {"engagement": 847, "format_avg": 512, "lift": 1.65}}
  ]
}
```

Implementation: Reuse `load_all_notes(vault_path, org)` → filter by `posted_by` / `suggested_for` → cross-reference `pulse.db posts` for engagement data → compute age, staleness, format breakdown.

---

**GET `/api/vault/search/{org}?q={query}&limit={n}`**

Wraps `search_vault()`. Returns ranked content notes matching query.

Response: `[{"title": "...", "path": "...", "score": 0.92, "format": "meme", "frontmatter": {...}}]`

---

#### Pulse Routes (`sable/serve/routes/pulse.py`)

**GET `/api/pulse/performance/{org}`**

Returns content performance data for an org over the last 30 days.

Source: `pulse.db posts + snapshots`, grouped and aggregated.

Response shape (matches SableWeb `ContentPerformance` client type):
```json
{
  "total_posts": 98,
  "sable_posts": 38,
  "organic_posts": 60,
  "sable_share_of_engagement": 0.64,
  "sable_avg_engagement": 1247,
  "organic_avg_engagement": 412,
  "sable_lift_vs_organic": 2.03,
  "top_performing_formats": [...],
  "by_format": [...],
  "weekly_trend": [
    {"week": "W09", "sable_engagement": 12400, "organic_engagement": 8200, "sable_share": 0.6}
  ],
  "meta_informed": {
    "meta_informed_posts": 26,
    "meta_informed_avg": 1580,
    "non_meta_avg": 620,
    "meta_lift": 1.55
  }
}
```

Implementation:
1. Query `pulse.db posts` for org's accounts (via roster) in last 30 days
2. Join with latest `snapshots` per post for engagement metrics
3. Classify sable vs organic using `sable_content_type` field (non-null = sable)
4. Group by format (`sable_content_type` mapped to format buckets)
5. Compute weekly aggregates using `posted_at` week extraction
6. Cross-reference `meta.db format_baselines` for meta-informed classification

**Sable vs organic split:** Posts with `sable_content_type IS NOT NULL` or `sable_content_path IS NOT NULL` are Sable posts. Everything else from the org's tracked accounts is organic. This is the same heuristic the CLI `sable pulse report` uses.

---

**GET `/api/pulse/posting-log/{org}?days={n}`**

Returns raw posting log. Source: `pulse.db posts + snapshots`.

Response: `[{"url": "...", "text": "...", "posted_at": "...", "likes": 1200, "replies": 34, ...}]`

---

#### Meta Routes (`sable/serve/routes/meta.py`)

**GET `/api/meta/topics/{org}`**

Returns topic signals from the most recent meta scan.

Source: `meta.db topic_signals` WHERE org = :org, ordered by `avg_lift` desc.

Response shape (matches SableWeb `TopicSignal` type):
```json
[
  {"topic": "ZK proof mechanics", "momentum_score": 0.82, "confidence": "high", "trend_status": "rising"}
]
```

Implementation: Query `topic_signals` for latest `scan_id` for org. Map `avg_lift` → `momentum_score`, compute `trend_status` from acceleration field, derive `confidence` from `mention_count` thresholds.

---

**GET `/api/meta/baselines/{org}`**

Returns format baseline data (lift per format bucket).

Source: `meta.db format_baselines` WHERE org = :org.

Response shape (matches SableWeb `FormatLiftSignal` type):
```json
[
  {"format": "meme", "signal": "DOUBLE_DOWN", "rationale": "Image-led thesis posts at 3,716 avg..."}
]
```

Implementation: Query `format_baselines` for latest 30d window. Classify signal using lift thresholds: >1.5 = DOUBLE_DOWN, <0.7 = EXECUTION_GAP, else PERFORMING. Generate rationale string from baseline numbers.

---

**GET `/api/meta/watchlist/{org}`**

Returns watchlist health diagnostics (coverage, staleness, scan history).

Source: `meta.db scan_runs + author_profiles` WHERE org = :org.

Response: `{"total_authors": 45, "stale_authors": 3, "last_scan": "2026-03-20", "coverage": 0.93}`

---

### App Factory (`sable/serve/app.py`)

```python
from fastapi import FastAPI
from sable.serve.routes import vault, pulse, meta

def create_app() -> FastAPI:
    app = FastAPI(title="Sable API", version="0.1.0")
    app.include_router(vault.router, prefix="/api/vault", tags=["vault"])
    app.include_router(pulse.router, prefix="/api/pulse", tags=["pulse"])
    app.include_router(meta.router, prefix="/api/meta", tags=["meta"])

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app
```

---

### Shared Dependencies (`sable/serve/deps.py`)

```python
import sqlite3
from functools import lru_cache
from sable.shared.paths import resolve_path

@lru_cache
def get_pulse_db() -> sqlite3.Connection:
    conn = sqlite3.connect(resolve_path("pulse.db"), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

@lru_cache
def get_meta_db() -> sqlite3.Connection:
    path = resolve_path("pulse/meta.db")
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn
```

---

### Tests

```
tests/serve/
├── test_app.py              — app factory, health endpoint
├── test_auth.py             — token validation, missing/invalid token
├── test_vault_routes.py     — inventory, search (with fixture vault notes)
├── test_pulse_routes.py     — performance aggregation, weekly trend
└── test_meta_routes.py      — topic signals, baselines, watchlist
```

Use `fastapi.testclient.TestClient`. Create fixture SQLite databases with known data. Verify response shapes match SableWeb TypeScript type expectations.

---

### Implementation Order

```
1. app.py + auth.py + deps.py + health endpoint + CLI serve command
2. pulse routes (performance, posting-log) — most data, highest value
3. meta routes (topics, baselines, watchlist) — extends pulse
4. vault routes (inventory, search) — requires vault note loading
5. Tests for all routes
```

Each step is independently deployable. SableWeb can start consuming pulse data while vault routes are still in progress.

---

### Validation

```bash
./.venv/bin/python -m pytest tests/serve/ -q
./.venv/bin/ruff check sable/serve/
./.venv/bin/mypy sable/serve/
# Manual: curl http://localhost:8420/health
# Manual: curl -H "Authorization: Bearer <token>" http://localhost:8420/api/pulse/performance/psy_protocol
```

---

## Audit Remediation Queue (2026-04-01)

**Status: COMPLETE (2026-04-02).** All AUDIT items landed with adversarial QA sign-off.
634 tests passing, ruff clean, mypy clean.

### AUDIT-1 · Secret handling + CLI error redaction hardening

**Risk level:** Tier 1 — credential exposure.

**Status:** ✅ Complete (2026-04-02).

**What shipped:**
- ✅ `config show` masks secrets with `(set)` / `(not set)` via `_SECRET_CONFIG_KEYS`
- ✅ `config set` refuses secret keys entirely; directs operators to env vars
- ✅ `require_key()` error message points to env var, not `config set`
- ✅ `SECRET_ENV_MAP` canonical mapping in `sable/config.py`, imported by `cli.py`
- ✅ `elevenlabs_api_key` added to `_DEFAULTS` and `SECRET_ENV_MAP`
- ✅ All 40+ CLI exception handlers redact via `redact_error()` (18 files)
- ✅ `redact_error` patterns cover: `sk-ant-*`, `r8_*` (bare), env var assignments,
  Bearer tokens, `xi-api-key` headers
- ✅ Tests: 9 config show/set, 8 CLI error redaction, 11 redact_error unit

### AUDIT-2 · SocialData response validation before persistence

**Risk level:** Tier 1 — silent data corruption / misleading outputs.
**Status:** ✅ Complete (2026-04-02).

**Why this is a real bug:**
- `sable/pulse/meta/scanner.py::_normalise_tweet()` currently trusts malformed
  SocialData payloads and converts missing engagement fields into zero-valued tweets
- those rows are then persisted normally by `sable/pulse/meta/db.py::upsert_tweet()`
- a provider shape drift can silently poison baselines, trends, digest inputs, and
  downstream Claude analysis

**Relevant files (with Codex line refs):**
- `sable/pulse/meta/scanner.py` — `:26,:68,:81` (`_normalise_tweet` trusts malformed payloads)
- `sable/pulse/meta/db.py` — `:216` (`upsert_tweet` persists without validation)
- maybe `sable/pulse/meta/fingerprint.py` and `sable/pulse/meta/normalize.py` if a small
  validation boundary type/helper is cleaner

**Required behavior change:**
- Validate required tweet fields before writing to `meta.db`
- if a tweet is malformed, skip it or mark it explicitly as invalid/degraded; do not
  silently coerce it into a normal zero-engagement record
- preserve scan completion when only some tweets are malformed
- surface the problem with a warning so operators can tell the upstream shape changed

**Implementation notes:**
- Keep this at the scanner boundary; do not spread field checks across downstream stages
- minimum useful validation: non-empty tweet id, parseable/postable timestamp when
  required for recency filtering, and sane numeric engagement fields
- avoid broad schema frameworks or new dependencies; a local validator/helper is enough

**Acceptance criteria:**
- malformed API payloads do not enter `scanned_tweets` as normal rows
- well-formed tweets in the same scan still process successfully
- operator gets a warning or count of skipped malformed rows

**Exact tests to add:**
- `tests/pulse/meta/test_scanner_validation.py`
  - malformed tweet missing id is skipped
  - malformed engagement payload does not become a persisted zero-engagement row
  - mixed batch with one bad tweet still saves the valid tweet(s)
  - warning path is exercised

### AUDIT-3 · Thin-sample trustworthiness gate for `sable pulse recommend`

**Risk level:** Tier 1 — confident but misleading client-facing output.
**Status:** ✅ Complete (2026-04-02).

**Why this is a real bug:**
- `sable/pulse/recommender.py::generate_recommendations()` will produce full Claude
  recommendations from any non-empty scored sample, even a single post
- there is no minimum-sample threshold or uncertainty disclosure
- this violates the repo’s “do not present thin data as strong signal” guidance

**Relevant files (with Codex line refs):**
- `sable/pulse/recommender.py` — `:35,:41,:87` (`generate_recommendations` has no sample-size
  gate; `:87` also bypasses `org_id` — overlaps AUDIT-5)
- `sable/pulse/cli.py`
- possibly `docs/COMMANDS.md` if CLI output semantics need documenting

**Required behavior change:**
- introduce a minimum-sample gate before Claude recommendations are generated
- when sample size is too small, return a truthful insufficiency result instead of
  pretending the tool has strong guidance
- the insufficiency result should explain what to do next, e.g. track more posts first
- if you still show any guidance on thin samples, it must be labeled as low-confidence

**Implementation notes:**
- keep the contract similar: return a dict with `summary`, `recommendations`,
  `content_ideas`, and `avoid`, but make the message explicitly low-confidence or
  insufficient-data
- choose a simple threshold and encode it in tests

**Acceptance criteria:**
- one-post or very small samples do not produce normal-strength recommendation payloads
- larger samples still use the current Claude flow
- CLI output remains readable in both cases

**Exact tests to add:**
- extend `tests/pulse/test_recommender.py`
  - one-post sample returns insufficiency / low-confidence summary
  - thin-sample path does not call Claude
  - sample above threshold still calls Claude once and preserves current behavior

### AUDIT-4 · Small-vault search fallback parity

**Risk level:** Tier 1 — avoidable operator-facing failure in a core workflow.
**Status:** ✅ Complete (2026-04-02).

**Why this is a real bug:**
- `sable/vault/search.py::search_vault()` only falls back to keyword ranking when the
  candidate set is `> 50`
- for `<= 50` candidates it calls Claude directly and lets failures escape
- `sable/vault/suggest.py` depends on `search_vault()`, so reply suggestions inherit the
  same fragility on smaller vaults

**Relevant files (with Codex line refs):**
- `sable/vault/search.py` — `:56,:61` (`search_vault` small-candidate branch has no fallback)
- `sable/vault/suggest.py` — `:102,:133,:144` (depends on `search_vault`, inherits fragility)
- existing tests in `tests/vault/test_search.py`
- possibly `tests/vault/test_suggest.py`

**Required behavior change:**
- Claude ranking failure should degrade to deterministic keyword results regardless of
  candidate count
- preserve the current `> 50` prescore behavior, but give the `<= 50` branch the same
  resilience contract
- keep `vault suggest` functional when ranking fails

**Implementation notes:**
- do not rewrite search quality logic
- the smallest safe patch is likely to route both branches through one common fallback path

**Acceptance criteria:**
- `search_vault()` never hard-fails just because Claude ranking is unavailable
- fallback results are still bounded by `config.max_suggestions`
- `vault suggest` returns zero or degraded suggestions cleanly rather than crashing

**Exact tests to add:**
- extend `tests/vault/test_search.py`
  - `<= 50` candidates + Claude failure returns keyword `SearchResult`s instead of raising
  - `> 50` branch still behaves as before
- optionally extend `tests/vault/test_suggest.py`
  - reply suggestion flow survives a ranking failure upstream

### AUDIT-5 · Org-scoped Claude budget enforcement gaps

**Risk level:** Tier 1/Tier 2 — burns money and breaks the platform contract.
**Status:** ✅ Complete (2026-04-02).

**Why this is a real bug:**
- the shared Claude wrapper already enforces budget + cost logging when `org_id` is
  passed
- several org-aware features still call Claude without `org_id`, so weekly caps and
  `cost_events` are bypassed
- the most concrete bug is in watchlist digest: it tries to resolve orgs using
  `SELECT id FROM orgs WHERE slug = ?`, but the actual schema stores `org_id` and has no
  `id` or `slug` columns

**Relevant files (with Codex line refs):**
- `sable/shared/api.py` — `:147,:153` (swallows `log_cost` failure silently)
- `sable/pulse/meta/digest.py` — `:128,:132,:135,:143` (org lookup uses wrong column names
  `id`/`slug` instead of `org_id`; Claude calls not org-scoped)
- `sable/pulse/meta/cli.py` — `:552` (digest subcommand does not thread org context)
- `sable/pulse/recommender.py` — `:87` (calls Claude without `org_id` despite having `account.org`)
- `sable/write/scorer.py` — `:112,:158` (`get_hook_patterns` and `score_draft` bypass org budget)
- `sable/vault/search.py` — `:146` (`claude_rank` not org-scoped)
- `sable/vault/suggest.py` — `:133` (`_draft_reply_texts` not org-scoped)
- schema reference: `sable/db/migrations/001_initial.sql`

**Required behavior change:**
- fix digest org lookup to the real schema (`org_id`)
- ensure digest Claude calls are actually org-scoped when an org is known
- cap or otherwise bound `sable pulse meta digest --top` so a user cannot fan out an
  unbounded number of per-post Claude calls on anatomy cache misses
- thread `org_id` through the remaining org-aware Claude callers where org context is
  already available

**Likely call sites to harden:**
- `pulse/meta/digest.py::_analyze_post_for_digest()`
- `pulse/recommender.py::generate_recommendations()` using `account.org`
- `write/scorer.py::get_hook_patterns()` and `score_draft()` using resolved org
- `vault/search.py::claude_rank()` and `vault/suggest.py::_draft_reply_texts()` using
  the `org` argument that is already in the function signature

**Implementation notes:**
- do not change truly non-org generation flows that are intentionally annotated
  `# budget-exempt`
- the target is org-aware flows only
- keep this centralized: prefer passing `org_id` into existing `call_claude_json(...)`
  calls rather than building bespoke logging
- `sable/shared/api.py` currently swallows `log_cost(...)` failures silently. That should
  become a visible warning in logs; otherwise cost observability can still fail without
  operators or maintainers noticing.

**Acceptance criteria:**
- org-aware recommendation/search/scoring/digest flows log spend through the shared wrapper
- digest no longer silently loses org context due to bad SQL
- `meta digest --top` has a sane ceiling or other explicit bound
- a failed `log_cost(...)` attempt emits a warning rather than disappearing silently

**Exact tests to add:**
- extend `tests/pulse/meta/test_digest.py`
  - digest resolves org via real schema and passes non-`None` `org_id` to `call_claude_json`
  - large `--top` input is capped/bounded
- extend `tests/pulse/test_recommender.py`
  - recommender passes `account.org` into `call_claude_json`
- extend `tests/write/test_scorer.py`
  - hook-pattern generation and draft scoring pass `org_id`
- add/extend vault tests
  - `search_vault()` passes `org_id`
  - reply-draft generation passes `org_id`
- add `tests/shared/test_api.py`
  - if `log_cost(...)` raises inside the shared wrapper, the Claude call still succeeds
    but a warning is logged

### AUDIT-6 · Follow-up maintainability cleanup after the fixes above

**Risk level:** Tier 2 — hidden coupling.
**Status:** ✅ Complete (2026-04-02). Addressed via `SECRET_ENV_MAP` deduplication and org_id threading.

**Why this matters:**
- budget enforcement currently depends on each call site remembering to pass `org_id`
- this is the hidden coupling behind the repeated misses above

**Goal:**
- after landing AUDIT-5, do a light cleanup in touched files so the org-aware Claude
  contract is obvious and hard to forget
- avoid a rewrite; just reduce repetition and ambiguity where the patch already touches code

**Acceptable scope:**
- helper variables like `resolved_org_id`
- comments explaining why a path is intentionally `budget-exempt`
- small local helper functions in touched modules only

**Do not do:**
- broad abstraction work across untouched modules
- large interface redesigns

### AUDIT-7 · Remove silent degradation in operator-facing audit flows

**Risk level:** Tier 2, with Tier 1 spillover when failures hide stale or untrustworthy output.
**Status:** ✅ Complete (2026-04-02).

**Why this is missing from the queue:**
- several of the exact paths touched by AUDIT-4 and AUDIT-5 still use broad
  `except Exception: pass` / silent fallback patterns
- the repo convention already says broad exception handlers should log warnings, but the
  current queue did not make that an explicit acceptance target
- if these swallows remain, the repo can still “look healthy” while quietly skipping
  reply drafts, cost logging, digest org resolution, or other degraded behavior

**Relevant files:**
- `sable/shared/api.py`
- `sable/vault/suggest.py`
- `sable/pulse/meta/digest.py`
- any touched file in AUDIT-1 through AUDIT-5 that currently degrades silently instead of
  logging a warning

**Required behavior change:**
- when an operator-facing path degrades but continues, emit `logger.warning(...)`
  with enough context to debug the issue
- keep the current resilient behavior where appropriate; this item is about visibility,
  not turning every degradation into a hard crash
- do not add noisy stack traces to normal user-facing terminal output; log the warning
  and keep CLI output clean

**Implementation notes:**
- this is intentionally scoped to files already being touched by the audit-remediation
  batch; do not go repo-wide and churn unrelated modules
- especially important cases:
  - `vault/suggest.py` account-context fallback and reply-draft generation failure
  - `pulse/meta/digest.py` org lookup failure and per-post Claude analysis failure
  - `shared/api.py` cost-log failure after a successful Claude call

**Acceptance criteria:**
- degraded reply suggestion / digest / cost-log paths are observable in logs
- the CLI still returns usable output where graceful degradation is intended
- no new silent `pass` blocks are introduced in touched files

**Exact tests to add:**
- extend or add tests covering warning emission for:
  - reply-draft generation fallback in `vault/suggest.py`
  - digest org-resolution or per-post analysis fallback in `pulse/meta/digest.py`
  - shared wrapper `log_cost(...)` failure in `sable/shared/api.py`

### AUDIT-8 · Migration test version assertions are stale

**Risk level:** Tier 3 — test maintenance.
**Status:** ✅ Complete (2026-04-02). Version derived from `_MIGRATIONS` source of truth.

**Why this fails:**
- `tests/platform/test_migration.py` hardcodes schema version `14` in three places
  (`:9,:30,:39`) but the live schema is at version `15`
- this causes 3 test failures that are unrelated to any code change

**Relevant files:**
- `tests/platform/test_migration.py` — lines 9, 30, 39

**Fix:** Update the hardcoded version from `14` to `15` in all three assertions.

**Acceptance criteria:**
- `pytest tests/platform/test_migration.py` passes
- validation snapshot returns to `0 failed`

---

### Validation for the full audit-remediation batch

Run after landing any of AUDIT-1 through AUDIT-5:

```bash
./.venv/bin/python -m pytest -q
./.venv/bin/ruff check .
./.venv/bin/mypy sable
```

Current baseline (post full audit remediation + Codex hardening + SocialData hardening, 2026-04-02):
- `./.venv/bin/python -m pytest -q` → `634 passed`
- `./.venv/bin/ruff check .` → 0
- `./.venv/bin/mypy sable` → 0

---

## SocialData API Hardening (2026-04-02)

**Status: COMPLETE.** Audited against `SablePlatform/docs/SOCIALDATA_BEST_PRACTICES.md`.

**What shipped:**
- ✅ Centralized HTTP client: `sable/shared/socialdata.py` — all 4 modules use `socialdata_get_async` / `socialdata_get`
- ✅ **402 fatal handling:** `BalanceExhaustedError` raised immediately, no retry, propagates past per-author exception handlers in scanner
- ✅ **429 exponential backoff + jitter:** 1s→4s→16s→64s schedule (was: flat 5s single retry in scanner only, zero handling in tracker/trends/suggest)
- ✅ **5xx retry:** Same schedule as 429 (was: raise immediately, no retry)
- ✅ **Network error retry:** Timeouts, DNS, connection resets retried with same schedule
- ✅ Removed duplicate `_get_headers()`, `_BASE_URL`, direct `httpx` imports from scanner.py, tracker.py, trends.py, suggest.py
- ✅ Fixed pre-existing endpoint bug: `suggest.py` used `/twitter/tweet/{id}` (singular), corrected to `/twitter/tweets/{id}` (plural)
- ✅ 9 new tests in `tests/shared/test_socialdata.py` covering 402, 429 retry+exhaust, 5xx, 200, 404, network error retry+exhaust, backoff schedule

**Known remaining gaps (low priority):**
- No per-phase cost breakdown in scanner (tracks total only)
- No cost tracking in tracker.py, trends.py, suggest.py (infrequent use)
- No cursor cycling detection (not currently exploitable — single-page fetches only)
- No checkpoint/resume (scan sizes well under 50 calls)

---

## FEATURE-3 (`sable pulse account`) — Remaining Items

- **`_classify_post` thread-detection gap** (known V1 limitation): `sable_content_type='text'`
  always passes `is_thread=False` because pulse.db has no thread marker. Text threads
  miscategorized as `standalone_text`. Requires pulse.db schema change to fix.

---

## Clip Pipeline Upgrades

Sourced from competitive audit of `samuraigpt/ai-youtube-shorts-generator` (2026-04-01).

### CLIP-2 · Face-centered crop for multi-speaker content

Current `stack_videos` (`shared/ffmpeg.py`) uses a static `scale+crop` filter that
center-crops the source panel. For interview content where speakers switch sides of
frame, a face-tracking crop would keep the largest detected face centered.

**Clarification:** This is face-centered cropping, not active-speaker detection. True
speaker identification would require audio diarization (pyannote) or lip-movement
analysis — neither is in scope. This tracks the largest face per frame.

**Approach:** Face detection (dlib HOG via `face_recognition`) every 10th frame (~3fps),
interpolated positions for intermediate frames. Smoothed crop x-offset via exponential
smoothing (e.g. 0.85 previous + 0.15 new). FFmpeg `crop` filter with per-frame offset.

**Dependency:** `face_recognition` is currently an optional import with try/except
fallback in `thumbnail.py`. It is NOT a declared dependency in `pyproject.toml` (dlib
requires CMake + C++ toolchain). Decision needed: (a) declare it as a hard dep, or
(b) keep optional and fall back to center-crop when unavailable. Option (b) is safer.

**Where it lives:** Detection + smoothing logic in new `sable/clip/face_track.py` (not
`shared/ffmpeg.py` — that module is pure FFmpeg subprocess wrappers). Only the final
crop-filter generation touches `ffmpeg.py`. Called from `assembler.py` when `--face-track`
flag is passed. Default off — static crop remains the default.

**Applies to:** Both `stack_videos` and `encode_clip_only` paths. Ignored when
`--audio-only` is set (no source video panel to crop).

**Edge cases:**
- Zero faces for entire clip → fall back to center crop
- Face appears/disappears mid-clip → hold last known position, decay to center
- Multiple faces → track largest, or nearest to previous position
- Performance budget: ~1-2x assembly time overhead at 720p with dlib HOG at 3fps

**When to build:** When a client asks for interview/podcast clip quality improvements, or
when we start processing multi-camera content. Build CLIP-2 before CLIP-3 (CLIP-3
depends on CLIP-2's detection gate).

### CLIP-3 · Motion-tracking crop for screen recordings

**Prerequisite: CLIP-2.** CLIP-3 is the no-face fallback within CLIP-2's `--face-track`
path. Cannot be built or used independently.

When `--face-track` is on and face detection returns no faces (screen shares, product
demos, coding streams), the current pipeline would center-crop. An optical-flow-based
crop would instead pan toward the area of activity (mouse cursor, typing, UI transitions).

**Approach:** Farneback optical flow (`cv2.calcOpticalFlowFarneback`, `opencv-python` is
a declared dep) computed once per second. Per-column flow magnitude summed → weighted
center of motion → smoothed pan position. Source scaled so its width is 1.5x the output
panel width (after the existing `scale` filter in the FFmpeg graph), giving 0.25x
panel-width of pan room in each direction.

**Where it lives:** Alongside CLIP-2 in `sable/clip/face_track.py`.

**Edge cases:**
- First frame: no prior frame for flow → default to center crop
- Static frames (no significant flow): hold current pan position, do not drift to center.
  Define a flow-magnitude threshold below which pan is frozen
- Full-screen transitions (page nav, app switch): flow spikes everywhere with no
  directional signal → treat as static, hold position

**Performance:** Farneback on 1080p ~50-100ms/frame on CPU. At 1fps for a 30s clip =
~1.5-3s overhead. Consider downscaling to 540p for flow computation.

**When to build:** When we start clipping screen-share or product demo content.

---

## Community Intelligence Features

Sourced from a multi-agent feature proposal competition (2026-04-01). See
`docs/AUDIT_HISTORY.md` § "Community Intelligence Feature Competition" for full
provenance (15 proposals, 5 agents, evaluation criteria, ranking, consolidation rationale).

### Build order

1. FEATURE-11 Part A (`--amplifiers`) — smallest scope, zero deps, highest impact
2. FEATURE-10 (`sable lexicon`) — high onboarding value, unblocks FEATURE-14
3. FEATURE-12 (`--voice-check`) — requires AUDIT-5 landed first
4. FEATURE-14 (`sable narrative`) — shares threshold patterns with FEATURE-10
5. FEATURE-15 (`sable style-delta`) — benefits from FEATURE-11 context
6. FEATURE-16 (`sable silence-gradient`) — unblocks CHURN-1
7. FEATURE-11 Part B (`--bridge-aware`) — requires CultGrader diagnostic data
8. FEATURE-13 (`--community-voice`) — requires cross-repo migration

### Documentation update checklist (per feature shipped)

After each feature lands, update these docs before merging:

- [ ] `docs/COMMANDS.md` — add new CLI commands/flags with examples
- [ ] `docs/ARCHITECTURE.md` — add new module to tree + subsystem diagram
- [ ] `docs/SCHEMA_INVENTORY.md` — add new tables/models/config keys
- [ ] `README.md` — add to Modules table
- [ ] `docs/CONFIG_REFERENCE.md` — add new config keys
- [ ] `docs/IMPLEMENTATION_LOG.md` — append dated implementation record
- [ ] `docs/AUDIT_HISTORY.md` — update validation history row
- [ ] `CLAUDE.md` — update if feature adds new DB tables, architectural patterns, or cross-module dependencies

---

### FEATURE-10 · Community Lexicon (`sable lexicon`)

**Problem:** `sable write` generates content with no awareness of community-specific
language. Operators catch voice mismatches manually. `topics.py` detects trending terms
but not community-exclusive vocabulary.

**What it does:**

1. `sable lexicon scan --org <org>` reads `meta.db.scanned_tweets` using existing
   `extract_terms()` / `extract_repeated_ngrams()` from `topics.py`. Applies an
   **exclusivity filter**: term must appear in ≥2 tweets AND ≤25% of watchlist authors
   (filters generic crypto language).
2. One optional batched Claude call (`call_type='lexicon_interpret'`) classifies top 25
   terms as `insider_slang | project_term | topic_reference | noise` with one-line glosses.
   `check_budget()` before the call. `--no-interpret` skips Claude entirely.
3. Computes **Lexical Spread Rate** per term:
   `LSR = (unique_authors / total_tracked_authors) * log2(1 + mention_count)`.
   LSR is a sort key for surfacing candidates, not a client-facing health metric.
4. Writes report to vault as `{vault_dir(org)}/lexicon_report.md`.

**CLI surface:**
```
sable lexicon scan --org <org> [--days 14] [--top 20] [--no-interpret] [--dry-run]
sable lexicon list --org <org>
sable lexicon add --org <org> --term "<term>" --gloss "<gloss>"
sable lexicon remove --org <org> <term>
```

`sable write` gains `--lexicon` flag (opt-in, v1). When set, loads lexicon report and
injects community vocabulary into the generation prompt. Auto-injection deferred to v2.

**Minimum-data thresholds (report refused below these):**
- ≥10 unique authors in corpus (`MIN_AUTHORS = 10`)
- ≥50 tracked tweets in scan window (`MIN_TWEETS = 50`)
- ≥3 appearances per term
- ≥2 unique authors per term

These constants are exported from `sable/lexicon/scanner.py` for reuse by FEATURE-14
(Narrative Velocity).

**Persistence:** `meta.db.lexicon_terms` table is the single source of truth. The vault
report (`lexicon_report.md`) is a rendered snapshot — read-only output, not an input.
`sable lexicon add/remove` writes to `meta.db`; `sable lexicon scan` regenerates the
vault report from `meta.db` state. `sable write --lexicon` reads from `meta.db`, not from
the vault file.

**`--dry-run` behavior:** Prints corpus stats (unique authors, tweet count, whether
minimum thresholds are met) and estimated Claude call count (0 or 1). Makes no API calls
and writes nothing.

**Where it lives:** `sable/lexicon/` — `scanner.py`, `cli.py`, `writer.py`. New
`lexicon_terms` table in `meta.db` (`_SCHEMA` string). Tests in `tests/lexicon/`.

**Cost:** One Claude call per scan (~$0.02 at Sonnet rates) or zero with `--no-interpret`.

**What is deferred from v1:**
- Dialect drift detection (requires subsquad identity data from CultGrader)
- Reply-based vocabulary sampling (requires SocialData reply endpoint validation — build
  gate: validate `GET /twitter/search?query=to:{handle}` before implementing)
- Vernacular lint pass on `sable write` (`--lint-vernacular` flag, deferred to v2)

**When to build:** After AUDIT remediation queue is clear. High value for new client
onboarding — lexicon is the first thing a new operator needs to understand about a
community.

#### Implementation plan

**Slice A — Data layer + scanner (no Claude):**
- New file `sable/lexicon/__init__.py`
- New file `sable/lexicon/scanner.py`:
  - `scan_lexicon(org, days, top_n, conn)` → reads `meta.db.scanned_tweets`, calls
    `extract_terms()` / `extract_repeated_ngrams()`, applies exclusivity filter
  - `compute_lsr(term_stats)` → Lexical Spread Rate computation
  - Minimum-data threshold checks (10 authors, 50 tweets, 3 appearances, 2 authors/term)
- Add `lexicon_terms` table to `meta.db` `_SCHEMA` string in `sable/pulse/meta/db.py`:
  `(org TEXT, term TEXT, category TEXT, gloss TEXT, lsr REAL, updated_at TEXT,
  UNIQUE(org, term))`
- New file `sable/lexicon/store.py`: `upsert_term()`, `list_terms()`, `remove_term()`,
  `add_manual_term()` — all operate on `meta.db.lexicon_terms`
- Tests: `tests/lexicon/test_scanner.py` — exclusivity filter, LSR math, threshold
  refusal, empty corpus

**Slice B — Claude interpretation + vault report:**
- New file `sable/lexicon/writer.py`:
  - `interpret_terms(terms, org_id, conn)` → single batched `call_claude_json()` with
    `call_type='lexicon_interpret'`, `check_budget()` before call
  - `render_report(terms, org, vault_path)` → write `lexicon_report.md` to vault via
    `atomic_write()`
- Tests: `tests/lexicon/test_writer.py` — mock Claude response parsed correctly,
  `--no-interpret` skips Claude call, report renders expected markdown, `--dry-run`
  makes no writes and no API calls

**Slice C — CLI + write integration:**
- New file `sable/lexicon/cli.py`: `scan`, `list`, `add`, `remove` subcommands
- Register `lexicon` group in `sable/cli.py`
- Modify `sable/commands/write.py`: add `--lexicon` flag, load from `meta.db` via
  `store.list_terms()`, inject into generation prompt
- Tests: `tests/lexicon/test_cli.py` — CLI smoke tests for each subcommand,
  `tests/write/test_write_lexicon.py` — `--lexicon` flag injects terms into prompt

**File change summary:**
| Action | File |
|--------|------|
| Create | `sable/lexicon/__init__.py`, `scanner.py`, `store.py`, `writer.py`, `cli.py` |
| Modify | `sable/pulse/meta/db.py` (`_SCHEMA` string — add `lexicon_terms` table) |
| Modify | `sable/cli.py` (register `lexicon` group) |
| Modify | `sable/commands/write.py` (add `--lexicon` flag) |
| Create | `tests/lexicon/test_scanner.py`, `test_writer.py`, `test_cli.py` |
| Create | `tests/write/test_write_lexicon.py` |

**Estimated tests:** 18–22

---

### FEATURE-11 · Watchlist Amplifiers + Bridge Node Signals

**Consolidates:** Operator PM `--amplifiers` (rank 1 overall) + Cross-repo PM Bridge Node
Amplification + Academic PM Bridge Score (phased prerequisite). Three proposals answering
"who matters in this community?" merged into a single feature with two deliverables and
one deferred phase.

#### Part A: `sable pulse watchlist --amplifiers`

**Problem:** Watchlist accounts are a flat list. Operators have no ranked view of who is
actually spreading content vs. passively consuming.

**What it does:** Pure signal math on existing `meta.db.scanned_tweets`. No Claude calls,
no new API calls.

**Three signals (computed over configurable window, default 30 days):**

1. **Retweet velocity (RT_v):** `sum(reposts) / days_active` where `days_active` = count
   of distinct calendar days the author posted.
2. **Reply-pull rate (RPR):** `sum(replies) / (likes + reposts + replies + quotes + bookmarks)`.
   Measures conversation-triggering relative to reach.
3. **Quote-tweet rate (QTR):** `sum(quotes) / total_tweets_in_window`. Highest-value
   amplification signal.

**Composite:** `amp_score = 0.40 * percentile(RT_v) + 0.35 * percentile(RPR) + 0.25 * percentile(QTR)`.
Percentiles within the org's watchlist. Weights configurable in
`~/.sable/config.yaml: pulse_meta.amplifier_weights`.

**Output:** Rich terminal table + `--json` flag for machine consumption. Function
`compute_amplifiers(org, window_days, conn)` in `sable/pulse/meta/amplifiers.py` is
importable by `sable advise` stage1 assembly.

**CLI:** `sable pulse watchlist --amplifiers --org <org> [--window-days 30] [--top 10] [--json]`

**Where it lives:** New `sable/pulse/meta/amplifiers.py`. CLI flag in
`sable/pulse/meta/cli.py`. No schema changes.

#### Part B: Bridge Node Activity in `sable advise`

**Problem:** CultGrader identifies bridge nodes and writes `bridge_node` tags to
`sable.db` via `platform_sync.py`. Slopper's `sable advise` ignores this data after
onboarding.

**What it does:** When `--bridge-aware` flag is passed to `sable advise`, queries
`sable.db` for `bridge_node` tagged entities, then queries `meta.db.scanned_tweets` for
their recent tweet performance (application-level join — no cross-DB SQL). Injects a
labeled prose section into the assembled input. Claude interprets the signal — no magic
multiplier on baselines.

**Key constraints:**
- `baselines.py` is NOT modified. Bridge node data is a separate advise section.
- Default off. Operator opts in per run with `--bridge-aware`.
- If org has zero bridge node tags, section is skipped entirely.
- Estimated token cost: ~56 tokens worst case (5 bridge nodes).

**Where it lives:** Helper in `sable/advise/stage1.py`, flag in `sable/commands/advise.py`.

#### Deferred: Bridge Score Graph (Phase 0 + Phase 1)

**Prerequisite for future graph analysis.** Not built until amplifiers + bridge node
section prove value with operators.

- **Phase 0:** Add `quoted_author_handle TEXT` column to `scanned_tweets` in `meta.db`
  `_SCHEMA` string. Update scanner to extract from SocialData `quoted_status.user.screen_name`.
  Schema version bump. Ships as standalone PR.
- **Phase 1:** Build directed quote-tweet graph, compute in-degree + betweenness centrality.
  `sable bridge-score --org <org>` ranked table. Requires networkx (justify before adding).
  Minimum edge threshold: <20 edges → empty result with `insufficient_data` flag.
- **Phase 2 (separate proposal):** Topic clustering overlay on the graph. Out of scope.

**When to build Part A:** First feature to build after AUDIT queue — smallest scope,
highest impact, zero new dependencies.

#### Implementation plan

**Slice A — Amplifier computation + output:**
- New file `sable/pulse/meta/amplifiers.py`:
  - `compute_amplifiers(org, window_days, conn)` → queries `scanned_tweets`, computes
    RT_v, RPR, QTR per author, percentile ranks, composite `amp_score`
  - Returns list of `AmplifierRow` dataclasses (author, rt_v, rpr, qtr, amp_score, rank)
- Tests: `tests/pulse/meta/test_amplifiers.py` — percentile math, zero-division guards,
  single-author edge case, window filtering, composite weight sum = 1.0

**Slice B — CLI integration:**
- Modify `sable/pulse/meta/cli.py`: add `--amplifiers` flag to `watchlist` command group
  with `--window-days`, `--top`, `--json` options
- Rich table output (rank, handle, amp_score, RT_v, RPR, QTR)
- Tests: `tests/pulse/meta/test_amplifiers_cli.py` — CLI smoke test, `--json` output
  format, `--top` truncation

**Slice C — Bridge node section in advise (Part B):**
- Modify `sable/advise/stage1.py`: add `_assemble_bridge_section(org, sable_db_conn,
  meta_db_conn)` — queries `sable.db` for `bridge_node` tagged entities, queries
  `meta.db.scanned_tweets` for their recent tweets, renders prose section
- Modify `sable/commands/advise.py`: add `--bridge-aware` flag, pass to `assemble_input()`
- Tests: `tests/advise/test_bridge_section.py` — section rendered when bridge nodes
  exist, section skipped when zero bridge nodes, section skipped when flag not passed

**File change summary:**
| Action | File |
|--------|------|
| Create | `sable/pulse/meta/amplifiers.py` |
| Modify | `sable/pulse/meta/cli.py` (add `--amplifiers` flag) |
| Modify | `sable/advise/stage1.py` (bridge section assembly) |
| Modify | `sable/commands/advise.py` (add `--bridge-aware` flag) |
| Create | `tests/pulse/meta/test_amplifiers.py`, `test_amplifiers_cli.py` |
| Create | `tests/advise/test_bridge_section.py` |

**Estimated tests:** 14–18

---

### FEATURE-12 · Voice Check (`sable write --voice-check`)

**Problem:** `sable write` generates variants but the existing `voice_fit` score in
`score_draft()` uses only 200 characters of `tone.md`. Operators catch voice drift
manually. The vault contains every post ever written for an account — an untapped voice
corpus.

**What it does:** Enhances the existing `score_draft()` function in `sable/write/scorer.py`
with an optional `voice_corpus: str | None` parameter. When `--voice-check` is active,
assembles a richer corpus from `tone.md` (full) + `notes.md` (full) + recent vault notes
filtered by `posted_by`, then passes it into the existing scorer. No parallel scoring path.

**Voice corpus caps (bound prompt cost):**
- Max 10 vault notes
- Max 500 tokens per note
- Max 4,000 tokens total corpus
- All configurable in `~/.sable/config.yaml: write.voice_check.*`

**Cost:** ~$0.07/run (3 variants) or ~$0.12 (5 variants) at Sonnet rates. `check_budget()`
called before scoring loop. `--voice-check` implies `--score`.

**Dependency:** Requires AUDIT-5 (org-scoped budget enforcement) to be landed first so
`check_budget()` actually gates spend when `org_id` is passed through the write path.

**Where it lives:** Modified `sable/write/scorer.py` (add `voice_corpus` param),
`sable/write/generator.py` (corpus assembly helper), `sable/commands/write.py` (flag).

**When to build:** After AUDIT-5 and FEATURE-10. Small scope, immediate daily value.

#### Implementation plan

**Slice A — Voice corpus assembly:**
- Modify `sable/write/generator.py`: add `assemble_voice_corpus(handle, org, vault_path,
  config)` — loads `tone.md` (full), `notes.md` (full), recent vault notes filtered by
  `posted_by` (up to 10, 500 tokens each, 4000 total cap)
- Configurable caps read from `config.get('write.voice_check.*')`
- Tests: `tests/write/test_voice_corpus.py` — corpus caps enforced, empty vault returns
  empty string, `posted_by` filter works, token truncation

**Slice B — Scorer integration:**
- Modify `sable/write/scorer.py`: add `voice_corpus: str | None = None` parameter to
  `score_draft()`, inject corpus into existing Claude scoring prompt when provided
- `check_budget()` called once before the variant scoring loop in `write.py` (not
  inside `score_draft()` itself) when `voice_corpus` is set
- Tests: `tests/write/test_scorer_voice.py` — voice corpus injected into prompt,
  `None` corpus uses existing behavior, budget check called

**Slice C — CLI flag:**
- Modify `sable/commands/write.py`: add `--voice-check` flag, implies `--score`,
  calls `assemble_voice_corpus()` and passes result to `score_draft()`
- Tests: `tests/commands/test_write_voice_flag.py` — flag wiring, `--voice-check`
  without `--score` still triggers scoring

**File change summary:**
| Action | File |
|--------|------|
| Modify | `sable/write/generator.py` (add `assemble_voice_corpus()`) |
| Modify | `sable/write/scorer.py` (add `voice_corpus` param) |
| Modify | `sable/commands/write.py` (add `--voice-check` flag) |
| Create | `tests/write/test_voice_corpus.py`, `test_scorer_voice.py` |
| Create | `tests/commands/test_write_voice_flag.py` |

**Estimated tests:** 10–14

---

### FEATURE-13 · Community Language Injection (`sable advise --community-voice`)

**Problem:** CultGrader produces `emergent_cultural_terms`, `mantra_candidates`, and
`language_arc_phase` per community. These fields are NOT currently in `sable.db` — they
live in CultGrader's `DiagnosticAnalysis` and are written to checkpoint JSON files. Slopper
has no access to them.

**Prerequisite (cross-repo):**

1. **SablePlatform migration (next sequential number after current):** Add
   `language_arc_phase TEXT`, `emergent_cultural_terms_json TEXT`,
   `mantra_candidates_json TEXT` to `diagnostic_runs`. Migration number depends on
   SablePlatform's current schema version at implementation time — check
   `sable_platform/db/migrations/` for the latest file and increment.
2. **CultGrader `platform_sync.py`:** Extend `_upsert_diagnostic_run()` INSERT/UPDATE
   to populate the three new columns from `DiagnosticAnalysis`.

**What it does (Slopper side):** `stage1.py::assemble_input()` queries `diagnostic_runs`
for the latest completed run with non-null language fields. Injects a `## Community
Language Signal` section into the advise assembled input.

**Key constraints:**
- 14-day freshness gate: if diagnostic data > 14 days old, log warning, inject nothing.
- Null guard at every layer: empty fields → skip injection entirely. No empty structured
  blocks reach Claude.
- Token cost: ~34-60 tokens worst case. Well under 500-token threshold.
- Scoped to `sable advise` only. Not wired into `sable write` in v1.

**Where it lives:** `sable/advise/stage1.py` (read + render). Cross-repo changes in
SablePlatform and CultGrader.

**When to build:** After a CultGrader diagnostic has run for at least one active client
(TIG Foundation). Prerequisite migration must land in SablePlatform first.

#### Implementation plan

**Slice A — Cross-repo prerequisites (SablePlatform + CultGrader):**
- SablePlatform: new migration file (next sequential number) adding three columns to
  `diagnostic_runs`: `language_arc_phase TEXT`, `emergent_cultural_terms_json TEXT`,
  `mantra_candidates_json TEXT`
- CultGrader: modify `platform_sync.py::_upsert_diagnostic_run()` to populate the three
  new columns from `DiagnosticAnalysis`
- Tests: migration test in SablePlatform, sync test in CultGrader

**Slice B — Slopper advise integration:**
- Modify `sable/advise/stage1.py`: add `_assemble_community_language(org_id, conn)` —
  queries `diagnostic_runs` for latest completed run with non-null language fields,
  applies 14-day freshness gate, renders `## Community Language Signal` section
- Null guard at every layer: empty fields → skip injection entirely
- Modify `sable/commands/advise.py`: add `--community-voice` flag
- Tests: `tests/advise/test_community_language.py` — fresh data injected, stale data
  (>14d) skipped with warning, null fields skipped, flag wiring

**File change summary (Slopper only):**
| Action | File |
|--------|------|
| Modify | `sable/advise/stage1.py` (add community language assembly) |
| Modify | `sable/commands/advise.py` (add `--community-voice` flag) |
| Create | `tests/advise/test_community_language.py` |

**Estimated tests (Slopper):** 6–8

---

### FEATURE-14 · Narrative Velocity (`sable narrative`)

**Problem:** `sable calendar` plans what to post. `sable pulse meta` measures what formats
work. Neither answers: "is our narrative arc actually landing with the community?"

**What it does:** Operator defines narrative beats as keyword lists in YAML. The tool
scores how fast those keywords spread through watchlist tweets. Zero Claude calls. Pure
deterministic scoring on existing `meta.db` data.

**Beat definition:** `~/.sable/{org}/narrative_beats.yaml`:
```yaml
beats:
  - id: zk_mainnet
    label: "zkEVM mainnet launch"
    keywords: ["zk mainnet", "zkEVM", "mainnet live"]
    start_date: "2026-03-01"
    target_days: 14
```

**Uptake Score per beat:**
- `uptake_score = unique_authors_mentioning / total_tracked_authors`
- `uptake_velocity = unique_authors_mentioning / days_since_start`

Keywords matched case-insensitively as substrings. Same minimum-data thresholds as
FEATURE-10 (10 authors, 50 tweets).

**CLI:**
```
sable narrative score --org <org> [--beats <path>] [--days 14] [--output <path>]
sable narrative beats edit --org <org>   # opens in $EDITOR
```

**Where it lives:** `sable/narrative/` — `tracker.py`, `cli.py`, `models.py`. Imports
`extract_terms()` from `topics.py`. Tests in `tests/narrative/`.

**Cost:** Zero. No Claude calls, no API calls.

**When to build:** After FEATURE-10 (shares minimum-data threshold patterns). Good
candidate for a new client onboarding where the operator has a clear narrative strategy.

#### Implementation plan

**Slice A — Beat parser + uptake scoring:**
- New file `sable/narrative/__init__.py`
- New file `sable/narrative/models.py`: `NarrativeBeat` and `UptakeResult` dataclasses
- New file `sable/narrative/tracker.py`:
  - `load_beats(org)` → parse `~/.sable/{org}/narrative_beats.yaml`, validate schema
  - `score_uptake(beat, org, days, conn)` → query `meta.db.scanned_tweets`, case-insensitive
    substring match on keywords, compute `uptake_score` and `uptake_velocity`
  - Imports minimum-data threshold constants from `sable/lexicon/scanner.py`
    (`MIN_AUTHORS`, `MIN_TWEETS`) — FEATURE-10 must export these
- Tests: `tests/narrative/test_tracker.py` — uptake math, keyword matching, threshold
  refusal, empty beats file, malformed YAML

**Slice B — CLI + report:**
- New file `sable/narrative/cli.py`: `score` and `beats edit` subcommands
- Register `narrative` group in `sable/cli.py`
- `--output <path>` writes JSON report
- `beats edit` opens `$EDITOR` on the beats YAML file
- Tests: `tests/narrative/test_cli.py` — CLI smoke tests, output file written, missing
  beats file error

**File change summary:**
| Action | File |
|--------|------|
| Create | `sable/narrative/__init__.py`, `models.py`, `tracker.py`, `cli.py` |
| Modify | `sable/cli.py` (register `narrative` group) |
| Create | `tests/narrative/test_tracker.py`, `test_cli.py` |

**Estimated tests:** 10–14

---

### FEATURE-15 · Style Delta (`sable style-delta`)

**Problem:** Operators know what formats perform well (from pulse meta) but not how their
managed account's structural posting style differs from top performers in the niche. No
quantitative gap analysis exists.

**What it does:** Computes a linguistic fingerprint for the managed account (from
`pulse.db.posts`) and the top-quintile watchlist accounts (from `meta.db.scanned_tweets`).
Surfaces the gap as a structured report.

**Fingerprint features (managed side, from `pulse.db.posts`):**
- Format distribution (by `sable_content_type` → share of post count)
- Sample size

`pulse.db.posts` does not store thread length, media presence, or link presence. These
fields exist only in `meta.db.scanned_tweets`. If the managed account is also on its own
watchlist (common for active clients), the watchlist-side fingerprint includes the richer
feature set below. If not, the delta report is limited to format distribution only and
must state this limitation explicitly.

**Fingerprint features (watchlist side, from `meta.db.scanned_tweets`):**
- Format distribution (coarse-mapped from `format_bucket`)
- Median thread length
- Media rate (share of posts with images/video)
- Link rate
- Sample size

**Schema note:** `pulse.db.posts` uses `sable_content_type` (coarse: clip/meme/faceswap/
text/unknown), not `format_bucket`. `meta.db.scanned_tweets` uses the finer-grained
`format_bucket` from `normalize.py`. To make the comparison meaningful, **both sides must
use the same taxonomy.** Use `sable_content_type`-level coarse types for both: map
`scanned_tweets.format_bucket` values back to coarse categories via an explicit mapping
function (e.g. `standalone_text|thread|quote_commentary → text`, `short_clip|long_video →
clip`). The delta is only useful when comparing equivalent categories.

**Top-quintile definition:** Rank all `scanned_tweets` for the org by `total_lift` DESC,
take top 20% via `NTILE(5)`. Compute distributions across that filtered set. This is a
**filtered mean**, not a cluster centroid.

**Delta computation:** `format_gap[bucket] = watchlist_share - managed_share` per format
bucket. Positive gap = watchlist over-indexes on that bucket relative to managed account.

**Minimum sample guard:** If either side has <10 posts, refuse to render report.

**CLI:** `sable style-delta --handle <handle> --org <org> [--output <path>]`

**Where it lives:** `sable/style/` — `fingerprint.py`, `delta.py`, `cli.py`, `report.py`.
Tests in `tests/style/`.

**Cost:** Zero. No Claude calls, no API calls. Recomputed on every invocation (no cache
in v1).

**When to build:** After FEATURE-11 (both read from same meta.db data; style-delta
benefits from amplifier context). Useful as a cold-start diagnostic when onboarding a new
account.

#### Implementation plan

**Slice A — Fingerprint computation:**
- New file `sable/style/__init__.py`
- New file `sable/style/fingerprint.py`:
  - `fingerprint_managed(handle, pulse_conn, meta_conn=None)` → query `pulse.db.posts`
    for format distribution (by `sable_content_type`) + sample size. If `meta_conn` is
    provided and handle exists in `meta.db.scanned_tweets`, also compute thread length,
    media rate, link rate from watchlist data (richer fingerprint).
  - `fingerprint_watchlist(org, meta_conn)` → query `meta.db.scanned_tweets`, filter top
    quintile by `total_lift` DESC via `NTILE(5)`, compute full feature set
  - `_coarse_bucket(format_bucket)` → mapping function from fine-grained `format_bucket`
    to coarse `sable_content_type`-level categories
  - When managed account is not in watchlist, delta report limited to format distribution
    only — report states this limitation explicitly
- Tests: `tests/style/test_fingerprint.py` — coarse mapping correctness, top-quintile
  filtering, minimum sample guard (<10 → refuse), managed-only-in-pulse degrades to
  format-distribution-only, managed-in-both-dbs gets full fingerprint

**Slice B — Delta computation + report:**
- New file `sable/style/delta.py`:
  - `compute_delta(managed_fp, watchlist_fp)` → per-bucket `format_gap` computation
- New file `sable/style/report.py`:
  - `render_delta_report(delta, managed_fp, watchlist_fp)` → Rich table or markdown
- Tests: `tests/style/test_delta.py` — gap math, symmetric edge cases (identical
  distributions → zero gap)

**Slice C — CLI:**
- New file `sable/style/cli.py`: `style-delta` command with `--handle`, `--org`,
  `--output` options
- Register in `sable/cli.py`
- Tests: `tests/style/test_cli.py` — CLI smoke test, `--output` writes file

**File change summary:**
| Action | File |
|--------|------|
| Create | `sable/style/__init__.py`, `fingerprint.py`, `delta.py`, `report.py`, `cli.py` |
| Modify | `sable/cli.py` (register `style-delta` command) |
| Create | `tests/style/test_fingerprint.py`, `test_delta.py`, `test_cli.py` |

**Estimated tests:** 12–16

---

### FEATURE-16 · Silence Gradient (`sable silence-gradient`)

**Problem:** Community decay is currently only detectable after it happens. CHURN-1/CHURN-2
(below) depend on Platform shipping a decay alerting pipeline. Silence Gradient detects
pre-decay signals from data already in `meta.db`, unblocking churn intervention without
waiting for Platform.

**What it does:** Per-watchlist-author rolling 30-day cadence analysis. Three signals:

1. **Volume drop (0.4 weight):**
   `vol_drop = 1.0 - (posts_recent_half / max(posts_prior_half, 1))`, clamped [0, 1].
2. **Engagement drop (0.35 weight):**
   `eng_drop = 1.0 - (median_lift_recent / max(median_lift_prior, 0.001))`, clamped [0, 1].
   Requires ≥5 rows per window half.
3. **Format regression (0.25 weight):**
   Shannon entropy of `format_bucket` distribution, normalized to [0, 1], inverted.
   `fmt_reg = 1.0 - (entropy / log2(len(FORMAT_BUCKETS)))`. Requires ≥5 posts.

**Combination:** Weighted sum with proportional redistribution when a signal is
`insufficient_data`. All weights are module-level constants.

**Minimum sample thresholds (non-negotiable for Tier 1 compliance):**
- Author has <5 posts total → excluded entirely
- Per-signal thresholds: <5 rows in either window half → signal marked `insufficient_data`
- All three signals insufficient → author excluded from ranked output

**Window semantics:** `--window 30` means "look back 30 days total." The algorithm splits
this into two equal halves: last 15 days vs prior 15 days. Custom windows follow the same
split: `--window 14` = 7d vs 7d. Odd values are rejected with a clear error message
("window must be even"). Minimum accepted window: 6 (3d vs 3d) to keep the per-half
sample useful.

**New table in `meta.db`:** `author_cadence` — one row per `(author_handle, org, computed_at)`.
Columns: `posts_recent_half`, `posts_prior_half`, `median_lift_recent`, `median_lift_prior`,
`format_entropy`, `vol_drop`, `eng_drop`, `fmt_reg`, `silence_gradient`, `insufficient_data`,
`window_days` (records the actual window used so column names stay generic).

**Retention:** Only the latest `computed_at` per `(author_handle, org)` is kept. Each
write uses `INSERT OR REPLACE` on the unique index `(author_handle, org)` — no historical
accumulation. If historical trends are needed later, add a separate time-series table.

**CLI:**
```
sable silence-gradient --org <org> [--top 20] [--window 30] [--output <path>]
sable silence-gradient --org <org> --include-insufficient  # show suppressed rows
```

**Relationship to CHURN:** Silence Gradient produces a `silence_gradient` score (not a
"decay score"). It is derived entirely from `meta.db` watchlist data, not Platform's
member engagement model. It can serve as an **alternative upstream data source** for
CHURN-1 when Platform's decay alerting pipeline is not yet available.

**Where it lives:** `sable/cadence/` — `signals.py`, `combine.py`, `store.py`, `cli.py`.
Tests in `tests/cadence/`.

**Cost:** Zero. No Claude calls, no API calls.

**When to build:** After FEATURE-11 (uses same meta.db data patterns). Unblocks CHURN-1
work without cross-repo dependency.

#### Implementation plan

**Slice A — Signal computation:**
- New file `sable/cadence/__init__.py`
- New file `sable/cadence/signals.py`:
  - `compute_volume_drop(posts_recent, posts_prior)` → clamped [0, 1]
  - `compute_engagement_drop(median_lift_recent, median_lift_prior)` → clamped [0, 1],
    requires ≥5 rows per half
  - `compute_format_regression(format_counts)` → Shannon entropy, normalized, inverted
  - Each function returns `(score, insufficient_data: bool)`
- Tests: `tests/cadence/test_signals.py` — math correctness, clamping bounds, insufficient
  data thresholds, zero-division guards

**Slice B — Combination + storage:**
- New file `sable/cadence/combine.py`:
  - `combine_signals(vol_drop, eng_drop, fmt_reg)` → weighted sum with proportional
    redistribution when a signal is `insufficient_data`
  - `compute_silence_gradient(org, window_days, conn)` → orchestrator querying
    `meta.db.scanned_tweets`, splitting window, computing per-author signals, combining
- New file `sable/cadence/store.py`:
  - `upsert_cadence(rows, conn)` → `INSERT OR REPLACE` into `author_cadence`
  - Add `author_cadence` table to `meta.db` `_SCHEMA` string in `sable/pulse/meta/db.py`
- Tests: `tests/cadence/test_combine.py` — weight redistribution, all-insufficient
  exclusion, window split math (even/odd/minimum), per-author orchestration
- Tests: `tests/cadence/test_store.py` — INSERT OR REPLACE retention policy

**Slice C — CLI:**
- New file `sable/cadence/cli.py`: `silence-gradient` command with `--org`, `--top`,
  `--window`, `--output`, `--include-insufficient` options
- Register in `sable/cli.py`
- Tests: `tests/cadence/test_cli.py` — CLI smoke test, `--include-insufficient` shows
  suppressed rows, `--output` writes file

**File change summary:**
| Action | File |
|--------|------|
| Create | `sable/cadence/__init__.py`, `signals.py`, `combine.py`, `store.py`, `cli.py` |
| Modify | `sable/pulse/meta/db.py` (`_SCHEMA` string — add `author_cadence` table) |
| Modify | `sable/cli.py` (register `silence-gradient` command) |
| Create | `tests/cadence/test_signals.py`, `test_combine.py`, `test_store.py`, `test_cli.py` |

**Estimated tests:** 16–20

---

## Churn Prediction Intervention Engine (Slopper Side)

**Dependency (updated):** Primary input path: Platform decay alerting pipeline (computes
who is at risk). Alternative input path: FEATURE-16 Silence Gradient (`sable silence-gradient
--org <org> --output at-risk.json`) can produce a compatible at-risk list from `meta.db`
data, unblocking CHURN-1 before Platform ships decay alerting. Slopper still does not own
decay scoring as a platform concept — Silence Gradient is a Slopper-internal early warning
signal that happens to produce a compatible input format.

### CHURN-1 · Intervention playbook generation

Given a list of at-risk members (delivered from Platform's decay alert pipeline), generate
a targeted re-engagement playbook per member or per cohort. Each playbook entry maps a
member to concrete actions the community manager can take immediately.

**Output per at-risk member:**
- Interest-matched content tags: "Tag @member in upcoming thread about [topic]" derived
  from the member's historical engagement topics (passed in from Platform/Cult Grader data)
- Role assignment recommendations: "Assign @member the [role] role" when participation
  history suggests they respond to ownership/status signals
- Contribution spotlight: "Create content featuring @member's contributions" when the
  member has notable past activity worth amplifying
- Direct engagement prompts: specific reply/quote-tweet suggestions referencing the
  member's past interactions

**Where it lives:** New module `sable/churn/` with `__init__.py`, `interventions.py`
(core logic), `cli.py` (command registration), tests in `tests/churn/`. Claude prompt
templates in `sable/churn/prompts.py` following existing `call_claude_json()` patterns.

**CLI surface:**
- `sable churn intervene --org <org> --input <at-risk-members.json>` — generate
  intervention playbook from Platform's at-risk export
- `sable churn intervene --org <org> --input <at-risk-members.json> --format calendar` —
  output as calendar-ready items instead of standalone playbook
- `sable churn intervene --org <org> --input <at-risk-members.json> --dry-run` —
  estimate Claude call count and cost without generating (matches `advise` and
  `playbook discord` convention)
- Input format: JSON array of `{handle, decay_score, topics, last_active, role, notes}`
  as defined by Platform's export contract

**Why `--org` instead of a handle argument:** Churn intervention operates on community
members across the org, not on a specific managed Twitter handle. There is no single
account to scope to — the at-risk list spans the org's community.

**Generation cost model:** One Claude call per at-risk member (each member gets a
personalized playbook entry with their topics and history injected). Not batched — each
call needs full member context for quality. Soft cap: if the at-risk list exceeds 50
members, emit a warning with estimated cost and require `--force` to proceed. `--dry-run`
prints the member count, estimated calls, and approximate spend without making any calls.

**Integration with existing commands:**
- `sable advise` gains `--churn-input <path>` flag to fold at-risk member re-engagement
  into its existing multi-stage recommendation flow
- `sable playbook discord` gains `--churn-input <path>` flag to include churn intervention
  tactics in Discord engagement playbooks (delegates scoring context to Cult Grader,
  actions to Slopper)

**Claude call pattern:** Org-scoped (`org_id` + `call_type='churn_intervention'`) so
spend is observable and budget-gated. Profile markdown for the org's account is injected
for tone/voice consistency.

### CHURN-2 · Calendar integration for at-risk re-engagement

Extend `sable calendar` to accept churn intervention data and prioritize content that
re-engages at-risk members within the generated posting schedule.

**Approach:** When `--churn-input` is passed to `sable calendar`, the calendar planner
receives the intervention playbook (from CHURN-1) alongside normal pulse/format data.
Calendar slots are annotated with re-engagement intent: which at-risk members each post
aims to pull back, and what engagement action accompanies the post (tag, reply,
spotlight).

**Where it lives:** Changes to existing `sable/calendar/` module. No new module needed.
Intervention context injected into the calendar prompt as a structured section.

**Constraints:**
- Re-engagement content should not dominate the calendar — cap at ~30% of slots unless
  the operator passes `--prioritize-churn` to remove the cap
- Calendar output includes a `churn_targets` field per slot (list of handles) so the
  operator knows which posts serve retention goals
- Falls back gracefully to normal calendar generation when no churn input is provided

**Edge cases:**
- Empty at-risk list → no churn annotations, calendar unchanged
- At-risk member has no identifiable interest topics → generic engagement recommendation
  (role offer, DM prompt) rather than content-specific tag
- Overlapping members across multiple churn runs → deduplicate by handle, use most
  recent decay data
- Org has no profile set up → warn and skip tone injection, proceed with generic output

**When to build:** After CHURN-1 ships. CHURN-2 consumes CHURN-1's playbook output.
CHURN-1 can be fed by either Platform's decay alerting export or FEATURE-16 Silence
Gradient output — CHURN-2 inherits whichever input path CHURN-1 uses.

---

## Phase 2+ (Deferred)

### Phase 2 — Web UI (`sable serve`)

- FastAPI app in `sable/serve/app.py`
- Cloudflare Tunnel for team/client access
- Role-based access control via `sable/vault/permissions.py` (currently stub)
- Token auth middleware + `~/.sable/vault_users.yaml`
- Web views: dashboard, content browser, search, reply suggest, posting log
- See `docs/ROLES.md` for permission matrix, `docs/ROADMAP.md` for architecture

### Phase 3 — VPS

- Docker + systemd, Postgres backend, multi-org S3 vault storage
- Webhook receivers for pulse data push + tweet notifications
- Scheduled sync via cron

### Phase 4 — Scale

- Multi-tenant auth, vault-as-API, real-time enrichment queue (Celery/Redis)
- Automated gap-fill suggestions triggered by pulse performance data
- Client portal with read-only dashboard + export access

---

## Convention Notes for Future Feature Work

### Command registration

- Top-level commands in `sable/cli.py`; nested subcommands in owning group file
- Handle-scoped commands call `require_account()` first; default `--org` from roster
- `build_account_context()` takes an `Account` object, not a bare handle string

### DB schema awareness

- `pulse.db` uses `posts.id` and `snapshots.id` (not `post_id`/`snapshot_id`)
- `posts.sable_content_type` is a coarse hint, not a format taxonomy — map to
  pulse-meta format buckets explicitly
- `meta.db.format_baselines` stores baseline aggregates only (no `current_lift`,
  `status`, `momentum`, `confidence_grade`)
- `load_all_notes()` returns frontmatter dicts with `_note_path`; scans
  `vault/content/**/*.md` only
- Vault note lifecycle: `posted_by` and `suggested_for` — no `status='posted'` field
- Content note freshness: `assembled_at` (no `created_at` on synced content notes)
- Config access: `sable.config.get(...)` / `require_key(...)` (no `get_config()`)
- `search_vault(query, vault_path, org, filters=SearchFilters(...), config=...)`

### Shared patterns

- Claude calls via `call_claude()` / `call_claude_json()` from `sable/shared/api.py`
- Org-scoped calls pass `org_id` + `call_type`; non-org sites annotated `# budget-exempt`
- File writes via `atomic_write()` from `sable/shared/files.py`
- All `except Exception` blocks must `logger.warning(...)` — no silent swallows
- New modules follow: `__init__.py`, main logic file, CLI command, tests in `tests/{module}/`
- `meta.db` table definitions go in `sable/pulse/meta/db.py`'s `_SCHEMA` string (not
  migration files), even when a different module owns the read/write logic. The owning
  module imports `meta_db_path()` and connects directly.

### Validation checklist

```bash
./.venv/bin/python -m pytest -q
./.venv/bin/ruff check .
./.venv/bin/mypy sable
```
