# Sable Slopper — Schema Inventory

> Research artifact. No implementation planned. Describes every defined schema in the codebase as of 2026-03-22.

---

## Overview

The codebase has **three SQLite databases**, **22 Python data models** (dataclasses + Pydantic), **one YAML config schema**, **one YAML watchlist schema**, **one markdown frontmatter schema** (vault notes), and **one YAML character profile schema**.

No formal ORM, no Pydantic-backed database layer. `pulse.db` and `meta.db` use hand-written SQL + dataclasses with no migration runner. `sable.db` uses `sable db migrate` (`sable/db/migrations/001_initial.sql`) via `ensure_schema()`.

---

## 1. SQLite Databases

### pulse.db — `~/.sable/pulse.db`
**Defined in:** `sable/pulse/db.py`
Content performance tracking and posting log.

| Table | Purpose |
|-------|---------|
| `posts` | One row per piece of posted content |
| `snapshots` | Time-series engagement metrics per post |
| `account_stats` | Follower/following counts over time |
| `recommendations` | Stored AI-generated recommendations |
| `schema_version` | Single-row version tracker |

#### posts
```sql
id TEXT PRIMARY KEY,
account_handle TEXT NOT NULL,
platform TEXT DEFAULT 'twitter',
url TEXT,
text TEXT,
posted_at TEXT,
sable_content_type TEXT,   -- 'clip' | 'meme' | 'faceswap' | 'text' | 'unknown'
sable_content_path TEXT,
created_at TEXT DEFAULT (datetime('now'))
```

#### snapshots
```sql
id INTEGER PRIMARY KEY AUTOINCREMENT,
post_id TEXT NOT NULL REFERENCES posts(id),
taken_at TEXT DEFAULT (datetime('now')),
likes INTEGER DEFAULT 0,
retweets INTEGER DEFAULT 0,
replies INTEGER DEFAULT 0,
views INTEGER DEFAULT 0,
bookmarks INTEGER DEFAULT 0,
quotes INTEGER DEFAULT 0
```
Indexes: `idx_posts_account`, `idx_snapshots_post`, `idx_snapshots_taken`

#### account_stats
```sql
id INTEGER PRIMARY KEY AUTOINCREMENT,
account_handle TEXT NOT NULL,
taken_at TEXT DEFAULT (datetime('now')),
followers INTEGER DEFAULT 0,
following INTEGER DEFAULT 0,
tweet_count INTEGER DEFAULT 0
```

#### recommendations
```sql
id INTEGER PRIMARY KEY AUTOINCREMENT,
account_handle TEXT NOT NULL,
generated_at TEXT DEFAULT (datetime('now')),
content TEXT,
applied INTEGER DEFAULT 0
```

---

### meta.db — `~/.sable/pulse/meta.db`
**Defined in:** `sable/pulse/meta/db.py`
Watchlist tweet cache and format-trend intelligence.

| Table | Purpose |
|-------|---------|
| `scanned_tweets` | Raw + enriched tweets from watchlist accounts |
| `author_profiles` | Per-author scan state (cursor, tweet count) |
| `scan_runs` | Audit log of each `sable pulse meta scan` run |
| `format_baselines` | 7d/30d aggregate lift per format bucket per org |
| `topic_signals` | Top terms extracted from high-lift tweets per scan |
| `schema_version` | Single-row version tracker |

#### scanned_tweets (the big one)
```sql
tweet_id TEXT PRIMARY KEY,
author_handle TEXT NOT NULL,
text TEXT,
posted_at TEXT,
format_bucket TEXT,           -- one of 8 FORMAT_BUCKETS
attributes_json TEXT,         -- JSON list of attribute strings
-- raw engagement
likes, replies, reposts, quotes, bookmarks, video_views INTEGER,
video_duration INTEGER,
-- structural flags
is_quote_tweet, is_thread, has_image, has_video, has_link INTEGER,
thread_length INTEGER DEFAULT 1,
-- author context
author_followers INTEGER,
author_median_likes, _replies, _reposts, _quotes, _total REAL,
author_median_same_format REAL,
-- computed lift scores
likes_lift, replies_lift, reposts_lift, quotes_lift REAL,
total_lift REAL,
format_lift REAL,             -- lift vs author's own median for this format bucket
-- quality grading
author_quality_grade TEXT,    -- 'A' | 'B' | 'C'
author_quality_weight REAL,
format_lift_reliable INTEGER DEFAULT 0,
-- lineage
scan_id INTEGER,
org TEXT
```
Indexes: `author`, `org`, `format_bucket`, `scan_id`

