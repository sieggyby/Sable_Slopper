# Pulse Meta — Content Shape Intelligence

`sable pulse meta` answers the question: **what content formats is our niche actually rewarding right now?**

It fetches tweets from a curated watchlist of accounts, classifies them into 8 format buckets, measures each author's engagement relative to their own baseline, then trends those signals across a 30-day and 7-day window. The output is a three-pane console report plus a vault markdown file with actionable recommendations.

---

## Prerequisites

1. **SOCIALDATA_API_KEY** — all data fetching goes through SocialData. Set via env var or config:
   ```bash
   export SOCIALDATA_API_KEY=your_key
   # or
   sable config set socialdata_api_key your_key
   ```
2. **ANTHROPIC_API_KEY** — needed for the Claude analysis step (skip with `--cheap`).
3. **Watchlist** — at least 20 accounts covering your niche (see setup below).

---

## Watchlist Setup

The watchlist lives at `~/.sable/watchlist.yaml`. It has two scopes:

- **global** — accounts pulled in for every org's analysis
- **orgs** — per-org overrides/additions

### YAML schema

```yaml
global:
  - handle: "@kaito_crypto"
    niche: "crypto alpha / research"
    notes: "high-signal; threads outperform everything"
    added_at: "2026-01-15"

orgs:
  multisynq:
    - handle: "@someone_specific"
      niche: "DePIN / infra"
      notes: ""
      added_at: "2026-03-10"
```

### Managing the watchlist

```bash
# Add an account (global by default)
sable pulse meta watchlist add @handle --niche "defi / yield" --notes "big thread poster"

# Add org-scoped
sable pulse meta watchlist add @handle --org multisynq --niche "DePIN"

# List current watchlist
sable pulse meta watchlist list
sable pulse meta watchlist list --org multisynq   # show global + org-specific

# Remove
sable pulse meta watchlist remove @handle
sable pulse meta watchlist remove @handle --org multisynq

# Run diagnostics (coverage, staleness, diversity)
sable pulse meta watchlist health --org multisynq

# Stats summary
sable pulse meta watchlist stats

# Validate YAML structure
sable pulse meta watchlist validate
```

### Recommended watchlist size

**20+ accounts** for reliable signal. Below ~10, a single viral thread from one account can dominate the trend scores. Aim for variety across:
- Account sizes (micro 5K–50K, mid 50K–500K, large 500K+)
- Content styles (thread writers, hot-takers, educators, meme posters)
- Sub-niches relevant to your client

---

## Running a Scan

The scan fetches tweets for all watchlist accounts via SocialData and stores them in `meta.db`. It uses **incremental cursors** — each author's last-seen tweet ID is stored so re-runs only fetch new tweets.

```bash
# Standard incremental scan + full analysis for org
sable pulse meta scan --org multisynq

# Force full 48h rescan (ignore cursors)
sable pulse meta scan --org multisynq --full

# Include topic keyword searches beyond watchlist
sable pulse meta scan --org multisynq --deep

# Scan only, skip Claude analysis (faster + cheaper)
sable pulse meta scan --org multisynq --cheap

# Estimate API cost before running
sable pulse meta scan --org multisynq --dry-run
```

### Cost control

Each SocialData request costs ~$0.002. The default `max_cost_per_run` cap is **$1.00** — the scan aborts if the estimate exceeds this before making any API calls. To raise the cap:

```yaml
# ~/.sable/config.yaml
pulse_meta:
  max_cost_per_run: 2.50
```

---

## Full Analysis Pipeline

Run the complete pipeline (scan if needed → baselines → trends → topics → Claude → report) with:

```bash
sable pulse meta --org multisynq

# Skip Claude synthesis (trends + topics only)
sable pulse meta --org multisynq --cheap

# Trends pane only, no topic signals or recommendations
sable pulse meta --org multisynq --trends-only

# Include deep topic searches
sable pulse meta --org multisynq --deep

# Dry run — cost estimate, no API calls
sable pulse meta --org multisynq --dry-run
```

The report is also written to `~/.sable-vault/{org}/pulse_meta_report.md`.

---

## Understanding the Output

The report has three panes.

### Pane 1 — Format Trends

Each of the 8 format buckets gets a row showing:

