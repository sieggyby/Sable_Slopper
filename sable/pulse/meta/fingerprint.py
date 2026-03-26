"""8-bucket format classifier + layered attribute detection."""
from __future__ import annotations

import re

# The complete set of valid format buckets.
# Every return from classify_format() must be in this set.
FORMAT_BUCKETS = frozenset({
    "quote_tweet",
    "thread",
    "short_clip",
    "long_clip",
    "single_image",
    "link_share",
    "standalone_text",
    "mixed_media",
})


def classify_format(
    is_quote_tweet: bool = False,
    is_thread: bool = False,
    thread_length: int = 1,
    has_video: bool = False,
    video_duration: int | None = None,
    has_image: bool = False,
    has_link: bool = False,
    urls: list | None = None,
) -> str:
    """Classify a tweet into exactly one of 8 format buckets.

    Priority order (highest to lowest):
    1. quote_tweet — is_quote_tweet takes precedence over everything
    2. thread      — is_thread with length >= 2
    3. short_clip  — video under 60s
    4. long_clip   — video 60s or more
    5. single_image — image, no video
    6. link_share  — link only
    7. standalone_text — no media/links/thread
    8. mixed_media — fallback
    """
    duration = video_duration if video_duration is not None else 0

    # AR5-16: compute has_link from raw urls if provided (avoids pre-filter issue)
    if urls is not None:
        has_link = bool(urls) and not has_video and not has_image

    if is_quote_tweet:
        bucket = "quote_tweet"
    elif is_thread and thread_length >= 2:
        bucket = "thread"
    elif has_video and duration < 60 and not is_quote_tweet:
        bucket = "short_clip"
    elif has_video and duration >= 60 and not is_quote_tweet:
        bucket = "long_clip"
    elif has_image and not has_video and not is_quote_tweet and not is_thread:
        bucket = "single_image"
    elif has_link and not is_quote_tweet and not is_thread:
        bucket = "link_share"
    elif not has_video and not has_image and not has_link and not is_thread and not is_quote_tweet:
        bucket = "standalone_text"
    else:
        bucket = "mixed_media"

    # Invariant assertion: returned bucket must always be in FORMAT_BUCKETS
    assert bucket in FORMAT_BUCKETS, f"classify_format produced invalid bucket: {bucket!r}"
    return bucket


# ---------------------------------------------------------------------------
# Layered attribute detection
# ---------------------------------------------------------------------------

# Tone patterns
_CONFRONTATIONAL = re.compile(
    r"\b(wrong|lol|cope|embarrassing|ridiculous|stupid|dumb|they don|no one|"
    r"actually|debunked|false|lie|lies|misinformation|hot take|unpopular opinion)\b",
    re.IGNORECASE,
)
_EXPLANATORY = re.compile(
    r"\b(here's why|let me explain|thread|breakdown|deep dive|tldr|in other words|"
    r"what this means|how it works|explained|a quick|step by step)\b",
    re.IGNORECASE,
)
_MEME_HUMOR = re.compile(
    r"\b(lmao|lmfao|kek|based|ngmi|gm|gn|wen|ser|fren|anon|wagmi|cope|seethe|"
    r"vibes|ngl|ngl|unironically|ironically|brainrot)\b|"
    r"(?:😂|💀|🤣|😭|🫡|🐸|💊|🔴|🟢)",
    re.IGNORECASE,
)
_TECHNICAL = re.compile(
    r"\b(protocol|smart contract|zk|zkp|evm|calldata|merkle|consensus|sequencer|"
    r"validator|slashing|liquidity|tvl|apr|apy|yield|leverage|margin|perpetual|"
    r"orderbook|amm|dex|cex|bridge|cross.chain|layer 2|l2|rollup|shard|proof of)\b",
    re.IGNORECASE,
)
_ANNOUNCEMENT = re.compile(
    r"\b(announcing|launched|live|mainnet|testnet|introducing|release|v\d|"
    r"partnership|integrat|milestone|update|upgrade|new feature)\b",
    re.IGNORECASE,
)
_HYPE = re.compile(
    r"\b(massive|huge|incredible|insane|bullish|mooning|aping|degen|"
    r"alpha|signal|gem|100x|next big|to the moon|lfg|let's go|banger)\b",
    re.IGNORECASE,
)


def detect_attributes(
    text: str,
    is_quote_tweet: bool = False,
    has_image: bool = False,
    has_video: bool = False,
) -> list[str]:
    """Detect zero or more layered attributes for a tweet."""
    attrs: list[str] = []

    # Tone
    if _CONFRONTATIONAL.search(text):
        attrs.append("confrontational")
    if _EXPLANATORY.search(text):
        attrs.append("explanatory")
    if _MEME_HUMOR.search(text):
        attrs.append("meme_humor")
    if _TECHNICAL.search(text):
        attrs.append("technical")
    if _ANNOUNCEMENT.search(text):
        attrs.append("announcement")
    if _HYPE.search(text):
        attrs.append("hype")

    # Structure
    if is_quote_tweet:
        attrs.append("reactive")
    else:
        attrs.append("original")

    # Media
    if has_image or has_video:
        # has_face: heuristic — can't detect without vision; skip for MVP
        # has_caption_hook: first line of text is short bold caption
        lines = text.strip().split("\n")
        if lines and len(lines[0]) < 80 and lines[0].isupper():
            attrs.append("has_caption_hook")

    # Short text
    if len(text.strip()) < 100:
        attrs.append("short_text")

    return list(dict.fromkeys(attrs))  # deduplicate, preserve order


def classify_tweet(tweet: dict) -> tuple[str, list[str]]:
    """Convenience: classify format + detect attributes from a raw tweet dict.

    Returns (format_bucket, attributes).
    """
    bucket = classify_format(
        is_quote_tweet=tweet.get("is_quote_tweet", False),
        is_thread=tweet.get("is_thread", False),
        thread_length=tweet.get("thread_length", 1),
        has_video=tweet.get("has_video", False),
        video_duration=tweet.get("video_duration"),
        has_image=tweet.get("has_image", False),
        has_link=tweet.get("has_link", False),
        urls=tweet.get("urls"),  # AR5-16: pass raw urls for has_link recomputation
    )
    attrs = detect_attributes(
        text=tweet.get("text", ""),
        is_quote_tweet=tweet.get("is_quote_tweet", False),
        has_image=tweet.get("has_image", False),
        has_video=tweet.get("has_video", False),
    )
    return bucket, attrs
