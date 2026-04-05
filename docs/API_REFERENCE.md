# Sable Slopper API Reference

`sable serve` exposes a read-only FastAPI backend. No Claude calls, no cost.

**Base URL:** `http://<host>:8000` (default uvicorn port)

**Authentication:** All endpoints except `/health` require a Bearer token.

```
Authorization: Bearer <SLOPPER_TOKEN>
```

Token is configured in `~/.sable/config.yaml`. Supports two layouts:

```yaml
# Legacy single token
serve:
  token: "your-token"

# Named tokens (preferred — provides audit trail)
serve:
  tokens:
    sableweb: "token-for-web"
    debug: "token-for-dev"
```

Named tokens are checked first; legacy `serve.token` is a fallback. All tokens are HMAC-compared (constant-time). The authenticated client name is logged on every request.

---

## Health

### `GET /health`

No authentication required.

**Response:**
```json
{
  "status": "ok",
  "checks": {
    "pulse_db": true,
    "meta_db": true,
    "vault": true
  }
}
```

**Field notes:**
- `status`: `"ok"` when all checks pass, `"degraded"` when any check fails
- `checks.pulse_db`: pulse.db exists and is readable (read-only `SELECT 1`)
- `checks.meta_db`: meta.db exists and is readable (read-only `SELECT 1`)
- `checks.vault`: vault directory exists
- Always returns HTTP 200 — consumers decide how to act on `degraded`

---

## Pulse

### `GET /api/pulse/performance/{org}`

Content performance data for an org over a time window.

**Path params:**
- `org` (string, required) — Org slug

**Query params:**
- `days` (int, default: 30, range: 1–365) — Lookback window in days

**Response:**
```json
{
  "total_posts": 42,
  "sable_posts": 18,
  "organic_posts": 24,
  "sable_share_of_engagement": 0.65,
  "sable_avg_engagement": 152.3,
  "organic_avg_engagement": 87.1,
  "sable_lift_vs_organic": 1.75,
  "top_performing_formats": [
    {
      "format": "clip",
      "count": 8,
      "total_engagement": 1200,
      "avg_engagement": 150.0
    }
  ],
  "by_format": [ /* same shape as top_performing_formats */ ],
  "weekly_trend": [
    {
      "week": "2026W12",
      "sable_engagement": 450,
      "organic_engagement": 300,
      "sable_share": 0.6
    }
  ],
  "meta_informed": {
    "meta_informed_posts": 10,
    "meta_informed_avg": 175.0,
    "non_meta_avg": 120.0,
    "meta_lift": 1.46
  }
}
```

**Error (no accounts):**
```json
{"error": "No accounts found for org", "org": "example"}
```

---

### `GET /api/pulse/posting-log/{org}`

Raw posting log with latest snapshot metrics.

**Path params:**
- `org` (string, required) — Org slug

**Query params:**
- `days` (int, default: 30, range: 1–365) — Lookback window in days

**Response:**
```json
[
  {
    "id": "1234567890",
    "url": "https://twitter.com/user/status/1234567890",
    "text": "Post text...",
    "posted_at": "2026-03-15 14:30:00",
    "sable_content_type": "clip",
    "likes": 45,
    "retweets": 12,
    "replies": 8,
    "views": 3200,
    "bookmarks": 5,
    "quotes": 2
  }
]
```

Returns `[]` if no accounts found for org.

---

## Meta

### `GET /api/meta/topics/{org}`

Top topic signals from the most recent successful scan.

**Path params:**
- `org` (string, required) — Org slug

**Query params:**
- `limit` (int, default: 20, range: 1–100)

**Response:**
```json
[
  {
    "topic": "restaking",
    "momentum_score": 0.8,
    "confidence": "high",
    "trend_status": "rising",
    "avg_lift": 4.2,
    "unique_authors": 8,
    "mention_count": 15
  }
]
```

Returns `[]` if no scan data exists.

