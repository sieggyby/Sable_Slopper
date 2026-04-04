# Sable Slopper — CLI Command Reference

Full reference for every `sable` command and flag. All commands run via `sable <command> [options]`.

---

## roster

Account management and markdown profile system.

```
sable roster add HANDLE [options]        Add a managed account
sable roster remove HANDLE               Remove an account from the roster
sable roster show HANDLE                 Show account config + profile preview
sable roster list [--org ORG]            List all accounts (optionally filtered by org)
sable roster update HANDLE [options]     Update account fields
```

### roster add / update flags
| Flag | Description |
|------|-------------|
| `--display-name NAME` | Account display name |
| `--org ORG` | Org slug this account belongs to |
| `--archetype ARCHETYPE` | Voice archetype (e.g. "degen analyst") |
| `--platform PLATFORM` | Platform (default: twitter) |

### roster profile
```
sable roster profile init HANDLE         Scaffold blank profile files (tone, interests, context, notes)
sable roster profile show HANDLE         Print all profile files
sable roster profile edit HANDLE --file FILE   Open a profile file in $EDITOR
```

| `--file` value | What it edits |
|----------------|---------------|
| `tone` | Voice, language patterns, what to avoid |
| `interests` | Topics, crypto sub-communities, current meta |
| `context` | Background, community standing, lore |
| `notes` | What's landed, what flopped, current arcs |

---

## clip

Video → vertical clips with brainrot + captions.

```
sable clip process SOURCE --account HANDLE [options]
```

`SOURCE` can be a local file path or a YouTube URL (yt-dlp handles download automatically).

| Flag | Default | Description |
|------|---------|-------------|
| `--account / -a` | required | Account handle e.g. `@tig_intern` |
| `--num-clips / -n` | all worthy | Max clips to produce |
| `--min-duration` | 15s | Drop clips shorter than this |
| `--max-duration` | 45s | Trim clips longer than this at a sentence boundary |
| `--target-duration` | — | Single duration target; sets min/max with ±10s tolerance |
| `--clip-sizes` | — | Comma-separated targets e.g. `15,30` |
| `--whisper-model` | `base.en` | faster-whisper model name |
| `--dry-run` | — | Transcribe + detect windows, print plan, skip Claude and encoding |
| `--platform` | `twitter` | Output encoding profile (`twitter`, `discord`, `telegram`) |
| `--caption-style` | account default | `word`, `phrase`, `none` |
| `--caption-color` | auto | `white`, `yellow`, `black`, `cyan`, `green`, `red`, `#RRGGBB` |
| `--brainrot-energy` | account default | `low`, `medium`, `high` |
| `--no-brainrot` | — | Skip brainrot overlay entirely |
| `--image-overlay` | — | PNG to composite in bottom-left |
| `--no-highlight` | — | Disable active-word karaoke highlight |
| `--audio-only` | — | Source audio only — brainrot fills full frame (podcasts, screen-shares) |
| `--face-track` | — | Center crop on detected faces; falls back to motion tracking, then center |
| `--org` | account org | Org slug for cost logging (logs Claude spend without budget gating) |

### clip brainrot
```
sable clip brainrot add FILE --energy LEVEL [--tags TAGS]
sable clip brainrot list
sable clip brainrot remove FILE [--delete]
sable clip brainrot trace FILE
```

---

## meme

Template-based meme generation.

```
sable meme list-templates
sable meme generate --account HANDLE [--template NAME] [--topic TOPIC] [--dry-run]
sable meme batch --account HANDLE --count N [--render]
```

---

## face

Replicate-powered face swap.

```
sable face library add PHOTO --name NAME --consent
sable face swap TARGET --account HANDLE [--dry-run] [--quality LEVEL]
```

| `--quality` | Description |
|-------------|-------------|
| `low` | Fast, lower fidelity |
| `medium` | Balanced (default) |
| `high` | Slower, highest fidelity |

---

## pulse

Performance tracking, format lift, attribution, and AI recommendations.

```
sable pulse track --account HANDLE [--mock]
sable pulse report --account HANDLE [--followers N]
sable pulse recommend --account HANDLE [--update-roster]
sable pulse export --account HANDLE --format FORMAT --output PATH
sable pulse trends --org ORG [--format BUCKET]
sable pulse account HANDLE [--days N] [--org ORG]
sable pulse attribution HANDLE [--days N] [--org ORG]
sable pulse link CONTENT_ID POST_ID --account HANDLE --org ORG
sable pulse outcomes --org ORG --handle HANDLE
```