| Column | Meaning |
|--------|---------|
| **Format** | The content type (see buckets below) |
| **Current lift** | This format's weighted-mean engagement vs each author's own baseline. `1.0x` = average for that author; `2.5x` = 2.5× their normal engagement |
| **vs 30d** | Current lift ÷ 30-day stored baseline. The primary trend signal |
| **vs 7d** | Current lift ÷ 7-day baseline. Used for momentum |
| **Status** | Trend label (see below) |
| **Momentum** | Direction of recent change (see below) |
| **Confidence** | A / B / C data quality grade |

#### What "lift" means

Lift is **author-relative** — it normalises away follower count and posting frequency. If a 5K-follower account and a 500K-follower account both post threads and both get 3× their usual replies, that's two independent data points at `3.0x` lift. The system averages across authors weighted by data quality (more history = higher weight).

This means the numbers are not raw engagement; they measure whether a format is working *relative to what's normal for each account*.

#### Format buckets

| Bucket | What it captures |
|--------|-----------------|
| `quote_tweet` | Quote tweets (always classified first regardless of other signals) |
| `thread` | Thread openers (2+ connected tweets) |
| `short_clip` | Video under 60 seconds |
| `long_clip` | Video 60 seconds or longer |
| `single_image` | Image-only posts (no video) |
| `link_share` | Link posts with no other media |
| `standalone_text` | Text-only tweets — no media, no links, not a thread |
| `mixed_media` | Fallback: posts that don't fit the above |

Classification is mutually exclusive and priority-ordered (quote_tweet → thread → clips → images → links → text → mixed).

#### Trend status labels

| Label | What it means |
|-------|--------------|
| `surging` | Current lift ≥ 2.5× the 30-day baseline — breakout format |
| `rising` | Current lift ≥ 1.5× the 30-day baseline — gaining traction |
| `stable` | Current lift is 0.8–1.5× baseline — holding its ground |
| `declining` | Current lift is 0.5–0.8× baseline — losing steam |
| `dead` | Current lift < 0.5× baseline — format has stalled |
| *(blank)* | Quality gates not met — raw lift shown but no label |

Labels require quality gates to pass: minimum 4 tweets in the bucket, 2+ unique authors, and 5+ days of baseline history. Below those thresholds the raw lift is shown without a label.

#### Momentum labels

| Label | What it means |
|-------|--------------|
| `accelerating` | 7-day performance is ≥1.3× the 30-day performance — picking up |
| `plateauing` | 7-day and 30-day are roughly matched (0.85–1.3×) |
| `decelerating` | 7-day is <0.85× the 30-day — trending down recently |

#### Confidence grades

| Grade | Criteria |
|-------|---------|
| A | ≥15 tweets, ≥8 unique authors, not concentrated, not all-fallback |
| B | ≥8 tweets, ≥4 unique authors, or soft concentration/fallback flags |
| C | <8 tweets, single author, or other weak-signal conditions |

"All-fallback" means every contributing author has fewer than 5 tweets in history — their baselines aren't reliable yet, so the grade is capped at B even with large sample counts.

### Pane 2 — Topic Signals

Topics that appear frequently across watchlist accounts in the current scan window, ranked by `unique_authors × avg_lift`. A topic appearing in 8 accounts' high-lift content scores higher than one mentioned 20 times by a single account.

Topics are extracted via:
- `$TICKER` mentions
- Capitalized phrases (2+ words: "Layer 2 Season", "Real Yield")
- Hashtags
- Cross-tweet bigrams/trigrams (e.g. "token unlock", "zk rollup", "airdrop farming")
- Known org tags from your vault

Synonyms defined in vault topic hub frontmatter (`aliases:` field) are merged to canonical names.

### Pane 3 — Recommendations

Claude analyzes the top N tweets (default: 20) alongside the trend and topic data and produces:
- **Do more of** — formats + angles showing strong lift
- **Stop doing / deprioritize** — formats in decline
- **Create next** — specific content ideas with format + topic rationale

Skip this pane with `--cheap` (saves ~$0.05–0.15 per run).

---

## Known Limitations

- **Data cap skew:** SocialData imposes per-account tweet limits. In practice, `--full` scans of active accounts may not reach 48 hours back. Spike periods (a viral thread from a watchlist account) can dominate the bucket sample for that scan. If you run `watchlist health` and see high concentration warnings, consider adding more watchlist accounts in that niche.
- **New orgs need 5+ days before trend labels appear.** The first runs show raw lift only; baselines accumulate over time.
- **`--deep` mode is significantly more expensive** — it runs additional SocialData keyword searches on top of the watchlist account fetches.
- `weighted_median` and `winsorized_mean` aggregation methods are not yet implemented. `weighted_mean` is the only working option.