**Field notes:**
- `momentum_score`: 0–1, derived from avg_lift (capped at lift/5)
- `confidence`: "high" (10+ mentions), "medium" (5–9), "low" (<5)
- `trend_status`: "rising" (accel > 1.5), "declining" (accel < 0.5), "stable"

---

### `GET /api/meta/baselines/{org}`

Format baseline data — lift per format bucket from latest computation window.

**Path params:**
- `org` (string, required) — Org slug

**Response:**
```json
[
  {
    "format": "hot_take",
    "signal": "DOUBLE_DOWN",
    "avg_lift": 2.1,
    "sample_count": 25,
    "unique_authors": 12,
    "rationale": "hot_take at 2.10x lift (25 samples, 12 authors)"
  }
]
```

**Signal values:**
- `DOUBLE_DOWN` — avg_lift >= 1.5
- `EXECUTION_GAP` — avg_lift < 0.7
- `PERFORMING` — between 0.7 and 1.5

Falls back from 30d to 7d baselines if no 30d data exists.

---

### `GET /api/meta/watchlist/{org}`

Watchlist health diagnostics — coverage, staleness, scan history.

**Path params:**
- `org` (string, required) — Org slug

**Response:**
```json
{
  "total_authors": 45,
  "stale_authors": 3,
  "last_scan": "2026-03-28 10:15:00",
  "coverage": 0.93,
  "total_scans": 12
}
```

**Field notes:**
- `stale_authors`: authors with `last_seen` > 14 days ago
- `coverage`: `(total - stale) / total`

---

## Vault

### `GET /api/vault/inventory/{org}`

Vault content inventory — produced, posted, unused, by-format breakdown.

**Path params:**
- `org` (string, required) — Org slug

**Response:**
```json
{
  "total_produced": 85,
  "total_posted": 42,
  "total_unused": 43,
  "stale_threshold_days": 14,
  "by_format": [
    {
      "format": "clip",
      "produced": 30,
      "posted": 18,
      "unused": 12
    }
  ],
  "unused_assets": [
    {
      "title": "What is restaking?",
      "format": "clip",
      "produced_at": "2026-03-10T14:00:00",
      "age_days": 18
    }
  ],
  "recent_posted": [
    {
      "title": "DeFi explained",
      "format": "clip",
      "produced_at": "2026-03-25T10:00:00",
      "posted_at": "2026-03-26 12:00:00",
      "performance": {"engagement": 245}
    }
  ]
}
```

**Field notes:**
- `unused_assets` sorted by age descending, capped at 50
- `recent_posted` capped at 20
- Posted detection: checks both `sable_content_path` in pulse.db and `posted_by` frontmatter

**Error:**
```json
{"error": "Invalid org", "org": "example"}
```

---

### `GET /api/vault/search/{org}`

Search vault content notes by keyword matching.

**Path params:**
- `org` (string, required) — Org slug

**Query params:**
- `q` (string, required, min_length: 1) — Search query (space-separated keywords)
- `limit` (int, default: 10, range: 1–50)

**Response:**
```json
[
  {
    "title": "What is a DAO",
    "path": "/path/to/vault/content/dao_explainer.md",
    "score": 3,
    "format": "clip",
    "frontmatter": {
      "topic": "What is a DAO",
      "type": "clip",
      "keywords": ["dao", "governance"]
    }
  }
]
```

Returns `[]` if no matches or invalid org.

**Field notes:**
- `score`: count of query tokens found in searchable fields
- Searched fields: topic, caption, keywords, questions_answered, script_preview, depth, tone
- No Claude call — pure keyword match (read-only API, no spend)

---

## SableWeb Integration

SableWeb needs these environment variables to connect:
- `SLOPPER_URL` — Base URL of the sable serve instance (e.g., `https://slopper.example.com`)
- `SLOPPER_TOKEN` — Bearer token matching `serve.token` in sable's config

SableWeb sections powered by this API:
- **Content performance** → `/api/pulse/performance/{org}`
- **Format intelligence** → `/api/meta/baselines/{org}`
- **Topic signals** → `/api/meta/topics/{org}`
- **Content pipeline / vault** → `/api/vault/inventory/{org}`