#### scan_runs
```sql
id INTEGER PRIMARY KEY AUTOINCREMENT,
org TEXT NOT NULL,
started_at, completed_at TEXT,
mode TEXT,
tweets_collected, tweets_new INTEGER,
estimated_cost REAL,
watchlist_size INTEGER,
claude_raw TEXT    -- raw Claude response blob
```

#### format_baselines
```sql
id, org TEXT, format_bucket TEXT,
period_days INTEGER,       -- 7 or 30
avg_total_lift REAL,
sample_count, unique_authors INTEGER,
computed_at TEXT
```

#### topic_signals
```sql
id, org TEXT, scan_id INTEGER,
term TEXT,
mention_count, unique_authors INTEGER,
avg_lift REAL,
prev_scan_mentions INTEGER,
acceleration REAL DEFAULT 0.0
```

---

## 2. Python Data Models

### Roster — `sable/roster/models.py`
Pydantic BaseModel. Serialized to `~/.sable/roster.yaml`.

| Class | Fields |
|-------|--------|
| `Platform` | handle, platform, url? |
| `Persona` | archetype, voice, topics[], avoid[] |
| `ContentSettings` | clip_style, meme_style, caption_style, brainrot_energy, hashtags[], watermark? |
| `Account` | handle, display_name, org, platforms[], persona, content, tweet_bank[], learned_preferences{}, active, created_at?, updated_at? |
| `Roster` | version (int), accounts[] |

`Account` is the primary entity representing a managed Twitter handle. `org` is a plain string (no separate Org table or model — org is just a grouping key used across pulse meta and vault).

---

### Vault — `sable/vault/`

#### VaultConfig — `config.py` (dataclass)
| Field | Type | Default |
|-------|------|---------|
| vault_base_path | str | `~/.sable-vault` |
| claude_model | str | claude-opus-... |
| auto_enrich | bool | True |
| enrich_batch_size | int | 10 |
| min_relevance_score | int | 6 |
| max_suggestions | int | 5 |
| draft_temperature | float | 0.7 |
| include_media_in_export | bool | False |

#### SearchFilters — `search.py` (dataclass)
```
depth: Optional[str]           # 'shallow' | 'deep'
content_type: Optional[str]    # 'clip' | 'meme' | 'faceswap' | 'explainer'
format: Optional[str]          # format bucket name
available_for: Optional[str]   # account handle filter
reply_context: Optional[str]   # tweet text being replied to
```

#### SearchResult — `search.py` (dataclass)
```
id: str         # content_id
score: int      # 1-10 Claude relevance score
reason: str     # Claude's explanation
note: dict      # the raw frontmatter dict of the matched vault note
```

#### SyncReport — `sync.py` (dataclass)
```
new: int
updated: int
errors: list[str]
```

#### ReplySuggestion — `suggest.py` (dataclass)
```
content_id: str
content_title: str
content_type: str
content_path: str
account: str
relevance_score: int
relevance_reason: str
reply_draft: str
```

---

### Vault Note Frontmatter Schema
**Defined implicitly in:** `sable/vault/notes.py`, `sable/vault/sync.py`
Vault notes are Obsidian-compatible `.md` files. YAML frontmatter fields:

**Core (all note types):**
```yaml
id: str                    # unique content ID (slug)
type: str                  # 'clip' | 'meme' | 'faceswap' | 'explainer'
source_tool: str           # which sable command created it
account: str               # @handle
output: str                # path to the media file
assembled_at: str          # ISO timestamp
meta_path: str             # path to the *_meta.json source

topics: [str]              # AI-assigned topic tags
questions_answered: [str]  # AI-extracted Q&A hooks
depth: str                 # 'shallow' | 'medium' | 'deep'
tone: str                  # 'educational' | 'humorous' | etc.
keywords: [str]
enrichment_status: str     # 'pending' | 'done' | 'failed'

suggested_for: [str]       # account handles this has been suggested to
posted_by: [str]           # account handles that have posted it
```

