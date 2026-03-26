# CLAUDE.md — Sable Slopper

Context, decisions, and plans that should survive a session restart.

---

## What This Is

Sable Slopper is a CLI toolkit for high-volume crypto Twitter content production.
It is Sable's internal tool — not a client product. Current deployment: local CLI only.

**One-liner:** `sable <command>` wraps Claude, ffmpeg, yt-dlp, and social APIs into a
production pipeline for managed Twitter accounts.

See `README.md` for full command reference. See `docs/ARCHITECTURE.md` for module map and data flow.

---

## Current Phase

**Phase 1 (CLI) is complete.** All vault, pulse, clip, meme, face, character-explainer,
wojak, calendar, write, score, diagnose, and advise commands are implemented.
`sable pulse` now has 9 subcommands: `track`, `report`, `recommend`, `export`, `trends`,
`account`, `attribution`, `link`, and the `meta` subgroup.

**Platform layer (Round 1) is complete.** `sable.db` is live at `~/.sable/sable.db`.
`sable/platform/` provides shared entity, tag, merge, job, cost, and error helpers.
Five new CLI commands: `sable org`, `sable entity`, `sable job`, `sable db`, `sable resume`.

**Cult Doctor (Round 2) is complete.** Cult Grader now writes to sable.db after every run (via `platform_sync.py` in Sable_Cult_Grader). New: DB migrations 002+003 extend `sync_runs` and `diagnostic_runs` schemas. Discord playbook generator (`playbook/`) and operator bot (`bot/`) are live in Sable_Cult_Grader. Schema version is now 3.

**SableTracking (Round 3) is complete.** `app/platform_sync.py` in SableTracking bridges
Google Sheets (contributors + content_log) → `sable.db` (entities, handles, tags, content_items).
Async sync runner, `_apply_pending_migrations()`, `SABLE_CLIENT_ORG_MAP` env var config.
36 tests passing. Schema version remains 3.

**Phase 2 (local web UI) is planned but not started.**
- Entry point: `sable serve` → FastAPI app in `sable/serve/`
- Cloudflare Tunnel, role-based access (see `docs/ROLES.md`)
- `sable/vault/permissions.py` is a stub waiting for Phase 2
- Full plan in `docs/ROADMAP.md` and `TODO.md`

Phase 3 = VPS + Postgres. Phase 4 = multi-tenant. Both are future/speculative.

---

## Architecture Decisions (not obvious from code)

- **Three SQLite databases, no ORM.** `pulse.db` (performance + posting log), `meta.db`
  (watchlist tweet cache + format intelligence), and `sable.db` (platform cross-tool store).
  Hand-written SQL + dataclasses throughout. `sable db migrate` runs
  `sable/db/migrations/001_initial.sql` via `ensure_schema()`.
  See `docs/SCHEMA_INVENTORY.md` for full table and model inventory.

- **No shared DB connection factory for pulse/meta.** Each module (`sable/pulse/db.py`,
  `sable/pulse/meta/db.py`) opens its own `sqlite3` connection directly. `sable/platform/db.py`
  provides `get_db()` for `sable.db` only.

- **`org` is a plain string in pulse/meta/vault, and a table in `sable.db`.** The `orgs` table
  now exists in `sable.db`; pulse/meta/vault still use plain string org grouping.

- **`sable.db` is the platform cross-tool store.** Entities, tags, merge candidates, jobs,
  artifacts, cost events, diagnostic runs, and sync runs live here. `sable/platform/`
  modules are the only writers. All CLI handlers catch `SableError` and call `sys.exit(1)`.

- **Vault notes are raw dicts.** Vault notes are Obsidian-compatible markdown files.
  Frontmatter is read as raw dicts — no typed `ContentItem` class wraps them.

- **Profile files are markdown, not config.** Each account gets `~/.sable/profiles/@handle/`
  with `tone.md`, `interests.md`, `context.md`, `notes.md`. These are injected verbatim
  into Claude prompts — not parsed, not structured.

- **yt-dlp is integrated.** `sable clip process` accepts YouTube URLs directly. No manual
  download step needed.

- **SocialData is the Twitter data provider** (`$0.002/request`). Not the Twitter API.
  Cost guardrail: soft warning at $3/run, monthly ceiling ~$200.

---

## Clip Pipeline — Decisions and Known Lessons

The clip pipeline iterates a lot. Key settled decisions (from `CLIP_LESSONS.md`):

- **Batch eval (Option B):** single Claude call for all clips. Gives cross-clip context
  and is efficient. Per-clip calls (Option A) were too slow.

- **Pause threshold for `_candidate_endpoints`: 0.15s** (lowered from 0.3s). Fast-paced
  crypto interviews have real sentence boundaries at 0.15–0.29s. The old threshold
  caused clips to cluster in the 43–47s range.

- **`kill` flag exists on batch eval.** Claude can now discard a clip entirely (no-landing
  clips were forced through before this).

- **`extend` flag exists.** When the long variant still cuts mid-argument, pipeline
  searches up to 20s beyond the endpoint for the next clean pause-backed boundary.

- **Brainrot `pick()` prefers long sources.** `source_duration >= clip_duration / 2`
  to prevent visible looping. Falls back to any energy-matched source if nothing long enough.

**Still open (next iteration):**
- Leading filler trim ✓ done (2026-03-26)
- Context backtrack for dangling references ✓ done (2026-03-26)
- Per-clip score in CLI output ✓ done (2026-03-26)
- Brainrot theme matching (not just energy)

---

## Key Docs Index

| Doc | What it covers |
|-----|---------------|
| `docs/ARCHITECTURE.md` | Module map, databases, external APIs, data flow diagrams |
| `docs/SCHEMA_INVENTORY.md` | Every table, Python model, YAML schema in the codebase |
| `docs/ROADMAP.md` | Phase 1–4 plan with file-level detail for Phase 2 |
| `docs/PULSE_META.md` | Full pulse meta docs: output interpretation, config tuning |
| `docs/CONFIG_REFERENCE.md` | All config keys and defaults |
| `docs/ENV_VARS.md` | All env vars, local dev patterns |
| `docs/ROLES.md` | Phase 2 RBAC permission matrix |
| `docs/QA_WORKFLOW.md` | Default hardening workflow |
| `docs/THREAT_MODEL.md` | Adversarial testing lens |
| `CLIP_LESSONS.md` | Tracked failures and fixes in the clip pipeline |
| `TODO.md` | Non-MVP features deferred to Phase 2+ |
| `AGENTS.md` | Instructions for Codex review role (QA layer) |

---

## Working Conventions

- **Small, reviewable patches over rewrites.** Don't refactor untouched modules.
- **Don't silently change API, schema, or persistence contracts.**
- **No new dependencies without clear justification.**
- **Preserve behavior unless the task explicitly changes it.**
- API keys load from env vars or `~/.sable/config.yaml`. Never in logs or committed code.
- Cost-sensitive: flag any API call in an unbounded loop; flag missing caching on reused data.
