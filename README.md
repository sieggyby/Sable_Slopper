# Sable Slopper

High-volume crypto Twitter content production toolkit. CLI-driven, Claude-powered.

## Modules

| Command | Description |
|---------|-------------|
| `sable roster` | Account management + markdown profile system |
| `sable clip` | Video → vertical clips with brainrot + captions |
| `sable meme` | Template-based meme generation |
| `sable face` | Replicate-powered face swap |
| `sable pulse` | Performance tracking, format lift, attribution, content outcomes, and AI recommendations |
| `sable character-explainer` | Brainrot explainer videos with famous character voices |
| `sable vault` | Content catalog, search engine, and client knowledge base |
| `sable wojak` | Wojak asset library and Claude-driven scene compositor |
| `sable calendar` | Claude-generated posting schedule with vault inventory + trend alignment |
| `sable diagnose` | Full account audit: format health, topic gaps, vault waste, cadence |
| `sable write` | Draft tweets and threads in an account's voice |
| `sable score` | Hook quality scorer |
| `sable advise` | Multi-stage strategic brief (profile → pulse → vault → recommendations) |
| `sable onboard` | Onboard a new client org via prospect YAML (6-step pipeline) |
| `sable playbook` | Generate Discord engagement playbook (delegates to Cult Grader) |
| `sable tracking` | Sync SableTracking data into sable.db |
| `sable lexicon` | Community vocabulary extraction + lexicon management |
| `sable narrative` | Narrative velocity: keyword spread scoring for narrative arcs |
| `sable style-delta` | Posting style gap analysis: managed account vs top-performing watchlist |
| `sable silence-gradient` | Pre-churn cadence signals: volume drop, engagement drop, format regression |
| `sable churn` | Churn intervention playbook generation for at-risk community members |
| `sable weekly` | Automated weekly cycle: pulse track → meta scan → advise → calendar → vault sync |
| `sable serve` | Read-only API server (FastAPI): pulse, meta, vault, cost endpoints with Bearer auth + RBAC |
| `sable org` / `sable entity` / `sable job` / `sable db` / `sable resume` | Platform management: orgs, entities, jobs, sable.db migrations |

## Quick Start

```bash
pip install -e .

# Configure API keys
sable config set anthropic_api_key sk-ant-...
sable config set replicate_api_key r8_...
sable config set socialdata_api_key ...

# Add an account
sable roster add @tig_intern --display-name "Tig Intern" --org "Sable" --archetype "degen analyst"

# Edit the profile (tone, interests, context, ops notes)
sable roster profile edit @tig_intern --file tone
sable roster profile edit @tig_intern --file interests

# Show full account + profile preview
sable roster show @tig_intern
```

## Per-Account Profile Files

Each account gets a profile directory at `~/.sable/profiles/@handle/`:

```
~/.sable/profiles/
└── @tig_intern/
    ├── tone.md        # Voice, language patterns, what to avoid
    ├── interests.md   # Topics, crypto sub-communities, current meta
    ├── context.md     # Background, community standing, lore
    └── notes.md       # What's landed, what flopped, current arcs
```

All tools that call Claude (`clip`, `meme`, `pulse recommend`) auto-load these files and inject them into prompts.

```bash
sable roster profile init @handle      # Scaffold blank files
sable roster profile show @handle      # Print all profile files
sable roster profile edit @handle --file tone   # Open in $EDITOR
```

## score_brainrot.py — Automatic Brainrot Library Populator

Scores a long source video (1hr+ OrbitalNCG gameplay, etc.) and automatically
extracts the best clips at each duration tier, then registers them in the brainrot
library. Uses combined audio energy + motion density to rank windows; reads the
existing library to prioritise underrepresented tiers.

```bash
# Install signal-extraction deps first
pip install -e ".[score]"

# Download source video (include audio for better scoring)
yt-dlp "https://youtube.com/watch?v=..." -f "bestvideo[ext=mp4]+bestaudio[ext=m4a]" \
  --merge-output-format mp4 -o "~/Downloads/source.mp4"

# For gameplay/no-commentary videos where audio is irrelevant, download video-only
# and pass --no-audio:
yt-dlp "https://youtube.com/watch?v=..." -f "bestvideo[ext=mp4]" -o "~/Downloads/source.mp4"

# Preview what would be extracted (no files written)
python scripts/score_brainrot.py ~/Downloads/source.mp4 \
  --tags "parkour,gameplay" \
  --dry-run

# Full run — slice and register
python scripts/score_brainrot.py ~/Downloads/source.mp4 \
  --tags "parkour,gameplay" \
  --skip-end 90

# Gameplay video with no useful audio
python scripts/score_brainrot.py ~/Downloads/source.mp4 \
  --tags "gameplay" --no-audio
```