### pulse outcomes

Compute content performance outcomes from pulse snapshots and write them to `sable.db outcomes`.
Groups posts by `sable_content_type`, computes average engagement rate per type plus an aggregate,
and records deltas against prior outcome rows.

```
sable pulse outcomes --org ORG --handle HANDLE
```

| Flag | Required | Description |
|------|----------|-------------|
| `--org` | yes | Org ID for outcome records |
| `--handle` | yes | Account handle to compute outcomes for |

### pulse meta

Content shape intelligence: format trends, topic signals, watchlist management.

```
sable pulse meta --org ORG [--cheap] [--full] [--dry-run]
sable pulse meta scan --org ORG [--cheap] [--full] [--dry-run]
sable pulse meta watchlist list [--org ORG]
sable pulse meta watchlist add HANDLE [--org ORG] [--niche NICHE]
sable pulse meta watchlist remove HANDLE [--org ORG]
sable pulse meta watchlist health --org ORG
```

---

## character-explainer

Brainrot explainer videos with famous character voices.

```
sable character-explainer list-characters
sable character-explainer generate [options]
sable character-explainer setup-voice [options]
```

### character-explainer generate flags
| Flag | Default | Description |
|------|---------|-------------|
| `--topic` | required | Topic to explain |
| `--character` | required | Character ID (see `list-characters`) |
| `--bg-video` | random from brainrot library | Brainrot background video |
| `--output` | auto | Output mp4 path |
| `--background-md` | — | Markdown context file injected into script prompt |
| `--tts-backend` | character default | `local` (F5-TTS) or `elevenlabs` |
| `--target-duration` | `30` | Target video length in seconds |
| `--orientation` | `landscape` | `landscape` (1280×720) or `portrait` (720×1280) |
| `--platform` | `twitter` | Encoding preset: `twitter`, `youtube`, `discord`, `telegram` |
| `--no-talking-head` | — | Disable mouth animation |

### character-explainer setup-voice flags
| Flag | Description |
|------|-------------|
| `--character` | Character ID |
| `--source` | YouTube URL or local file path |
| `--start N` | Trim start (seconds) |
| `--end N` | Trim end (seconds) |
| `--mouth-open PATH` | PNG for open mouth animation |
| `--mouth-closed PATH` | PNG for closed mouth animation |

---

## vault

Content catalog, search engine, and client knowledge base.

```
sable vault init --org ORG [--vault PATH]
sable vault sync --org ORG [--workspace PATH] [--vault PATH] [--dry-run]
sable vault enrich --org ORG [--vault PATH]
sable vault status --org ORG [--vault PATH]
sable vault search QUERY --org ORG [--depth DEPTH] [--type TYPE] [--available-for HANDLE] [--reply-to TWEET] [--format BUCKET]
sable vault suggest --org ORG [--tweet-text TEXT] [--tweet-url URL] [--account HANDLE]
sable vault log [CONTENT_ID] --account HANDLE --tweet-id ID --org ORG [--sync-from-pulse] [--bulk CSV]
sable vault assign CONTENT_ID --account HANDLE --org ORG [--caption TEXT]
sable vault niche-gaps --org ORG [--top N] [--min-authors N] [--json]
sable vault export --org ORG [--output PATH] [--include-media]
sable vault topic add SLUG --display-name NAME --org ORG
sable vault topic list --org ORG
sable vault topic refresh --org ORG
```

---

## wojak

Wojak asset library and Claude-driven scene compositor.

```
sable wojak list
sable wojak add URL --id ID --name NAME --emotion EMOTION [--tags TAGS] [--description DESC]
sable wojak download-missing
sable wojak scene generate --account HANDLE --topic TOPIC
sable wojak scene render SPEC_YAML --account HANDLE [--output PATH]
```

---

## calendar

Claude-generated posting schedule with vault inventory + trend alignment.

