"""SocialData tweet fetching with incremental cursors and dry-run support."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional

from sable.shared.handles import strip_handle, normalize_handle
from sable.shared.socialdata import socialdata_get_async, BalanceExhaustedError

_COST_PER_REQUEST = 0.002  # rough estimate per API call

_CORE_ENGAGEMENT_KEYS = ("favorite_count", "retweet_count", "reply_count")


def _safe_int(val, default: int = 0) -> int:
    """Coerce a value to int, returning default on failure."""
    try:
        return int(val)
    except (TypeError, ValueError):
        return default




def _normalise_tweet(raw: dict, author_handle: str) -> Optional[dict]:
    """Normalise a raw SocialData tweet into our internal format.

    Returns None if the tweet is malformed (missing id, unparseable date,
    or no core engagement fields present).
    """
    user = raw.get("user", {})
    tweet_id = str(raw.get("id_str") or raw.get("id") or "")
    if not tweet_id:
        return None

    text = raw.get("full_text") or raw.get("text") or ""

    # Parse created_at
    created_at = raw.get("created_at", "")
    posted_at = _parse_twitter_date(created_at)
    if posted_at is None:
        return None

    # Validate engagement fields: at least one core counter must be present,
    # and every present core counter must be coercible to int.  A provider
    # drift that drops or retypes a single field should not silently zero-fill.
    if not any(k in raw for k in _CORE_ENGAGEMENT_KEYS):
        return None
    for k in _CORE_ENGAGEMENT_KEYS:
        if k in raw:
            try:
                int(raw[k])
            except (TypeError, ValueError):
                return None

    # Media detection
    extended = raw.get("extended_entities") or raw.get("entities") or {}
    media_list = extended.get("media", [])
    has_video = any(m.get("type") in ("video", "animated_gif") for m in media_list)
    has_image = any(m.get("type") == "photo" for m in media_list) and not has_video

    # Video duration
    video_duration = None
    for m in media_list:
        video_info = m.get("video_info", {})
        duration_ms = video_info.get("duration_millis")
        if duration_ms:
            video_duration = int(duration_ms / 1000)
            break

    # Link detection (URLs that aren't media)
    urls = (raw.get("entities") or {}).get("urls", [])
    has_link = bool(urls) and not has_video and not has_image

    # Quote/thread detection
    is_quote = bool(raw.get("is_quote_status", False))
    in_reply = bool(raw.get("in_reply_to_screen_name"))
    # Treat as thread if replying to same user
    is_thread = in_reply and raw.get("in_reply_to_screen_name", "").lower() == normalize_handle(author_handle)

    return {
        "tweet_id": tweet_id,
        "author_handle": author_handle if author_handle.startswith("@") else f"@{author_handle}",
        "text": text,
        "posted_at": posted_at,
        "urls": urls,  # AR5-16: raw URL list for has_link recomputation in classify_format
        "likes": _safe_int(raw.get("favorite_count", 0)),
        "replies": _safe_int(raw.get("reply_count", 0)),
        "reposts": _safe_int(raw.get("retweet_count", 0)),
        "quotes": _safe_int(raw.get("quote_count", 0)),
        "bookmarks": _safe_int(raw.get("bookmark_count", 0)),
        "video_views": _safe_int(raw.get("views_count", 0)),
        "video_duration": video_duration,
        "is_quote_tweet": is_quote,
        "is_thread": is_thread,
        "thread_length": 1,
        "has_image": has_image,
        "has_video": has_video,
        "has_link": has_link,
        "author_followers": _safe_int(user.get("followers_count", 0)),
    }


def _parse_twitter_date(date_str: str) -> Optional[str]:
    """Parse Twitter date format to ISO8601. Returns None on parse failure."""
    if not date_str:
        return None
    # Twitter format: "Thu Mar 17 12:00:00 +0000 2026"
    try:
        dt = datetime.strptime(date_str, "%a %b %d %H:%M:%S +0000 %Y")
        return dt.replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        pass
    # Try ISO format
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00")).isoformat()
    except ValueError:
        console_warn(f"Could not parse Twitter date: {date_str!r}")
        return None


async def _fetch_author_tweets_async(
    handle: str,
    since_id: Optional[str] = None,
    limit: int = 100,
    lookback_hours: int = 48,
) -> list[dict]:
    """Fetch tweets for one author, optionally since a last tweet ID."""
    handle_clean = strip_handle(handle)
    params: dict = {"type": "tweets", "limit": min(limit, 100)}

    data = await socialdata_get_async(
        f"/twitter/user/{handle_clean}/tweets", params=params,
    )

    raw_tweets = data.get("tweets", data.get("data", []))

    # Filter to incremental range if since_id given
    if since_id and raw_tweets:
        raw_tweets = [t for t in raw_tweets
                      if str(t.get("id_str") or t.get("id") or "") > since_id]

    # Filter to lookback window
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=lookback_hours)).isoformat()
    filtered = []
    for t in raw_tweets:
        posted_at = _parse_twitter_date(t.get("created_at", ""))
        if posted_at is None:  # AR5-19: skip tweets with unparseable dates
            continue
        if posted_at >= cutoff:
            filtered.append(t)

    return filtered


async def _search_tweets_async(query: str, limit: int = 50) -> list[dict]:
    """Search tweets by keyword (deep mode)."""
    data = await socialdata_get_async(
        "/twitter/search",
        params={"query": query, "type": "Latest", "limit": limit},
    )
    return data.get("tweets", data.get("data", []))


class Scanner:
    """Incremental scanner: fetches tweets, classifies them, stores normalized results."""

    def __init__(
        self,
        org: str,
        watchlist: list[dict],
        db,
        cfg_meta: dict | None = None,
        deep: bool = False,
        full: bool = False,
        dry_run: bool = False,
        max_cost: float = float("inf"),
    ):
        self.org = org
        self.watchlist = watchlist
        self.db = db
        self.meta_cfg = cfg_meta or {}
        self.deep = deep
        self.full = full
        self.dry_run = dry_run
        self.max_cost = max_cost
        self.lookback_hours = self.meta_cfg.get("lookback_hours", 48)
        self._estimated_cost: float = 0.0  # P2: track for partial failure reporting
        self._tweets_new: int = 0          # P2: track for partial failure reporting
        self._failed_authors: list[str] = []  # AR5-8: track failed author fetches

    def estimate_cost(self) -> dict:
        """Estimate cost without making API calls."""
        n_accounts = len(self.watchlist)
        # ~1 request per account + deep overhead
        n_requests = n_accounts + (10 if self.deep else 0)
        est_cost = n_requests * _COST_PER_REQUEST
        return {
            "accounts": n_accounts,
            "estimated_requests": n_requests,
            "estimated_cost_usd": est_cost,
        }

    def run(self, scan_id: int) -> dict:
        """Run the full scan. Returns summary dict."""
        if self.dry_run:
            return {**self.estimate_cost(), "dry_run": True, "tweets_new": 0, "tweets_collected": 0}

        return asyncio.run(self._run_async(scan_id))

    async def _run_async(self, scan_id: int) -> dict:
        tweets_collected = 0
        tweets_new = 0
        estimated_cost = 0.0
        aborted = False

        from sable.pulse.meta.fingerprint import classify_tweet
        from sable.pulse.meta.normalize import compute_author_lift

        # Process each watchlist account
        for entry in self.watchlist:
            handle = entry.get("handle", "")
            if not handle:
                continue

            # Get last seen tweet ID for incremental scan
            since_id = None
            if not self.full:
                profile = self.db.get_author_profile(handle, self.org)
                if profile:
                    since_id = profile.get("last_tweet_id")

            try:
                raw_tweets = await _fetch_author_tweets_async(
                    handle,
                    since_id=since_id,
                    lookback_hours=self.lookback_hours,
                )
                estimated_cost += _COST_PER_REQUEST
                self._estimated_cost += _COST_PER_REQUEST
            except BalanceExhaustedError:
                raise  # 402 is fatal — propagate immediately
            except Exception as e:
                console_warn(f"Failed to fetch {handle}: {e}")
                self._failed_authors.append(handle)  # AR5-8
                continue

            if estimated_cost > self.max_cost:
                aborted = True
                break

            if not raw_tweets:
                continue

            # Normalise + classify
            normalised_raw = [_normalise_tweet(t, handle) for t in raw_tweets]
            normalised = [t for t in normalised_raw if t is not None]
            skipped = len(normalised_raw) - len(normalised)
            if skipped:
                console_warn(f"Skipped {skipped} malformed tweet(s) for {handle}")

            # Build author history from DB for normalization
            author_history = self.db.get_author_tweets(handle, self.org, limit=100)

            for tweet in normalised:
                tweets_collected += 1

                # Classify format + attributes
                bucket, attrs = classify_tweet(tweet)
                tweet["format_bucket"] = bucket
                tweet["attributes"] = attrs
                tweet["org"] = self.org
                tweet["scan_id"] = scan_id

                # Compute author-relative normalization
                normalized = compute_author_lift(tweet, author_history)

                # Merge lift fields back into tweet dict
                tweet.update({
                    "author_median_likes": normalized.author_median_likes,
                    "author_median_replies": normalized.author_median_replies,
                    "author_median_reposts": normalized.author_median_reposts,
                    "author_median_quotes": normalized.author_median_quotes,
                    "author_median_total": normalized.author_median_total,
                    "author_median_same_format": normalized.author_median_same_format,
                    "likes_lift": normalized.likes_lift,
                    "replies_lift": normalized.replies_lift,
                    "reposts_lift": normalized.reposts_lift,
                    "quotes_lift": normalized.quotes_lift,
                    "total_lift": normalized.total_lift,
                    "format_lift": normalized.format_lift,
                    "format_lift_reliable": normalized.format_lift_reliable,
                    "author_quality_grade": normalized.author_quality.grade,
                    "author_quality_weight": normalized.author_quality.weight,
                })

                is_new = self.db.upsert_tweet(tweet)
                if is_new:
                    tweets_new += 1
                    self._tweets_new += 1  # P2
                    author_history.append(tweet)  # use new tweet in subsequent normalizations

            # Update author profile cursor (AR5-9: use integer comparison, not string max)
            if normalised:
                valid_ids = [int(t["tweet_id"]) for t in normalised
                             if t.get("tweet_id") and str(t["tweet_id"]).isdigit()]
                latest_id = str(max(valid_ids)) if valid_ids else None
                if latest_id:
                    self.db.upsert_author_profile(
                        author_handle=handle,
                        org=self.org,
                        last_tweet_id=latest_id,
                        tweet_count=len(normalised),
                        last_seen=datetime.now(timezone.utc).isoformat(),
                    )

        # Deep mode: search by topic keywords
        outsider_results: dict[str, list] = {}
        if not aborted and self.deep:
            # Build query from top topics (placeholder: use common crypto terms)
            queries = ["crypto", "defi", "blockchain"]
            watchlist_handles = {normalize_handle(e.get("handle", "")) for e in self.watchlist}

            for query in queries[:3]:  # why: cap at 3 queries to limit deep-mode API spend
                try:
                    raw = await _search_tweets_async(query, limit=30)
                    estimated_cost += _COST_PER_REQUEST
                    if estimated_cost > self.max_cost:
                        aborted = True
                        break

                    # Filter out watchlist accounts — these are "outsiders"
                    outsiders = [
                        t for t in raw
                        if t.get("user", {}).get("screen_name", "").lower() not in watchlist_handles
                    ]

                    from sable.pulse.meta.fingerprint import classify_tweet as ct
                    for raw_tweet in outsiders:
                        user = raw_tweet.get("user", {})
                        handle = f"@{user.get('screen_name', 'unknown')}"
                        maybe_tweet = _normalise_tweet(raw_tweet, handle)
                        if maybe_tweet is None:
                            continue
                        tweet = maybe_tweet
                        bucket, attrs = ct(tweet)
                        tweet["format_bucket"] = bucket
                        tweet["attributes"] = attrs
                        outsider_results.setdefault(bucket, []).append(tweet)

                except BalanceExhaustedError:
                    raise  # 402 is fatal — propagate immediately
                except Exception as e:
                    console_warn(f"Deep mode query '{query}' failed: {e}")

        return {
            "tweets_collected": tweets_collected,
            "tweets_new": tweets_new,
            "estimated_cost": estimated_cost,
            "outsider_results": outsider_results,
            "failed_authors": self._failed_authors,  # AR5-8
            "dry_run": False,
            "aborted": aborted,
        }


def console_warn(msg: str) -> None:
    """Print a warning to stderr without importing rich everywhere."""
    import sys
    print(f"[WARN] {msg}", file=sys.stderr)
