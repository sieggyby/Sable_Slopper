# PROMPTS.md

Use these prompts by frequency. Do not run everything by default.

---

## Default prompts
Use these in normal day-to-day review loops.
For new tools with no prior branch, use the **greenfield structural audit** in place of the maintainer review.

### 1) Instruction sanity check
```text
Read `AGENTS.md`, `docs/QA_WORKFLOW.md`, `docs/PROMPTS.md`, and `docs/THREAT_MODEL.md`.
Summarize the instructions you will follow in this repo before doing any work.
Keep it brief. Include: review priorities, repo context, and security baseline.
```

### 2) Maintainer review
```text
Review the current branch as the maintainer responsible for reliability and future change velocity.
Use `docs/THREAT_MODEL.md` to inform your risk assessment for this repo.

Focus on:
- hidden coupling
- duplicated business logic
- weak abstractions
- unclear ownership boundaries
- schema drift
- test gaps
- cost/resource risks
- output trustworthiness (if the tool produces client-facing scores, summaries, or reports)

Do not rewrite yet.

Output only:
1. critical risks
2. cost/resource risks
3. maintainability risks
4. minimal corrective plan
5. exact tests to add

If no issues exist at a given level, say so and move on.
```

### 3) Greenfield structural audit
> Use instead of maintainer review when Claude Code has built a new tool from scratch.

```text
This is a new tool or an early codebase with no stable baseline yet.
Review it for structural risks before feature accretion makes them expensive.
Use `docs/THREAT_MODEL.md` to inform your risk assessment.

Focus on:
- pipeline boundaries and data contracts between stages
- caching opportunities
- secret handling
- rate-limit and retry strategy
- where partial failure could leave stale state
- where client-facing outputs could become untrustworthy due to thin or malformed upstream data

Output only:
1. critical structural risks
2. cost/resource risks
3. maintainability risks
4. minimal corrective plan
5. exact tests to add now

If no issues exist at a given level, say so and move on.
```

### 4) Add failing tests first
```text
Based on the current branch, add failing tests for the most important edge cases
and contract assumptions introduced by these changes.

Prioritize tests for:
- malformed or empty API responses from external services
- partial pipeline failures (stage N succeeds, stage N+1 fails)
- missing or invalid environment variables / credentials
- rate limit or timeout responses from upstream APIs
- boundary inputs (empty datasets, single item, max expected size)
- output trustworthiness (scores or summaries from sparse or incomplete data)

Use mocks for external API calls. Do not make real network requests in tests.
Prefer small, high-signal tests. Each test should have a clear name describing what breaks.
```

### 5) Smallest safe patch
```text
Implement the smallest safe patch set needed to make those tests pass.
Avoid broad rewrites. Preserve existing contracts unless a critical flaw requires a minimal structural fix.

If a fix touches API call patterns, verify:
- rate limit handling still works
- caching is preserved
- error responses are caught before downstream stages consume them
```

### 6) Cleanup pass
```text
Reduce duplication and improve clarity in touched files only.
Prefer deletion over addition. Do not change behavior.
Remove dead code. Verify no secrets in added log or print statements.
```

---

## Periodic prompts
Use weekly or after major changes, not on every branch.

### 7) Cost/resource audit
```text
Audit this repo for cost and resource risks.

Focus on:
- API calls inside loops
- missing caching
- duplicated fetches across stages
- unbounded pagination
- inflated or duplicated LLM prompts
- unnecessary repeated file or sheet writes

First list the highest-risk cost issues. Then propose the smallest fixes.
Patch only after presenting the list.
```

### 8) Security/secrets audit
```text
Audit this repo for credential exposure and unsafe secret handling.

Check for:
- hardcoded secrets
- missing `.env` ignore rules
- secrets leaking to logs, stdout/stderr, reports, or committed files
- unsafe traceback or request logging
- service account JSON handling

First enumerate all violations and likely exposures. Then propose one scoped patch plan.
Do not patch before listing findings.
```

### 9) Resilience audit
```text
Audit this tool for resilience against API failures, rate limits, malformed responses,
empty inputs, and mid-pipeline failure.

Use `docs/THREAT_MODEL.md`.
List the most important failure modes first, then propose the smallest hardening steps.
```

---

## Situational prompts
Use only when relevant.

### 10) Data contract audit
```text
Check for schema mismatches, brittle parsing, implicit payload assumptions,
sheet-layout assumptions, and migration risk.
Add tests first where practical.
```

### 11) Output trustworthiness audit
```text
Audit this tool's client-facing outputs for trustworthiness risk.

Focus on cases where the tool could produce confident but misleading scores, summaries,
rankings, or reports because upstream data is sparse, malformed, stale, truncated, or partially failed.

Check for:
- missing-data states presented as real signals
- fragile scoring on tiny sample sizes
- silent truncation or token/context overflow
- stale intermediate data reused after failed runs
- reports that do not disclose uncertainty or missing coverage

First list the trustworthiness risks. Then propose the smallest safe fixes and exact tests.
```
