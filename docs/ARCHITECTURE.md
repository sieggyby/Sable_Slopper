# Architecture Overview

Sable Slopper is a CLI toolkit with 11 subsystems sharing a common config layer, two SQLite databases, and three external API integrations.

---

## Module Map

```
sable/
├── cli.py               ← main entry point; registers all subcommands
├── config.py            ← shared config loading (file + env var overrides)
│
├── roster/              ← account management + markdown profile system
├── clip/                ← video transcription → vertical clip pipeline
├── meme/                ← template-based meme generation
├── face/                ← face swap via Replicate
├── character_explainer/ ← character explainer videos (TTS + brainrot)
├── wojak/               ← wojak meme generation
│
├── pulse/               ← performance tracking
│   ├── cli.py           ← sable pulse group
│   ├── tracker.py       ← tweet fetch + DB write
│   ├── reporter.py      ← performance reporting
│   ├── recommender.py   ← AI recommendations from pulse data
│   └── meta/            ← content shape intelligence (see below)
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
└── watchlist.py    ← watchlist CRUD + health diagnostics
```

---

## Databases

Two SQLite databases, both stored in `$SABLE_HOME/` (default `~/.sable/`).

| File | Contains | Written by |
|------|---------|-----------|
| `pulse.db` | Tweet performance data, posting log, roster accounts | `sable pulse track`, `sable pulse log`, `sable roster` |
| `meta.db` | Watchlist tweet cache, per-author baselines, incremental scan cursors, format baseline history | `sable pulse meta scan` |

The databases do not share tables; `pulse meta` reads roster data from `pulse.db` for org membership but writes only to `meta.db`.

---

## External API Dependencies

| API | Used by | Key | Notes |
|-----|--------|-----|-------|
| Anthropic (Claude) | `clip`, `meme`, `pulse recommend`, `pulse meta`, `vault suggest`, `vault search`, `character-explainer` | `ANTHROPIC_API_KEY` | Core intelligence layer |
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

---

## Shared Infrastructure

| Component | File | Used by |
|-----------|------|--------|
| Config loading | `sable/config.py` | Everything |
| Path resolution | `sable/shared/paths.py` | Everything that touches `SABLE_HOME` or `SABLE_WORKSPACE` |
| Brainrot library | `sable/clip/brainrot.py` | `clip`, `character-explainer` |

DB access is direct via `sable/pulse/db.py` (pulse data) and `sable/pulse/meta/db.py` (meta intelligence); there is no shared connection factory.

---

## Phase 2+ Additions (Not Yet Built)

- `sable/serve/` — FastAPI app wrapping vault + pulse functions (see `docs/ROADMAP.md`)
- `sable/vault/permissions.py` — RBAC implementation (currently a stub; see `docs/ROLES.md`)
- Postgres backend replacing local SQLite (Phase 3)
