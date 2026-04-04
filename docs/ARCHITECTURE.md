# Architecture Overview

Sable Slopper is a CLI toolkit with 22 subsystems sharing a common config layer, three SQLite databases, and four external API integrations (plus local F5-TTS).

---

## Module Map

```
sable/
├── cli.py               ← main entry point; registers all subcommands
├── config.py            ← shared config loading (file + env var overrides)
│
├── db/
│   └── migrations/  ← 6 incremental migrations (001–006)
│
├── commands/                        ← CLI entry-point modules (one per top-level command)
│   ├── advise.py                    ← sable advise
│   ├── calendar.py                  ← sable calendar
│   ├── diagnose.py                  ← sable diagnose
│   ├── onboard.py                   ← sable onboard
│   ├── playbook.py                  ← sable playbook
│   ├── score.py                     ← sable score
│   ├── tracking.py                  ← sable tracking
│   └── write.py                     ← sable write
│
├── platform/                        ← shared cross-tool data layer
│   ├── db.py                        ← get_db(), ensure_schema()
│   ├── errors.py                    ← SableError + 19 error codes
│   ├── entities.py                  ← entity CRUD
│   ├── tags.py                      ← tag helpers (replace-current / append-history)
│   ├── merge.py                     ← merge candidate + execute_merge
│   ├── jobs.py                      ← job/step lifecycle + resume state machine
│   ├── cost.py                      ← cost logging + budget enforcement
│   ├── stale.py                     ← mark_artifacts_stale()
│   ├── artifacts.py                 ← register_content_artifact() for clip/meme production
│   ├── outcomes.py                  ← re-export: create_outcome, list_outcomes from sable_platform
│   ├── discord_pulse.py             ← discord_pulse_runs writer
│   └── cli.py                       ← org, entity, job, db, resume commands
│
├── roster/              ← account management + markdown profile system
├── clip/                ← video transcription → vertical clip pipeline
│   ├── face_track.py    ← face-centered + motion-tracking crop offsets (CLIP-2/3)
├── meme/                ← template-based meme generation
├── face/                ← face swap via Replicate
├── character_explainer/ ← character explainer videos (TTS + brainrot)
├── wojak/               ← wojak meme generation
│
├── lexicon/             ← community lexicon tracking
│   ├── scanner.py       ← term discovery + frequency analysis
│   ├── store.py         ← lexicon persistence layer
│   ├── writer.py        ← lexicon output rendering
│   └── cli.py           ← sable lexicon group
│
├── narrative/           ← narrative velocity scoring
│   ├── tracker.py       ← narrative arc tracking
│   ├── models.py        ← narrative data models
│   └── cli.py           ← sable narrative group
│
├── style/               ← style gap analysis
│   ├── fingerprint.py   ← style fingerprint extraction
│   ├── delta.py         ← style delta computation
│   ├── report.py        ← style gap report rendering
│   └── cli.py           ← sable style group
│
├── cadence/             ← silence gradient / pre-churn signals
│   ├── signals.py       ← cadence signal detection
│   ├── combine.py       ← signal aggregation
│   ├── store.py         ← cadence persistence layer
│   └── cli.py           ← sable cadence group
│
├── churn/               ← churn intervention playbooks
│   ├── interventions.py ← intervention strategy engine
│   ├── prompts.py       ← intervention prompt templates
│   └── cli.py           ← sable churn group
│
├── serve/               ← FastAPI backend (Phase 2)
│   ├── app.py           ← app factory
│   ├── auth.py          ← Bearer token auth
│   ├── deps.py          ← DB connection helpers
│   └── routes/          ← vault, pulse, meta endpoints
│
├── pulse/               ← performance tracking + attribution
│   ├── cli.py           ← sable pulse group (track, report, recommend, export, trends, account, attribution, link, outcomes, meta)
│   ├── tracker.py       ← tweet fetch + DB write
│   ├── reporter.py      ← performance reporting
│   ├── recommender.py   ← AI recommendations from pulse data
│   ├── attribution.py   ← ContentAttribution: Sable vs organic engagement breakdown
│   ├── account_report.py ← per-format lift report
│   ├── db.py            ← pulse.db connection + schema
│   ├── exporter.py      ← pulse data export
│   ├── feedback.py      ← operator feedback helpers
│   ├── linker.py        ← content→post link helpers
│   ├── outcomes.py      ← content performance outcomes sync (reads pulse.db, writes sable.db)
│   ├── scorer.py        ← hook scoring
│   ├── trends.py        ← trend classification
│   └── meta/            ← content shape intelligence (see below)
│
├── calendar/            ← posting schedule planner
│   └── planner.py       ← CalendarPlan dataclasses + build_calendar + render_calendar
│
└── vault/               ← content vault operations
    ├── init.py          ← vault directory structure creation
    ├── config.py        ← vault config loading (VaultConfig)
    ├── notes.py         ← markdown note CRUD
    ├── sync.py          ← *_meta.json → vault note sync
    ├── search.py        ← frontmatter filter + Claude ranking
    ├── suggest.py       ← reply suggestion engine
    ├── gaps.py          ← topic coverage gap analysis
    ├── enrich.py        ← AI enrichment of vault notes
    ├── log.py           ← posting log + pulse DB sync
    ├── voices.py        ← voice profile page generation
    ├── assign.py        ← content assignment to account queues
    ├── export.py        ← vault zip export
    ├── dashboard.py     ← vault index/dashboard page
    ├── topics.py        ← topic hub CRUD + FAQ linking
    ├── platform_sync.py ← sable.db content_items writer
    └── permissions.py   ← RBAC stub (Phase 2)
```

