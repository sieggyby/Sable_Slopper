# THREAT_MODEL.md

## Purpose
This document gives Codex an adversarial lens tuned to how Sable tools actually fail.
Use it to prioritize what to test and what to harden.

> Edit the Repo-specific threats section per repo.

---

## Common threat categories for Sable tools

### 1. External API failure
What happens: an upstream API errors, times out, rate-limits, or changes shape.

What to test:
- 429 rate limits
- 500s and timeouts
- empty or malformed bodies
- pagination returning fewer results than expected

What to check:
- retries are bounded
- retryable vs non-retryable errors are distinguished
- parsing validates before downstream use

### 2. Cost overrun
What happens: a loop, missing cache, or inflated LLM prompt blows the runtime or monthly budget.

What to test:
- 10x normal input size
- cache disabled or cold-cache behavior

What to check:
- API calls inside loops are bounded
- cache checks happen before fetches
- paginated fetches are capped
- prompts are not duplicated per item unnecessarily

### 3. Credential exposure
What happens: keys or tokens leak to logs, reports, tracebacks, stdout/stderr, or committed files.

What to test:
- failing API calls
- verbose/debug output
- generated report output

What to check:
- secrets come from env or gitignored files
- `.env` is gitignored
- tracebacks and request logging do not leak auth material

### 4. Pipeline partial failure
What happens: an early stage writes state and a later stage fails, leaving stale or misleading intermediate output.

What to test:
- force failure at each stage
- rerun after mid-pipeline failure
- stale cache or partial output reuse

What to check:
- intermediate writes are atomic where practical
- cleanup or incomplete markers exist
- resume behavior is explicit

### 5. Schema drift
What happens: upstream API response shapes or internal markdown frontmatter structures change and downstream code silently assumes the old shape.

What to test:
- missing expected fields
- extra unexpected fields
- renamed or retyped frontmatter keys

What to check:
- validation exists at stage boundaries
- frontmatter fields are accessed by key, not position
- API response parsing validates expected fields before use

### 6. Empty and degenerate inputs
What happens: a project has little or no activity, missing governance, one user, or no social data.

What to test:
- zero-result datasets
- single-item datasets
- nonexistent external identifiers

What to check:
- divide-by-zero and empty-list cases are handled
- reports represent no-data states explicitly
- templates do not break when sections are missing

### 7. Output trustworthiness failure
What happens: the tool produces confident but misleading client-facing scores, summaries, or rankings because upstream data is sparse, malformed, stale, truncated, or partially failed.

What to test:
- tiny sample sizes
- stale intermediate data after failed runs
- token/context overflow or truncation in LLM steps
- summaries or scores generated from incomplete source coverage

What to check:
- uncertainty or missing coverage is surfaced
- thin data is not presented as strong signal
- failed or partial inputs do not masquerade as complete outputs

---

## Repo-specific threats
### 1. Media pipeline partial writes
What happens: clip assembly, caption rendering, vault sync, or export writes some outputs before a later step fails, leaving the library or vault in a misleading state.

What to test:
- ffmpeg failure mid-render
- interrupted export or sync runs
- rerun after a partially written clip or note

What to check:
- outputs are written atomically where practical
- reruns can detect and replace incomplete artifacts
- indexes and metadata do not point at missing files

### 2. Token and cost blowups in content generation loops
What happens: per-window Claude calls, repeated transcriptions, or Replicate requests fan out across many assets and create runaway cost or latency.

What to test:
- long videos with many candidate windows
- repeated retries after malformed LLM output
- batch meme or clip generation on cold caches

What to check:
- expensive calls are bounded and cached
- token budgets scale intentionally with input size
- retries do not duplicate already completed work

### 3. Shared-state drift across subcommands
What happens: roster profiles, pulse data, vault notes, and generated assets evolve independently and a later command reads stale or incompatible local state.

What to test:
- profile schema changes
- vault sync after metadata format changes
- pulse or assignment commands reading older note formats

What to check:
- shared file formats are validated at boundaries
- migrations or compatibility shims are explicit
- one command cannot silently poison another command's state

### 4. Unsafe or misleading generated content
What happens: captions, face swaps, account suggestions, or exported notes contain policy-sensitive content, bad attribution, or low-confidence output presented as ready to publish.

What to test:
- empty or low-quality transcript inputs
- mismatched account profiles
- face-swap or character explainer runs on unsupported assets

What to check:
- safety gates run before publish-ready output is emitted
- missing source quality is surfaced to the operator
- generated copy is not presented as approved fact when the source is thin

### 5. Web UI permission regressions
What happens: as `sable serve` grows, routes bypass role checks and expose vault data or export actions across org boundaries.

What to test:
- creator/operator access to admin-only routes
- org-scoped export and search paths
- token handling and session reuse

What to check:
- authorization happens server-side on every route
- role scope is enforced consistently with `docs/ROLES.md`
- CLI admin assumptions do not leak into web handlers