```
sable calendar HANDLE [--org ORG] [--days N] [--formats-target N] [--save] [--churn-input PATH] [--prioritize-churn]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--org` | roster org | Org slug |
| `--days` | 7 | Planning horizon in days |
| `--formats-target` | 4 | Unique format types to target |
| `--save` | — | Save to `~/.sable/playbooks/calendar_{handle}_{date}.md` |
| `--churn-input PATH` | — | Path to at-risk members JSON for re-engagement slot injection |
| `--prioritize-churn` | — | Remove 30% cap on churn-annotated slots |

---

## diagnose

Full account audit: format health, topic gaps, vault waste, cadence, engagement.

```
sable diagnose HANDLE [--org ORG] [--days N] [--save]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--org` | roster org | Org slug |
| `--days` | 30 | Look-back window in days |
| `--save` | — | Save diagnosis artifact to sable.db |

---

## write

Generate tweet variants for a managed account in their voice.

```
sable write HANDLE [options]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--format BUCKET` | auto | Format bucket (e.g. `standalone_text`, `short_clip`) |
| `--topic TEXT` | account interests | Topic to write about |
| `--source-url URL` | — | Source tweet URL for quote-tweet format |
| `--variants N` | 3 | Number of variants to generate |
| `--org ORG` | roster org | Org context for trend data |
| `--score` | — | Score each variant's hook against recent high-performing patterns |
| `--lexicon` | — | Inject community vocabulary from lexicon into prompt |
| `--voice-check` | — | Use full voice corpus for richer draft scoring (implies `--score`) |
| `--watchlist-wire` | — | Inject top niche topics from meta.db into prompt |
| `--no-anatomy` | — | Skip viral anatomy pattern injection |

---

## score

Score a draft tweet's hook against recent high-performing patterns.

```
sable score HANDLE --text "draft tweet" [--format BUCKET] [--org ORG]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--text` | required | Draft tweet text to score |
| `--format` | `standalone_text` | Format bucket to score against |
| `--org` | roster org | Org slug |

---

## advise

Multi-stage strategic brief: profile → pulse → vault → recommendations.

```
sable advise HANDLE [--org ORG_ID] [--cheap] [--force] [--dry-run] [--export] [--bridge-aware] [--community-voice] [--churn-input PATH]
```

| Flag | Description |
|------|-------------|
| `--org ORG_ID` | Org ID (defaults to roster account org). Allows handles not in roster. |
| `--cheap` | Use cheaper/faster model |
| `--force` | Force regeneration even if cached |
| `--dry-run` | Estimate cost without generating |
| `--export` | Export brief to `./output/advise_<org>_<YYYY-MM-DD>.md` |
| `--bridge-aware` | Inject bridge node activity into the brief |
| `--community-voice` | Inject CultGrader community language data into the brief |
| `--churn-input PATH` | Path to at-risk members JSON to fold into the brief |

---

## onboard

Onboard a new client org through a 6-step pipeline from a prospect YAML.

```
sable onboard PROSPECT_YAML [--org ORG_ID] [--yes] [--non-interactive]
```

| Flag | Description |
|------|-------------|
| `--org ORG_ID` | Override org_id (default: from YAML or filename) |
| `--yes` | Accept all defaults without prompting |
| `--non-interactive` | Fail if disambiguation is needed |

---

## playbook

Generate Discord engagement playbook. Delegates to Cult Grader.

```
sable playbook discord ORG_ID [--force] [--cheap] [--dry-run]
```

| Flag | Description |
|------|-------------|
| `--force` | Force regeneration even if cached |
| `--cheap` | Use cheaper/faster model |
| `--dry-run` | Estimate cost without generating |

---

## tracking

Sync SableTracking data into sable.db. Delegates to SableTracking's `platform_sync`.

```
sable tracking sync ORG_ID
```

---

## serve

Read-only API server exposing pulse, meta, and vault data over HTTP. No Claude calls, no cost.

```
sable serve [--host HOST] [--port PORT] [--reload]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--host` | `127.0.0.1` | Bind address |
| `--port` | `8000` | Bind port |
| `--reload` | — | Auto-reload on code changes (dev mode) |

Optional dependency: `pip install -e ".[serve]"`

### Authentication