### pulse/meta subsystem

```
sable/pulse/meta/
├── cli.py          ← CLI entry point (sable pulse meta group)
├── scanner.py      ← SocialData fetch + incremental cursors
├── fingerprint.py  ← 8-bucket format classifier + attribute detection
├── normalize.py    ← author-relative lift computation
├── baselines.py    ← 30d/7d baseline storage and retrieval
├── quality.py      ← confidence grading (A/B/C)
├── trends.py       ← trend + momentum classification
├── topics.py       ← term extraction + ngram analysis + synonym merging
├── watchlist.py    ← watchlist CRUD + health diagnostics
├── analyzer.py     ← combined analysis orchestrator
├── anatomy.py      ← tweet anatomy decomposition
├── digest.py       ← digest formatting helpers
├── recommender.py  ← AI-driven format + topic recommendations
└── reporter.py     ← report rendering
```

---

## Databases

Three SQLite databases stored under `$SABLE_HOME/` (default `~/.sable/`). Note: `meta.db` lives at `$SABLE_HOME/pulse/meta.db`, not directly in `$SABLE_HOME/`.

| File | Contains | Written by |
|------|---------|-----------|
| `pulse.db` | Tweet performance data, posting log, roster accounts | `sable pulse track`, `sable pulse log`, `sable roster` |
| `meta.db` | Watchlist tweet cache, per-author baselines, incremental scan cursors, format baseline history, lexicon_terms, author_cadence | `sable pulse meta scan`, `sable lexicon`, `sable cadence` |
| `sable.db` | Orgs, entities, handles, tags, merge candidates, jobs, cost events, artifacts, outcomes, sync_runs, diagnostic_runs, content_items, discord_pulse_runs | `sable/platform/` modules; `sable/pulse/outcomes.py`; SableTracking `app/platform_sync.py` (external) |

