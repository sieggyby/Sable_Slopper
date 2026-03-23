# AGENTS.md

## Purpose
Use Codex in this repo primarily as a skeptical maintainer and QA layer for Claude Code output.

## Default stance
Assume the code may work while still hiding structural problems.
Prioritize finding production, cost, and maintainability risks before proposing broad implementation changes.

When you find issues: flag the risk, then fix what you can in a single scoped patch.
If a safe fix is too large, leave a `TODO(codex)` with a one-line explanation.
If no issues are found at a given priority tier, say so and move on. Do not invent findings.

---

## Repo domain context

This repo is Sable's content production toolkit for crypto social accounts, spanning media generation, account context, performance tracking, and vault operations.

| Trait | Repo-specific assumption |
|---|---|
| External dependencies | Anthropic, Replicate, ffmpeg/media tooling, faster-whisper, local file storage, optional social/performance APIs |
| Architecture | CLI package with multiple subcommands sharing account profiles, media assets, and local vault/state directories. Now also has a shared `sable.db` platform store (entities, jobs, cost events) written via `sable/platform/`. |
| Reliability risk | File-path mistakes, expensive media reprocessing, and partial writes to local asset libraries are more common than complete crashes |
| Auth surface | API keys for Anthropic, Replicate, SocialData, and any future server auth tokens |
| Output formats | Generated clips, memes, captions, markdown vault notes, exports, and local analytics data |
| Deployment | Mostly local CLI today, with an emerging local web UI and future multi-tenant server path |
| Cost sensitivity | Video generation, transcription, and LLM-assisted selection can become expensive in both API spend and machine time if loops or retries expand |

### Repo-specific cost targets
- Soft warning threshold: **$3/run**
- Typical monthly ceiling: **$200/month**

Use this context to sharpen prioritization. Prefer repo-specific risk calls over generic advice.

---

## Core rules
- Prefer small, reviewable patches over rewrites.
- Do not add dependencies unless clearly justified.
- Do not silently change API, schema, or persistence contracts.
- For bug fixes, reproduce with a failing test first when practical.
- Preserve current behavior unless the task explicitly requests behavior change.
- Prefer deletion over addition when the same outcome can be achieved safely.
- Avoid refactoring untouched modules unless directly required for a safe fix.
- Run the most relevant validation commands after making changes.

---

## Review priorities

### Tier 1 — breaks prod, leaks secrets, or burns money
- credential or secret exposure
- unbounded API calls or missing rate-limit handling
- partial pipeline failure with stale or corrupt state
- silent data corruption or silent data loss
- confident but misleading client-facing output from sparse or failed upstream data

### Tier 2 — breaks maintainers
- hidden coupling between pipeline stages
- duplicated business logic
- unclear ownership boundaries
- schema drift between producers and consumers
- weak or leaky abstractions
- Platform writes that bypass `check_budget()` or skip `SableError` catch in CLI handlers

### Tier 3 — slows future work
- missing edge-case handling
- test gaps on critical paths
- accidental complexity
- misleading naming or comments

---

## Standard review output
When asked to review a branch, PR, diff, or new codebase, output in this order:

1. Critical risks
2. Cost/resource risks
3. Maintainability risks
4. Minimal corrective plan
5. Exact tests to add

If no issues exist at a given level, state that and move on.

---

## Security baseline
- Secrets load from environment variables or a `.env` file.
- `.env` must be gitignored.
- Secrets must not appear in logs, CLI output, reports, error messages, or committed code.
- Generated files must not interpolate credentials.
- Service account JSON files must not be committed.

---

## Cost guardrails
- Flag any API call inside an unbounded loop.
- Flag missing caching when source data is reused within or across runs.
- Flag redundant refetches across pipeline stages.
- Flag duplicated or inflated LLM prompts.
- Estimate per-run API cost for new tools using the repo-specific cost targets above.
- `sable/platform/cost.py` logs AI spend per org; `check_budget()` raises `SableError(BUDGET_EXCEEDED)` at cap. New code that calls Claude for a platform job should call `check_budget()` before the API call.
- Platform cost cap defaults: $5.00/org/week (configurable in `platform.cost_caps.max_ai_usd_per_org_per_week`).

---

## Additional guidance
See `docs/QA_WORKFLOW.md` for the default hardening workflow.
See `docs/PROMPTS.md` for default, periodic, and situational prompts.
See `docs/THREAT_MODEL.md` for the adversarial testing lens.