**Type-specific fields:**
```yaml
# clip
source: str       # source video URL or path
start, end: float # timestamps
duration: float
caption: str
brainrot_energy: str

# meme
template: str
topic: str
texts: [str]

# faceswap
target: str
strategy: str

# explainer
topic: str
character_id: str
script_preview: str
```

---

### Pulse Meta Models — `sable/pulse/meta/`

#### AuthorQuality — `normalize.py` (dataclass)
```
grade: str          # 'A' | 'B' | 'C'
total_tweets: int
total_scans: int
reasons: list[str]
weight: float       # 1.0 (A), 0.7 (B), 0.3 (C)
```

#### AuthorNormalizedTweet — `normalize.py` (dataclass)
The in-memory representation of a tweet after lift computation. Mirrors most of the `scanned_tweets` SQL row plus an embedded `AuthorQuality` object.

#### EngagementQuality — `quality.py` (dataclass)
```
confidence: str          # 'A' | 'B' | 'C'
confidence_reasons: list[str]
sample_count: int
unique_authors: int
concentration: float     # top-author share of data
all_fallback: bool
mixed_quality_warning: str
```

#### TrendResult — `trends.py` (dataclass)
```
format_bucket: str
current_lift: float
lift_vs_30d: Optional[float]
lift_vs_7d: Optional[float]
trend_status: Optional[str]   # 'surging' | 'rising' | 'stable' | 'declining' | 'dead'
momentum: Optional[str]
confidence: str
confidence_reasons: list[str]
quality: EngagementQuality    # embedded
reasons: list[str]
gate_failures: list[str]
```

#### TopicSignal — `topics.py` (dataclass)
```
term: str
mention_count: int
unique_authors: int
avg_lift: float
prev_scan_mentions: int
acceleration: float
```

#### PostNowRecommendation — `recommender.py` (dataclass)
```
content_id: str
title: str
file_path: str
account: str
format_bucket: str
archetype: str
priority_score: float
confidence: str
reason: str
urgency: str     # 'now' | 'this-week' | 'whenever'
effort: str
shelf_life: str
```

#### FORMAT_BUCKETS — `fingerprint.py` (frozenset constant)
The 8 canonical format buckets used throughout:
`quote_tweet`, `thread`, `short_clip`, `long_clip`, `single_image`, `link_share`, `standalone_text`, `mixed_media`

---

### Character Explainer — `sable/character_explainer/`

#### CharacterProfile — `config.py` (dataclass)
```
id, display_name: str
system_prompt, explanation_style: str
speech_quirks: list[str]
tts_backend: str                    # 'local' | 'elevenlabs'
local_voice_sample_path: Optional[str]
elevenlabs_voice_id: Optional[str]
speaking_speed_modifier: float
image_closed_mouth, image_open_mouth, image_blink: Optional[str]
thumbnail_photo_path: Optional[str]
phonetic_corrections: dict          # word → pronunciation override
```
Loaded from `sable/character_explainer/characters/{id}/profile.yaml`.

#### ExplainerConfig — `config.py` (dataclass)
Runtime pipeline config (not serialized): target duration, word count bounds, Claude model, FFmpeg settings, orientation, platform preset.

#### ExplainerScript — `script.py` (dataclass)
```
character_id, topic, full_text: str
word_count: int
estimated_duration_s: float
```

#### TTSResult — `tts/base.py` (dataclass)
```
audio_path: str
word_timestamps: list[dict]   # each: {start, end, text}
duration_s: float
```

---

### Global Config — `sable/config.py`
YAML at `~/.sable/config.yaml`. Key namespaces:

```yaml
anthropic_api_key, replicate_api_key, socialdata_api_key: str
default_model: str
workspace: str

pulse_meta:
  lookback_hours: int
  baseline_long_days, baseline_short_days: int
  min_baseline_days, min_samples_for_trend, min_authors_for_trend: int
  concentration_threshold: float
  surging_threshold, rising_threshold, declining_threshold, dead_threshold: float
  lift_threshold: float
  aggregation_method: str
  max_cost_per_run: float
  claude_model: str
  top_n_for_analysis: int
  engagement_weights:
    likes, replies, reposts, quotes, bookmarks, video_views: float
```

---

### Watchlist — `sable/pulse/meta/watchlist.py`
YAML at `~/.sable/watchlist.yaml`. No Python model class — read/written as raw dicts.

```yaml
global:
  - handle: str
    niche: str
    notes: str
    added_at: str    # ISO timestamp
orgs:
  {org_name}:
    - handle, niche, notes, added_at
```