**Options:**

| Flag | Default | Description |
|------|---------|-------------|
| `--tags` | — | Comma-separated tags applied to every clip |
| `--skip-end N` | 120 | Seconds to ignore at the end of the video |
| `--quality N` | 50 | Minimum percentile of window scores to accept |
| `--output-name PREFIX` | video stem | Filename prefix for output clips |
| `--no-audio` | — | Ignore audio stream, use motion-only scoring |
| `--dry-run` | — | Print plan, write nothing |

**Duration tiers scored:** 15s, 30s, 45s, 60s, 90s, 2m, 5m.
Tiers shorter than the usable video range are skipped automatically.

## Clip

Transcribes a video, detects natural speech windows, and uses Claude to select the best
moments for vertical short-form content (TikTok / Reels / Shorts).

### How it works

**Step 1 — Transcription (faster-whisper)**

Audio is transcribed via the `faster-whisper` Python library, which returns both
phrase-level segments and word-level timestamps in a single pass. Results are cached
by file hash so re-running the same video skips re-transcription.

- Model auto-selects compute device (`cpu`/`cuda`/`mps`) and runs `int8` quantised
- VAD filtering (`min_silence_duration_ms=500`) suppresses non-speech regions
- Word timing is post-processed: overlaps split at midpoint, micro-gaps (<80ms) closed,
  minimum word duration enforced (100ms)
- Cache keyed by: `sha256(file)[:16]-{model}-v3`

**Step 2 — Window detection**

Word timestamps are walked and split on any pause ≥ 0.8s to produce contiguous
speech windows. Windows shorter than 5s are discarded. If word timestamps are absent
(rare), each phrase segment becomes its own window.

Window text is reconstructed from phrase segments whose **center point** falls inside
the window — this prevents partial-overlap segments at window edges from bleeding into
the wrong window.

**Step 3 — Claude selection**

Claude receives a numbered list of windows with timestamps and text snippets (up to
300 chars per window; windows >60s show start + mid + end). It selects windows by
index, may merge consecutive windows for complete thoughts, and scores each clip 1–10.
Only clips scored 6+ are returned. `max_tokens` scales with window count
(`min(max(2048, windows × 80), 8192)`) to avoid truncated JSON on long videos.

**Step 4 — Timestamp resolution**

Each Claude selection (window index list) is resolved to precise start/end times:

- `start` = first selected window's start time
- `end` = last selected window's end time, then snapped to the nearest
  sentence-boundary that is followed by a real pause (≥ 0.3s). Snapping prefers
  boundaries **at or before** the window end; only snaps forward if within 2s and
  nothing exists before.
- Clips shorter than `--min-duration` are dropped
- Clips exceeding `--max-duration` are trimmed to the nearest sentence/pause boundary
  at the target length, with a 2s grace window before hard-cutting

### Usage

```bash
# YouTube URL or local file — yt-dlp handles download automatically
sable clip process "https://youtube.com/watch?v=..." --account @tig_intern

# Dry run — transcribe and detect windows, print plan, skip Claude + encoding
sable clip process interview.mp4 --account @tig_intern --dry-run

# Cap output duration (clips over 45s are trimmed at a sentence boundary)
sable clip process interview.mp4 --account @tig_intern --max-duration 45

# Target a specific duration range
sable clip process interview.mp4 --account @tig_intern --target-duration 30

# Multiple target tiers (adjusts min/max bounds automatically)
sable clip process interview.mp4 --account @tig_intern --clip-sizes 15,30

# Limit to top 3 clips
sable clip process interview.mp4 --account @tig_intern --num-clips 3

# Use a larger whisper model for better accuracy
sable clip process interview.mp4 --account @tig_intern --whisper-model medium.en
```

### CLI flags

