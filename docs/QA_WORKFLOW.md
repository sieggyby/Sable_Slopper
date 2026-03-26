# QA_WORKFLOW.md

## Goal
Harden Claude Code output without broad rewrites and without letting the repo drift into brittle structure.

## Default workflow

### 1. Review before rewriting
Start by reviewing the current branch, diff, or touched files.
Identify:
- critical risks
- cost/resource risks
- maintainability risks
- test gaps
- contract assumptions
- hidden coupling

Do not start with a rewrite.

For **new tools built from scratch**, use the **greenfield structural audit** prompt
from `docs/PROMPTS.md` instead of the maintainer review. This is the normal path
for newly generated code, not a special case.

### 2. Add failing tests first
Where practical, add small, high-signal tests for:
- malformed or empty API responses from external services
- partial pipeline failures (stage N succeeds, stage N+1 fails)
- missing or invalid credentials/env vars
- rate limit or timeout responses
- boundary inputs (empty datasets, single item, max expected size)
- schema or contract assumptions
- regressions introduced by the branch
- output trustworthiness when the tool generates client-facing scores, summaries, or reports

Use mocks for external API calls. Tests must not make real network requests.

### 3. Apply the smallest safe patch
Fix only what is necessary to resolve the most important issues.
Prefer:
- local fixes
- small interface corrections
- explicit validation at pipeline boundaries
- bounded retries
- targeted refactors in touched code

Avoid:
- broad rewrites
- speculative abstractions
- moving large sections of code without clear need

### 4. Clean up touched files
After tests pass, reduce duplication and improve readability in touched files only.
Prefer deletion over addition when safe.
Remove dead code. Verify no secrets in added log or print statements.

### 5. Validate
Run the most relevant repo commands after edits.
Typical validation set:
- install deps if needed
- lint
- typecheck
- unit tests
- integration tests for changed areas
- build if relevant

Additionally verify:
- `.env` is gitignored
- no credentials appear in CLI output or generated files
- estimated per-run API cost fits the repo-specific targets in `AGENTS.md`

## Constraints
- Preserve current contracts unless explicitly authorized to change them.
- Do not introduce new dependencies casually.
- Keep diffs scoped and reviewable.
- Do not refactor unaffected modules unless directly blocking a safe fix.
- If a larger refactor is truly needed, explain why before doing it.

## Definition of a good Codex pass
A good pass should:
- reduce structural risk
- add confidence through tests
- keep the diff understandable
- avoid unnecessary novelty
- not introduce cost, security, or reliability regressions
