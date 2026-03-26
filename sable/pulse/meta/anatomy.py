"""Viral anatomy analysis for high-lift watchlist tweets."""
from __future__ import annotations

import json
import logging

from sable.platform.errors import SableError
from sable.pulse.meta.db import get_unanalyzed_viral_tweets, save_anatomy
from sable.shared.api import call_claude_json

logger = logging.getLogger(__name__)

_ANATOMY_FIELDS = (
    "hook_structure", "hook_length_words", "first_sentence",
    "emotional_register", "topic_cluster", "has_cta", "cta_type",
    "retweet_bait", "retweet_bait_element", "is_thread", "thread_length",
)

_REGISTERS = {"confident", "anxious", "excited", "contemptuous", "neutral", "urgent"}


def analyze_viral_tweet(tweet: dict, org: str) -> dict:
    """Call Claude to produce an anatomy JSON for a single high-lift tweet."""
    prompt = (
        f"Analyze this crypto Twitter post. "
        f"It achieved {tweet['total_lift']:.1f}x its author's average engagement.\n\n"
        f"Post:\n\"{tweet['text']}\"\n\n"
        "Return JSON with these exact fields:\n"
        "- hook_structure: string (structural pattern of the first sentence)\n"
        "- hook_length_words: int\n"
        "- first_sentence: string\n"
        f"- emotional_register: one of {sorted(_REGISTERS)}\n"
        "- topic_cluster: string (1-3 words)\n"
        "- has_cta: bool\n"
        "- cta_type: string or null\n"
        "- retweet_bait: bool\n"
        "- retweet_bait_element: string or null\n"
        "- is_thread: bool\n"
        "- thread_length: int or null"
    )
    raw = call_claude_json(prompt, call_type="anatomy")
    return json.loads(raw)


def run_anatomy_enrichment(
    org: str,
    lift_threshold: float = 10.0,
    limit: int = 20,
) -> int:
    """Analyze unprocessed viral tweets and save anatomy records. Returns count saved."""
    tweets = get_unanalyzed_viral_tweets(org, lift_threshold=lift_threshold, limit=limit)
    saved = 0
    for tweet in tweets:
        try:
            anatomy = analyze_viral_tweet(tweet, org)
            save_anatomy(
                org=org,
                tweet_id=tweet["tweet_id"],
                author_handle=tweet["author_handle"],
                total_lift=tweet["total_lift"],
                format_bucket=tweet["format_bucket"],
                anatomy_json=json.dumps(anatomy),
            )
            saved += 1
        except (SableError, Exception) as exc:
            logger.warning("anatomy: skipping %s — %s", tweet.get("tweet_id"), exc)
    return saved