| Flag | Default | Description |
|------|---------|-------------|
| `--account / -a` | required | Account handle e.g. `@tig_intern` |
| `--num-clips / -n` | all worthy | Max clips to produce |
| `--min-duration` | 15s | Drop clips shorter than this |
| `--max-duration` | 45s | Trim clips longer than this at a sentence boundary |
| `--target-duration` | — | Single duration target; sets min/max with ±10s (or ±20% for >30s) tolerance |
| `--clip-sizes` | — | Comma-separated targets e.g. `15,30`; sets min/max from range |
| `--whisper-model` | `base.en` | faster-whisper model name (`base.en`, `small.en`, `medium.en`, etc.) |
| `--dry-run` | — | Transcribe + detect windows, print plan, skip Claude and encoding |
| `--platform` | `twitter` | Output encoding profile (`twitter`, `discord`, `telegram`) |
| `--caption-style` | account default | Override caption style: `word`, `phrase`, `none` |
| `--caption-color` | auto | Caption colour: `white`, `yellow`, `black`, `cyan`, `green`, `red`, `#RRGGBB` |
| `--brainrot-energy` | account default | Override brainrot overlay: `low`, `medium`, `high` |
| `--no-brainrot` | — | Skip brainrot overlay entirely |
| `--image-overlay` | — | PNG to composite in bottom-left (character / logo) |
| `--no-highlight` | — | Disable active-word karaoke highlight on captions |

### Brainrot library

```bash
sable clip brainrot add subway_surfers.mp4 --energy medium --tags parkour
sable clip brainrot list
sable clip brainrot remove subway_surfers.mp4 --delete
sable clip brainrot trace subway_surfers.mp4   # find all clips that used this source
```

## Meme

```bash
sable meme list-templates
sable meme generate --account @tig_intern --template drake --topic "l2 fees"
sable meme generate --account @tig_intern --dry-run  # auto-selects template
sable meme batch --account @tig_intern --count 5 --render
```

## Face

```bash
# Add reference face with consent
sable face library add photo.jpg --name tig --consent

# Swap face
sable face swap target.jpg --account @tig_intern --dry-run
sable face swap viral_clip.mp4 --account @tig_intern --quality medium
```

## Pulse

```bash
# Track performance (--mock for testing without API key)
sable pulse track --account @tig_intern --mock

# View performance report
sable pulse report --account @tig_intern --followers 15000

# Get AI recommendations
sable pulse recommend --account @tig_intern --update-roster

# Per-format lift report (how each format bucket performs relative to account baseline)
sable pulse account @tig_intern --days 30 --org multisynq

# Content attribution: what fraction of engagement came from Sable-produced content?
sable pulse attribution @tig_intern --days 30 --org multisynq

# Search trending content in the niche watchlist
sable pulse trends --org multisynq --format short_clip

# Compute content performance outcomes per content type
sable pulse outcomes --org multisynq --handle @tig_intern

# Export data
sable pulse export --account @tig_intern --format csv --output report.csv
```

## Pulse Meta

Content shape intelligence: which format buckets (threads, clips, images, etc.) are overperforming in your niche right now, and what topics are worth covering.

### One-time setup

```bash
# Set SocialData API key (required for all tweet fetching)
sable config set socialdata_api_key sd_...

# Build a watchlist of 20+ accounts in your niche
sable pulse meta watchlist add @kaito_crypto --niche "crypto research"
sable pulse meta watchlist add @cobie --niche "crypto alpha"
# ...repeat for 20+ accounts
```

### Running analysis

```bash
# Full pipeline: scan + trend analysis + topic signals + Claude recommendations
sable pulse meta --org multisynq

# Scan only (no Claude, cheaper)
sable pulse meta scan --org multisynq --cheap

# Force full 48h rescan (ignore incremental cursors)
sable pulse meta scan --org multisynq --full

# Cost estimate before committing
sable pulse meta scan --org multisynq --dry-run
```

### Watchlist management

```bash
sable pulse meta watchlist list [--org ORG]
sable pulse meta watchlist add @handle [--org ORG] [--niche NICHE]
sable pulse meta watchlist remove @handle [--org ORG]
sable pulse meta watchlist health --org multisynq   # coverage + staleness diagnostics
```

### Output

A three-pane report: **format trends** (8 buckets with lift vs 30d/7d baselines), **topic signals** (what the niche is talking about in high-lift posts), and **recommendations** (what to create, stop doing, or double down on). Results are also saved to `~/.sable-vault/{org}/pulse_meta_report.md`.

See `docs/PULSE_META.md` for full documentation including output interpretation and config tuning.

## Character Explainer

Generates short explainer videos where a famous character explains a user-supplied topic
in their own voice, over brainrot background footage with karaoke subtitles. Supports
landscape (1280×720) and portrait (720×1280) output. Optionally animates the character's
mouth in sync with speech (requires PNG images in the character profile).

**Characters:** `peter_griffin`, `donald_trump`, `ishowspeed`

