# Config Reference

Config file location: `~/.sable/config.yaml`

All API keys can also be set as environment variables (see `docs/ENV_VARS.md`). Environment variables take precedence.

---

## Top-Level Keys

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `anthropic_api_key` | string | — | Anthropic API key. Override: `ANTHROPIC_API_KEY` env var |
| `replicate_api_key` | string | — | Replicate API token. Override: `REPLICATE_API_TOKEN` env var |
| `socialdata_api_key` | string | — | SocialData API key for tweet fetching. Override: `SOCIALDATA_API_KEY` env var |
| `default_model` | string | `"claude-sonnet-4-6"` | Default Claude model for all features |
| `workspace` | path | `~/sable-workspace` | Root output directory. Override: `SABLE_WORKSPACE` env var |

---

## `pulse_meta` Block

All keys live under `pulse_meta:` in `config.yaml`.

### Scan window

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `lookback_hours` | int | `48` | How many hours of tweets to fetch per account on a full scan |

### Baseline computation

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `baseline_long_days` | int | `30` | Long-window baseline period in days |
| `baseline_short_days` | int | `7` | Short-window baseline period in days |
| `min_baseline_days` | int | `5` | Minimum days of stored baseline data before trend labels are shown. New orgs will show raw lift only until this threshold is reached |

### Quality gates

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `min_samples_for_trend` | int | `4` | Minimum tweets in a format bucket to assign a trend label |
| `min_authors_for_trend` | int | `2` | Minimum unique authors in a bucket to assign a trend label |
| `concentration_threshold` | float | `0.50` | If top 2 authors account for more than this fraction of a bucket's total lift, a concentration warning is shown |

### Trend classification thresholds

These thresholds map `current_lift / 30d_baseline` ratios to trend labels.

| Key | Type | Default | Trend label assigned when lift_vs_30d ≥ this |
|-----|------|---------|---------------------------------------------|
| `surging_threshold` | float | `2.5` | `surging` |
| `rising_threshold` | float | `1.5` | `rising` |
| `declining_threshold` | float | `0.8` | `stable` (below this → declining) |
| `dead_threshold` | float | `0.5` | `declining` (below this → dead) |

Full classification logic:
- `lift_vs_30d >= surging_threshold` → `surging`
- `lift_vs_30d >= rising_threshold` → `rising`
- `lift_vs_30d >= declining_threshold` → `stable`
- `lift_vs_30d >= dead_threshold` → `declining`
- `lift_vs_30d < dead_threshold` → `dead`

### Lift threshold (topic / recommendation filtering)

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `lift_threshold` | float | `1.5` | Minimum lift for a format bucket to be highlighted in recommendations |

### Aggregation

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `aggregation_method` | string | `"weighted_mean"` | How per-tweet lifts are aggregated to a bucket-level score. Only `"weighted_mean"` is currently implemented |

### Claude analysis

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `claude_model` | string | `"claude-sonnet-4-6"` | Claude model used for the synthesis/recommendations step |
| `top_n_for_analysis` | int | `20` | Number of top-lift tweets sent to Claude for analysis |

### Cost control

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `max_cost_per_run` | float | `1.00` | Maximum USD spend per scan. The scanner aborts before making any API calls if the estimated cost exceeds this |

### Engagement weights

```yaml
pulse_meta:
  engagement_weights:
    likes: 1.0
    replies: 12.0
    reposts: 20.0
    quotes: 25.0
    bookmarks: 10.0
    video_views: 6.0
```

These weights control the `total_lift` calculation. Each metric's lift (ratio to author median) is multiplied by its weight, then the weighted mean across metrics is taken.

The defaults reflect a crypto Twitter context where replies and quotes are rare but high-intent signals, while likes are common but low-effort. Tune these for your client's niche:

- Communities where **retweets drive discovery** → raise `reposts`
- Video-heavy niches → raise `video_views`
- Conversation-heavy communities → raise `replies`

---

## `platform` Block

All keys live under `platform:` in `config.yaml`.

```yaml
platform:
  cost_caps:
    max_ai_usd_per_org_per_week: 5.00       # weekly AI spend ceiling per org
    max_ai_usd_per_playbook: 0.15
    max_ai_usd_per_strategy_brief: 0.20
    max_ai_usd_per_vault_sync: 0.00
    max_external_api_calls_per_feedback_loop: 500
    max_retries_per_step: 2
  model_ladder:
    primary: claude-sonnet-4-20250514        # default model for platform AI calls
    fallback: claude-haiku-4-5-20251001      # used when primary budget is tight
    template_only: null                      # no-AI template rendering (future)
  degrade_mode: fallback                     # fallback | skip | error
```

Per-org caps can override `max_ai_usd_per_org_per_week` via `orgs.config_json` in `sable.db`.

---

## Example Annotated config.yaml

```yaml
anthropic_api_key: "sk-ant-..."
socialdata_api_key: "sd_..."
replicate_api_key: "r8_..."
default_model: "claude-sonnet-4-6"
workspace: "~/sable-workspace"

pulse_meta:
  # Scan settings
  lookback_hours: 48
  max_cost_per_run: 2.00       # Raised from $1 default for larger watchlists

  # Baselines
  baseline_long_days: 30
  baseline_short_days: 7
  min_baseline_days: 5

  # Quality gates
  min_samples_for_trend: 4
  min_authors_for_trend: 2
  concentration_threshold: 0.50

  # Trend thresholds (crypto Twitter defaults — aggressive)
  surging_threshold: 2.5
  rising_threshold: 1.5
  declining_threshold: 0.8
  dead_threshold: 0.5
  lift_threshold: 1.5

  # Aggregation
  aggregation_method: "weighted_mean"

  # Claude analysis
  claude_model: "claude-sonnet-4-6"
  top_n_for_analysis: 20

  # Engagement weights (crypto Twitter defaults)
  engagement_weights:
    likes: 1.0
    replies: 12.0
    reposts: 20.0
    quotes: 25.0
    bookmarks: 10.0
    video_views: 6.0
```