All `/api/` endpoints require a Bearer token configured via `serve.token` in `config.yaml`. The `/health` endpoint is unauthenticated.

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check (no auth) |
| GET | `/api/pulse/performance/{org}` | Pulse performance summary for org |
| GET | `/api/pulse/posting-log/{org}` | Posting log for org |
| GET | `/api/meta/topics/{org}` | Topic signals for org |
| GET | `/api/meta/baselines/{org}` | Format baselines for org |
| GET | `/api/meta/watchlist/{org}` | Watchlist entries for org |
| GET | `/api/vault/inventory/{org}` | Vault inventory for org |
| GET | `/api/vault/search/{org}?q=...` | Vault search (query param `q`) |

---

## config

Read and write config values in `~/.sable/config.yaml`.

```
sable config show          # Print current config (API keys masked)
sable config set KEY VALUE # Set a config value
```

Common keys: `anthropic_api_key`, `replicate_api_key`, `socialdata_api_key`, `default_model`, `workspace`.

---

## org

Manage orgs in sable.db.

```
sable org add ORG_ID [--display-name NAME]
sable org list
sable org show ORG_ID
```

---

## entity

Manage community members (entities) in sable.db.

```
sable entity search QUERY [--org ORG]
sable entity show ENTITY_ID
sable entity merge ENTITY_A ENTITY_B [--force]
sable entity tag ENTITY_ID TAG [--replace]
sable entity note ENTITY_ID TEXT
```

---

## job

Inspect job lifecycle records in sable.db.

```
sable job list [--org ORG] [--status STATUS]
sable job show JOB_ID
```

---

## db

Run sable.db migrations and inspect schema state.

```
sable db migrate
sable db status
```

---

## resume

Resume a paused or failed job from its last checkpoint.

```
sable resume JOB_ID [--force]
```

---

## lexicon

Community vocabulary extraction and management.

```
sable lexicon scan --org ORG [--days N] [--top N] [--no-interpret] [--dry-run]
sable lexicon list --org ORG
sable lexicon add --org ORG --term TERM [--gloss GLOSS]
sable lexicon remove TERM --org ORG
```

### lexicon scan flags
| Flag | Default | Description |
|------|---------|-------------|
| `--org` | required | Org to scan |
| `--days` | 14 | Look-back window in days |
| `--top` | 20 | Max terms to extract |
| `--no-interpret` | — | Skip Claude classification (extraction only) |
| `--dry-run` | — | Show corpus stats without scanning or writing |

### lexicon add flags
| Flag | Description |
|------|-------------|
| `--org` | Org to add to (required) |
| `--term` | Term to add (required) |
| `--gloss` | Definition/explanation |

---

## narrative

Narrative velocity — keyword spread scoring for narrative arcs.

```
sable narrative score --org ORG [--beats PATH] [--days N] [--output PATH]
sable narrative beats edit --org ORG
```

### narrative score flags
| Flag | Default | Description |
|------|---------|-------------|
| `--org` | required | Org to score |
| `--beats` | `~/.sable/{org}/narrative_beats.yaml` | Path to narrative_beats.yaml |
| `--days` | 14 | Look-back window in days |
| `--output` | — | Write JSON report to file |

### narrative beats edit
Opens the narrative beats YAML in `$EDITOR`. Creates a template file if none exists.

---

## style-delta

Quantitative posting style gap analysis vs watchlist top performers.

```
sable style-delta --handle HANDLE --org ORG [--output PATH]
```

| Flag | Description |
|------|-------------|
| `--handle` | Managed account handle (required) |
| `--org` | Org for watchlist comparison (required) |
| `--output` | Write markdown report to file |

---

## silence-gradient

Pre-decay cadence signals from watchlist data. Detects community members going quiet before full churn.

```
sable silence-gradient --org ORG [--top N] [--window N] [--include-insufficient] [--output PATH]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--org` | required | Org to analyze |
| `--top` | 20 | Show top N authors |
| `--window` | 30 | Window in days (must be even, >= 6) |
| `--include-insufficient` | — | Include authors with some insufficient signals |
| `--output` | — | Write JSON report to file |

---

## churn

Churn detection and intervention tools.

```
sable churn intervene --org ORG --input PATH [--output PATH] [--force] [--dry-run]
```

### churn intervene flags
| Flag | Description |
|------|-------------|
| `--org` | Org ID (required) |
| `--input` | Path to at-risk members JSON file (required) |
| `--output` | Write playbook JSON to file |
| `--force` | Allow >50 members (bypasses soft cap) |
| `--dry-run` | Estimate cost without generating |