`pulse.db` and `meta.db` do not share tables; `pulse meta` reads roster data from `pulse.db` for org membership but writes only to `meta.db`. `sable.db` is entirely separate and written only through `sable/platform/`. External tools (SableTracking's `app/platform_sync.py`) write via the same `sable/platform/` helpers — they never write raw SQL.

---

## External API Dependencies

| API | Used by | Key | Notes |
|-----|--------|-----|-------|
| Anthropic (Claude) | `clip`, `meme`, `pulse recommend`, `pulse meta`, `vault suggest`, `vault search`, `character-explainer`, `calendar`, `advise`, `write`, `score`, `diagnose`, `churn` | `ANTHROPIC_API_KEY` | Core intelligence layer |
| SocialData | `pulse track`, `pulse trends`, `pulse meta scan` | `SOCIALDATA_API_KEY` | Twitter/X data provider; $0.002/request |
| Replicate | `face` | `REPLICATE_API_TOKEN` | Hosted face-swap model inference |
| ElevenLabs | `character-explainer` (elevenlabs backend) | `ELEVENLABS_API_KEY` | Hosted TTS; voice ID set per-character in profile.yaml |
| F5-TTS (local) | `character-explainer` (local backend) | — | Zero-shot voice cloning; requires local GPU |

---

## Data Flow

### Content production pipeline

```
Source video / URL
      │
      ▼
  sable clip         ← yt-dlp download + faster-whisper transcription
      │
      ▼
  Clip segments      ← Claude selects best moments
      │
      ▼
  assembler.py       ← FFmpeg: stack + captions + brainrot overlay
      │
      ▼
  ~/sable-workspace/output/@handle/
      │
      ▼
  *_meta.json        ← Written alongside every clip
      │
      ▼
  sable vault sync   ← Picks up *_meta.json, creates/updates vault notes
      │
      ▼
  ~/.sable-vault/{org}/  ← Obsidian-compatible markdown vault
```

### Pulse meta intelligence pipeline

```
~/.sable/watchlist.yaml
      │
      ▼
  scanner.py         ← SocialData: fetch tweets, store in meta.db
      │
      ▼
  fingerprint.py     ← Classify each tweet into 8 format buckets
      │
      ▼
  normalize.py       ← Compute per-tweet lift vs author's own median
      │
      ▼
  baselines.py       ← Aggregate + store 30d / 7d baselines per bucket
      │
      ▼
  trends.py          ← Compare current window vs baselines → trend labels
      │
      ▼
  topics.py          ← Extract + rank topic signals from high-lift tweets
      │
      ▼
  Claude analysis    ← Top N tweets + trends + topics → recommendations
      │
      ▼
  Console report + ~/.sable-vault/{org}/pulse_meta_report.md
```

### Calendar planning pipeline

```
pulse.db (posting history)
meta.db  (format baselines)
vault    (unposted notes)
      │
      ▼
  planner.py         ← _get_posting_history + _get_format_trends + _get_vault_inventory
      │
      ▼
  Claude call        ← formats_target + trends + inventory → daily slot plan (JSON)
      │
      ▼
  CalendarPlan       ← CalendarDay[] + CalendarSlot[] dataclasses
      │
      ▼
  render_calendar()  ← markdown output / optional save to ~/.sable/playbooks/
```

### Content attribution pipeline

```
pulse.db (posts + snapshots for last N days)
meta.db  (format baselines for meta-informed classification)
      │
      ▼
  attribution.py     ← compute_attribution(handle, days, org)
      │
      ▼
  ContentAttribution ← Sable vs organic engagement, per-format breakdown, meta lift
      │
      ▼
  render_attribution_report() ← markdown table output
```

---

## Shared Infrastructure

| Component | File | Used by |
|-----------|------|--------|
| Config loading | `sable/config.py` | Everything |
| Path resolution | `sable/shared/paths.py` | Everything that touches `SABLE_HOME` or `SABLE_WORKSPACE` |
| Brainrot library | `sable/clip/brainrot.py` | `clip`, `character-explainer` |
| `sable.db` connection | `sable/platform/db.py` | `sable/platform/` CLI commands |

DB access for pulse/meta is direct via `sable/pulse/db.py` and `sable/pulse/meta/db.py`. `sable.db` goes through `sable/platform/db.py` (`get_db()`).

---

## Phase 2+ Additions

- `sable/serve/` — FastAPI read-only API (Phase 2, complete). Bearer token auth, 7 endpoints. See `docs/COMMANDS.md` § serve.
- `sable/vault/permissions.py` — RBAC implementation (currently a stub; see `docs/ROLES.md`)
- Postgres backend replacing local SQLite (Phase 3)