```bash
# List available characters
sable character-explainer list-characters

# Generate a video (ElevenLabs TTS)
sable character-explainer generate \
  --topic "What is a DAO and why do most of them fail" \
  --character peter_griffin \
  --bg-video ~/.sable/brainrot/minecraft.mp4 \
  --tts-backend elevenlabs \
  --output ~/Desktop/dao_peter.mp4

# With optional markdown context file
sable character-explainer generate \
  --topic "Liquid staking" \
  --character donald_trump \
  --background-md context/lido_overview.md \
  --tts-backend elevenlabs
```

### CLI flags

| Flag | Default | Description |
|------|---------|-------------|
| `--topic` | required | Topic to explain |
| `--character` | required | Character ID (see `list-characters`) |
| `--bg-video` | random clip from `~/.sable/brainrot/` | Brainrot background video; if omitted, a random file is picked and trimmed to the audio length |
| `--output` | `~/sable-workspace/output/@explainer/{slug}/{character}.mp4` | Output path |
| `--background-md` | — | Markdown context file injected into the script prompt |
| `--tts-backend` | character default | `local` (F5-TTS) or `elevenlabs` |
| `--target-duration` | `30` | Target video length in seconds |
| `--orientation` | `landscape` | `landscape` (1280×720) or `portrait` (720×1280) |
| `--platform` | `twitter` | Encoding preset: `twitter`, `youtube`, `discord`, `telegram` |
| `--no-talking-head` | — | Disable mouth animation even if character has PNG images configured |

### TTS backends

