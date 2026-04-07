# CLAUDE.md — Sable Slopper

Context, decisions, and plans that should survive a session restart.

---

## Strategic Context

Slopper is in a **6–12 month services phase** — delivering content for managed client accounts, not building a general-purpose product. CLI is sufficient; Phase 2 web UI is explicitly deferred until 5+ active accounts make CLI management impractical.

**Active and incoming clients:** TIG Foundation (active), Multisynq (pseudo-client), PSY Protocol (best current lead), Flow L1 (next after PSY).

**What not to build:** Multi-tenant, self-serve, or externally accessible features. Slopper stays internal operator tooling.

---

## What This Is

Sable Slopper is a CLI toolkit for high-volume crypto Twitter content production.
It is Sable's internal tool — not a client product. Current deployment: local CLI only.

**One-liner:** `sable <command>` wraps Claude, ffmpeg, yt-dlp, and social APIs into a
production pipeline for managed Twitter accounts.

See `README.md` for full command reference. See `docs/ARCHITECTURE.md` for module map and data flow.

---

## Current Phase

**Phase 1 (CLI) is complete.** All commands implemented: vault, pulse, clip, meme, face, character-explainer, wojak, calendar, write, score, diagnose, advise, weekly, and more.
All community intelligence features are shipped (FEATURE-10 through FEATURE-16, CHURN-1, CHURN-2).
Weekly automation shipped (2026-04-06): `sable weekly run` orchestrates the full weekly cycle (pulse track → meta scan → advise → calendar → vault sync) with `--all`, `--dry-run`, `--cost-estimate`. Clip review triage (`sable clip review`) and launchd scheduling (`sable weekly cron install`) also shipped.

**Phase 2 (`sable serve`) is complete.** Read-only FastAPI backend exposing pulse, meta, vault, and cost data over HTTP. Named token auth (SS-17), rate limiting (SS-15), health dependency checks (SS-16), 8 API endpoints + /health. Cost forecast endpoint (`GET /api/v1/cost/org/{org_id}/cost-forecast`) added 2026-04-06. Optional dep: `pip install -e ".[serve]"`. Production hardening (SS-1 through SS-21) complete. Codit audit remediation (all CRIT/HIGH/MED) complete. Test count: 1213.

**Production URL:** `https://api.sable.tools` — Hetzner CX21 VPS (178.156.204.125). Cloudflare named tunnel `sable-serve` → `localhost:8420`. Both `cloudflared` and `sable serve` run as systemd services. Weekly automation runs via systemd timer (Monday 06:00 UTC). Postgres installed on the same box, pending migration from SQLite. See `deploy/DEPLOY.md` for full VPS setup and Postgres transition plan.

**RBAC (shipped 2026-04-05):** Three roles (admin/creator/operator) with per-token org scoping.
Operators see only their allowed orgs. Config in `~/.sable/config.yaml` under `serve.tokens`.
See `docs/ROLES.md` for the permission matrix and config format.

**Phase 3 (VPS) is partially complete.** Hetzner CX21 deployed 2026-04-06. systemd services running (`sable-serve`, `sable-weekly.timer`, `cloudflared`). Deploy scripts audited: yt-dlp added, log rotation configured (`deploy/logrotate.d/sable-serve`), smoke test added (`deploy/smoke-test.sh`). Postgres installed, awaiting `sable.db` migration (dialect adapter needed). See `deploy/DEPLOY.md`. Phase 4 = multi-tenant (future/speculative).

---

## Architecture Decisions (not obvious from code)

- **Three SQLite databases, no ORM.** `pulse.db` (performance + posting log), `meta.db`
  (watchlist tweet cache + format intelligence), and `sable.db` (platform cross-tool store).
  Hand-written SQL + dataclasses throughout. `sable db migrate` runs
  all migrations (001–006) via `ensure_schema()`.
  See `docs/SCHEMA_INVENTORY.md` for full table and model inventory.
  `pulse.db.posts` has `is_thread` and `thread_length` columns (added 2026-04-03).

- **`pulse.db` and `meta.db` schemas are embedded Python strings, not migration files.**
  Each module (`sable/pulse/db.py`, `sable/pulse/meta/db.py`) holds a `_SCHEMA` string
  applied via `CREATE TABLE IF NOT EXISTS` on every `migrate()` call. `meta.db`'s `_SCHEMA`
  now also includes `lexicon_terms` and `author_cadence` tables. There are no versioned
  migration files for these two databases — `sable db migrate` only covers `sable.db`.
  Schema changes to pulse/meta require editing the `_SCHEMA` string directly.