---

---

### sable.db — `~/.sable/sable.db`
**Defined in:** `sable/db/migrations/001_initial.sql` + `sable/platform/db.py`

| Table              | Purpose                                              |
|--------------------|------------------------------------------------------|
| `schema_version`   | Single-row version tracker (currently 3, after migrations 001–003) |
| `orgs`             | Registered client orgs (org_id, display_name, config)|
| `entities`         | Known community members per org                      |
| `entity_handles`   | Platform handles per entity (twitter, discord, etc.) |
| `entity_tags`      | Tags with replace-current vs append-history semantics|
| `entity_notes`     | Free-text notes per entity                           |
| `merge_candidates` | Potential duplicate entity pairs + confidence scores |
| `merge_events`     | Audit log of completed merges                        |
| `content_items`    | Content pieces linked to entities                    |
| `diagnostic_runs`  | Audit log of cult-doctor / health-check runs (extended by migration 003) |
| `jobs`             | Top-level job records per org                        |
| `job_steps`        | Individual steps per job with retry tracking         |
| `artifacts`        | Output files/blobs produced by jobs                  |
| `cost_events`      | Per-call AI/API cost tracking                        |
| `sync_runs`        | Audit log of platform sync operations (extended by migration 002) |

#### sync_runs (migration 002 adds columns, schema_version → 3)
```sql
sync_id               INTEGER PRIMARY KEY AUTOINCREMENT
org_id                TEXT REFERENCES orgs
sync_type             TEXT  -- 'cult_doctor' | 'sable_tracking' | ...
status                TEXT  -- 'running' | 'completed' | 'failed'
started_at            TEXT  -- datetime
completed_at          TEXT  -- datetime (nullable)
records_synced        INTEGER  -- entities_created + tags_added
error                 TEXT  -- nullable
-- added by migration 002:
cult_run_id           TEXT  -- nullable; FK to Cult Grader run_id
entities_created      INTEGER DEFAULT 0
entities_updated      INTEGER DEFAULT 0
handles_added         INTEGER DEFAULT 0
tags_added            INTEGER DEFAULT 0
tags_replaced         INTEGER DEFAULT 0
merge_candidates_created INTEGER DEFAULT 0
```
Indexes: `idx_sync_org`, `idx_sync_cult_run_id`

#### diagnostic_runs (migration 003 adds columns, schema_version → 3)
```sql
run_id               INTEGER PRIMARY KEY AUTOINCREMENT
org_id               TEXT REFERENCES orgs
run_type             TEXT  -- 'cult_doctor' | ...
status               TEXT  -- 'running' | 'completed' | 'failed'
started_at           TEXT  -- datetime
completed_at         TEXT  -- datetime (nullable)
result_json          TEXT  -- nullable
error                TEXT  -- nullable
-- added by migration 003:
cult_run_id          TEXT UNIQUE  -- nullable; Cult Grader run_meta.run_id
project_slug         TEXT  -- nullable
run_date             TEXT  -- YYYY-MM-DD
research_mode        TEXT  -- 'training' | 'web'
checkpoint_path      TEXT  -- absolute path to run dir
overall_grade        TEXT  -- A–F
fit_score            INTEGER  -- 1–10
recommended_action   TEXT  -- 'pursue' | 'monitor' | 'pass'
sable_verdict        TEXT  -- nullable
total_cost_usd       REAL  -- nullable
```
Indexes: `idx_diagnostic_org`, `idx_diagnostic_cult_run_id` (UNIQUE), `idx_diagnostic_slug`

---

## 3. Notable Gaps (remaining)

- **No `ContentItem` model.** Vault notes are raw dicts read from markdown frontmatter; there's no typed Python class wrapping them.
- **No shared DB connection factory for pulse/meta.** Each module (pulse, meta) opens its own sqlite3 connection directly. `sable/platform/db.py` provides `get_db()` for `sable.db` only.

Previously listed gaps that are now filled:
- ~~No `Org` model or table~~ → `orgs` table in `sable.db`
- ~~No `Job`, `DiagnosticRun`, or `Artifact` model~~ → `jobs`, `job_steps`, `diagnostic_runs`, `artifacts` tables
- ~~No schema migrations~~ → `sable db migrate` + `sable/db/migrations/001_initial.sql`