- **`local`** — [F5-TTS](https://github.com/SWivid/F5-TTS) zero-shot voice cloning; requires `local_voice_sample_path` (15–25s clean WAV) in the character profile; word timestamps derived via Whisper transcription of output. Install: `pip install f5-tts soundfile torch torchaudio`
- **`elevenlabs`** — fast, high-quality hosted API; requires `ELEVENLABS_API_KEY` env var and a voice ID set in the character's `profile.yaml`

### Adding a character

Create `sable/character_explainer/characters/{id}/profile.yaml`:

```yaml
id: your_character
display_name: Your Character
tts_backend: elevenlabs
elevenlabs_voice_id: "abc123"   # from ElevenLabs dashboard
speaking_speed_modifier: 1.0
explanation_style: >
  How this character explains things...
system_prompt: >
  You are [character]. [detailed in-character instructions]
speech_quirks:
  - "catchphrase one"
```

`speech_quirks` entries are injected into the Claude script-generation prompt; 2–3 are woven into each script naturally.

### Setting up a character voice (local TTS)

If using the `local` TTS backend, you need a reference voice sample and optionally mouth-animation PNGs:

```bash
sable character-explainer setup-voice \
  --character peter_griffin \
  --source "https://www.youtube.com/watch?v=..." \
  --start 10 --end 35          # optional: trim to clean speech segment

# Or from a local file
sable character-explainer setup-voice \
  --character peter_griffin \
  --source ~/Downloads/peter_clip.mp4
```

This downloads/copies the source, extracts a 15–25s audio segment, and saves it to
`~/.sable/voice_samples/{character}.wav`. Optionally, pass `--mouth-open` and `--mouth-closed`
PNG image paths to install mouth animation images and update the character profile automatically.

### Talking head animation

If a character profile defines `image_open_mouth` and `image_closed_mouth` (paths to PNG files with
transparency), the pipeline will animate the character's mouth in sync with speech and composite it
into the lower-left corner of the video. Disable with `--no-talking-head`.

Mouth images should be:
- PNG with alpha channel (RGBA)
- Same dimensions for both open/closed variants
- Stored at `~/.sable/character_images/{character}/mouth_open.png` and `mouth_closed.png`

Currently only `peter_griffin` has mouth images configured.

### Output

Each run produces two files alongside each other:
- `{slug}/{character}.mp4` — the video
- `{slug}/{character}.mp4_meta.json` — metadata (script, word count, TTS backend, topic)

## Vault

Obsidian-compatible markdown vault for content ops. Indexes every clip, meme, and asset produced by other tools into a searchable knowledge base, then surfaces relevant pieces for reply suggestions, topic gap analysis, and client exports.

### Quick start

```bash
# Initialize vault for an org
sable vault init --org multisynq

# Index workspace output into vault
sable vault sync --org multisynq

# Re-run AI enrichment on pending notes
sable vault enrich --org multisynq

# Search for relevant content
sable vault search "liquid staking explainer" --org multisynq

# Log that a piece of content was posted
sable vault log content_abc123 --account @tig_intern --tweet-id 1234567890 --org multisynq
```

### Command reference

| Command | Description |
|---------|-------------|
| `vault init --org ORG [--vault PATH]` | Initialize vault directory structure for org |
| `vault sync --org ORG [--workspace PATH] [--vault PATH] [--dry-run]` | Index workspace content into vault |
| `vault enrich --org ORG [--vault PATH]` | Re-run AI enrichment on pending notes |
| `vault status --org ORG [--vault PATH]` | Show vault inventory summary |
| `vault search QUERY --org ORG [--depth] [--type] [--available-for] [--reply-to] [--format]` | Search by relevance; `--format` filters by format bucket |
| `vault suggest --org ORG [--tweet-text] [--tweet-url] [--account]` | Generate reply suggestions from vault content |
| `vault log [CONTENT_ID] --account --tweet-id --org [--sync-from-pulse] [--bulk CSV]` | Log posted content; `--bulk` accepts a CSV of multiple posts |
| `vault assign CONTENT_ID --account --org [--caption]` | Assign content to account queue |
| `vault niche-gaps --org ORG` | Show topic coverage gaps: topics with niche signal but no vault content |
| `vault export --org ORG [--output] [--include-media]` | Export as client-ready zip |
| `vault topic add SLUG --display-name --org` | Add topic hub page |
| `vault topic list --org ORG` | List topic hubs |
| `vault topic refresh --org ORG` | Refresh topic→content links + FAQ linking |

Vault notes are stored at `~/.sable-vault/{org}/` and are Obsidian-compatible.

## Wojak

Wojak meme compositor. Maintains a local library of wojak PNGs and uses Claude to generate scene specs, which are then rendered into finished meme images.

```bash
# Library management
sable wojak list
sable wojak add https://example.com/wojak.png --id crying_wojak --name "Crying Wojak" \
  --emotion sad --tags "loss,regret" --description "Classic crying face"
sable wojak download-missing   # Download any library images not yet on disk

# Scene generation (Claude writes the spec)
sable wojak scene generate --account @tig_intern --topic "L2 fees going up"

# Render a pre-written YAML spec
sable wojak scene render spec.yaml --account @tig_intern --output ~/Desktop/meme.png
```

`scene generate` calls Claude to produce a YAML scene spec and then renders it. `scene render` takes an existing YAML spec and renders it directly, skipping the Claude call.

## Calendar

Generate a Claude-powered posting schedule that balances format diversity, niche trend alignment, and what's already ready in the vault.

```bash
# 7-day calendar for an account (default)
sable calendar @tig_intern --org multisynq

# Extend the horizon and target more format variety
sable calendar @tig_intern --org multisynq --days 14 --formats-target 5

# Save the output to ~/.sable/playbooks/
sable calendar @tig_intern --org multisynq --save
```

Output example:

```
# @tig_intern — 7-Day Content Calendar
Mon Mar 25 → Sun Mar 31

## Mon Mar 25
  ① standalone_text · "perp funding rate inversion" · CREATE
     Why: standalone_text surging at 2.3x; account hasn't posted text-only in 4 days

## Tue Mar 26
  ① short_clip · "L2 scaling explained" · POST READY → clip-001
     Why: clip in vault assigned to this account, topic aligned with niche signals

---
Summary: 4 formats across 7 days · 3 vault pieces scheduled · 4 new creation tasks
```

Saved calendars land at `~/.sable/playbooks/calendar_{handle}_{date}.md`.

## Workspace

Default output location: `~/sable-workspace/output/@handle/`

Override: `export SABLE_WORKSPACE=/path/to/workspace`

## Environment Variables

| Variable | Required for | Notes |
|----------|-------------|-------|
| `ANTHROPIC_API_KEY` | clip, meme, pulse recommend, pulse meta (analysis), vault suggest/search | Can also be set via `sable config set anthropic_api_key` |
| `REPLICATE_API_TOKEN` | `sable face` | Can also be set via `sable config set replicate_api_key` |
| `SOCIALDATA_API_KEY` | `sable pulse meta`, `sable pulse track`, `sable pulse trends` | Can also be set via `sable config set socialdata_api_key` |
| `ELEVENLABS_API_KEY` | `sable character-explainer` with `--tts-backend elevenlabs` | Read from env only; not stored in config.yaml |
| `SABLE_HOME` | Optional | Override config/DB directory (default: `~/.sable/`). Set to a temp dir for testing |
| `SABLE_WORKSPACE` | Optional | Override output directory (default: `~/sable-workspace/`) |
| `EDITOR` | Optional | Used by `sable roster profile edit` (falls back to `vi`) |

See `docs/ENV_VARS.md` for full details including local dev patterns.
