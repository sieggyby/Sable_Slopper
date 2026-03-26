"""Viral anatomy analysis for high-lift watchlist tweets."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

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


@dataclass
class ViralAnatomy:
    tweet_id: str
    author_handle: str
    total_lift: float
    format_bucket: str
    text: str
    hook_structure: str
    hook_length_words: int
    first_sentence: str
    emotional_register: str
    topic_cluster: str
    has_cta: bool
    cta_type: str | None
    retweet_bait: bool
    retweet_bait_element: str | None
    is_thread: bool
    thread_length: int | None
    analyzed_at: str


def write_anatomy_vault_note(anatomy: ViralAnatomy, vault_root: Path) -> Path:
    """Write a vault note for a viral anatomy record. Returns the note path."""
    from sable.vault.notes import write_note
    note_dir = vault_root / "content" / "viral_anatomy"
    note_dir.mkdir(parents=True, exist_ok=True)
    path = note_dir / f"{anatomy.tweet_id}.md"
    fm = {
        "id": f"viral_{anatomy.tweet_id}",
        "type": "viral_anatomy",
        "author": f"@{anatomy.author_handle}",
        "format": anatomy.format_bucket,
        "lift": round(anatomy.total_lift, 1),
        "hook_structure": anatomy.hook_structure,
        "topic_cluster": anatomy.topic_cluster,
        "analyzed_at": anatomy.analyzed_at,
    }
    body_lines = [
        anatomy.text,
        "",
        "## Anatomy",
        f"- **Hook structure:** {anatomy.hook_structure}",
        f"- **Hook length:** {anatomy.hook_length_words} words",
        f"- **First sentence:** {anatomy.first_sentence}",
        f"- **Emotional register:** {anatomy.emotional_register}",
        f"- **Topic cluster:** {anatomy.topic_cluster}",
        f"- **Has CTA:** {anatomy.has_cta}" + (f" ({anatomy.cta_type})" if anatomy.cta_type else ""),
        f"- **Retweet bait:** {anatomy.retweet_bait}" + (f" — {anatomy.retweet_bait_element}" if anatomy.retweet_bait_element else ""),
        f"- **Thread:** {anatomy.is_thread}" + (f" ({anatomy.thread_length} posts)" if anatomy.thread_length else ""),
    ]
    write_note(path, fm, "\n".join(body_lines))
    return path


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
    raw = call_claude_json(prompt, org_id=org, call_type="pulse_meta_anatomy")
    return json.loads(raw)


def run_anatomy_enrichment(
    org: str,
    vault_root: Path | None = None,
    max_per_run: int = 10,
    min_lift: float = 10.0,
) -> int:
    """Analyze unprocessed viral tweets, save anatomy records, and write vault notes.

    Returns count saved.
    """
    from sable.shared.paths import vault_dir
    _vault_root = vault_root if vault_root is not None else vault_dir(org)
    tweets = get_unanalyzed_viral_tweets(org, lift_threshold=min_lift, limit=max_per_run)
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
            analyzed_at = datetime.now(timezone.utc).isoformat()
            va = ViralAnatomy(
                tweet_id=tweet["tweet_id"],
                author_handle=tweet["author_handle"],
                total_lift=tweet["total_lift"],
                format_bucket=tweet["format_bucket"],
                text=tweet.get("text", ""),
                analyzed_at=analyzed_at,
                **{k: anatomy.get(k) for k in _ANATOMY_FIELDS},  # type: ignore[arg-type]
            )
            try:
                write_anatomy_vault_note(va, _vault_root)
            except Exception as exc:
                logger.warning("anatomy: vault note failed for %s — %s", tweet["tweet_id"], exc)
            saved += 1
        except (SableError, Exception) as exc:
            logger.warning("anatomy: skipping %s — %s", tweet.get("tweet_id"), exc)
    return saved