- **No shared DB connection factory for pulse/meta.** Each module (`sable/pulse/db.py`,
  `sable/pulse/meta/db.py`) opens its own `sqlite3` connection directly. `sable/platform/db.py`
  provides `get_db()` for `sable.db` only.

- **`org` is a plain string in pulse/meta/vault, and a table in `sable.db`.** The `orgs` table
  now exists in `sable.db`; pulse/meta/vault still use plain string org grouping.

- **`sable.db` is the platform cross-tool store.** Entities, tags, merge candidates, jobs,
  artifacts, cost events, outcomes, diagnostic runs, and sync runs live here. `sable/platform/`
  modules are the primary writers; `sable/pulse/outcomes.py` also writes via `sable/platform/outcomes.py`. All CLI handlers catch `SableError` and call `sys.exit(1)`.
  `diagnostic_runs` now has language columns (`language_arc_phase`,
  `emergent_cultural_terms_json`, `mantra_candidates_json`) queried by `--community-voice`,
  but these columns require a future migration to exist in the table.

- **Vault notes are raw dicts.** Vault notes are Obsidian-compatible markdown files.
  Frontmatter is read as raw dicts — no typed `ContentItem` class wraps them.

- **Profile files are markdown, not config.** Each account gets `~/.sable/profiles/@handle/`
  with `tone.md`, `interests.md`, `context.md`, `notes.md`. These are injected verbatim
  into Claude prompts — not parsed, not structured.

- **yt-dlp is integrated.** `sable clip process` accepts YouTube URLs directly. No manual
  download step needed.

- **SocialData is the Twitter data provider** (`$0.002/request`). Not the Twitter API.
  Cost guardrail: soft warning at $3/run, monthly ceiling ~$200.

- **Five community intelligence modules** added for FEATURE-10 through FEATURE-16:
  - `sable/lexicon/` — community vocabulary extraction (reads meta.db)
  - `sable/narrative/` — narrative arc keyword tracking (reads meta.db)
  - `sable/style/` — posting style gap analysis (reads pulse.db + meta.db)
  - `sable/cadence/` — pre-churn silence signals (reads meta.db, writes author_cadence)
  - `sable/churn/` — intervention playbook generation (Claude calls, reads sable.db for budget)

---

## Clip Pipeline — Settled Decisions

Non-obvious decisions that reverse naive intuition — get these wrong and you reproduce known bugs:

- **Pause threshold for `_candidate_endpoints`: 0.15s** (lowered from 0.3s). Fast-paced
  crypto interviews have real sentence boundaries at 0.15–0.29s. The old threshold
  caused clips to cluster in the 43–47s range.

- **`kill` flag exists on batch eval.** Claude can discard a clip entirely; no-landing
  clips were forced through before this.

- **`extend` flag exists.** When the long variant still cuts mid-argument, pipeline
  searches up to 20s beyond the endpoint for the next clean pause-backed boundary.

- **Brainrot `pick()` prefers long sources.** `source_duration >= clip_duration / 2`
  to prevent visible looping. Falls back to any energy-matched source if nothing long enough.

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
| `codit.md` | Codex audit findings (2026-03-23) — all CRIT/HIGH/MED resolved |
| `TODO.md` | Main development queue: audit remediation log, open hardening items, and completed feature history |
| `AGENTS.md` | Instructions for Codex review role (QA layer) |
| `docs/COMMANDS.md` | Full CLI command reference with flags and examples |
| `deploy/DEPLOY.md` | VPS deployment guide: Hetzner setup, data migration, Cloudflare tunnel, Postgres transition |
| `docs/LOCAL_DEV.md` | Local dev setup, venv, test runner, env var patterns |
| `docs/PROMPTS.md` | Claude prompt templates and prompt engineering notes |
| `docs/IMPLEMENTATION_LOG.md` | Chronological record of shipped features and decisions |

---

## Working Conventions

- **Small, reviewable patches over rewrites.** Don't refactor untouched modules.
- **Don't silently change API, schema, or persistence contracts.**
- **No new dependencies without clear justification.**
- **Preserve behavior unless the task explicitly changes it.**
- API keys load from env vars or `~/.sable/config.yaml`. Never in logs or committed code.
- Cost-sensitive: flag any API call in an unbounded loop; flag missing caching on reused data.
