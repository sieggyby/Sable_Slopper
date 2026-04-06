"""Narrative velocity tracker — keyword spread scoring for narrative arcs."""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from sable.lexicon.scanner import MIN_AUTHORS, MIN_TWEETS
from sable.narrative.models import NarrativeBeat, UptakeResult

logger = logging.getLogger(__name__)


def load_beats(org: str, beats_path: Path | None = None) -> list[NarrativeBeat]:
    """Parse narrative_beats.yaml for an org.

    Default path: ~/.sable/{org}/narrative_beats.yaml
    Raises FileNotFoundError if file missing, ValueError if malformed.
    """
    if beats_path is None:
        from sable.shared.paths import sable_home
        beats_path = sable_home() / org / "narrative_beats.yaml"

    if not beats_path.exists():
        raise FileNotFoundError(f"Beats file not found: {beats_path}")

    raw = beats_path.read_text(encoding="utf-8")
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in {beats_path}: {e}") from e

    if not isinstance(data, dict) or "beats" not in data:
        raise ValueError(
            f"Expected top-level 'beats' key in {beats_path}, "
            f"got: {type(data).__name__}"
        )

    beats_list = data["beats"]
    if not isinstance(beats_list, list):
        raise ValueError(f"'beats' must be a list, got: {type(beats_list).__name__}")

    results: list[NarrativeBeat] = []
    for i, entry in enumerate(beats_list):
        if not isinstance(entry, dict):
            raise ValueError(f"Beat #{i} must be a dict, got: {type(entry).__name__}")
        name = entry.get("name")
        keywords = entry.get("keywords")
        if not name or not keywords:
            raise ValueError(f"Beat #{i} missing required 'name' or 'keywords'")
        if not isinstance(keywords, list) or not all(isinstance(k, str) for k in keywords):
            raise ValueError(f"Beat '{name}' keywords must be a list of strings")
        results.append(NarrativeBeat(
            name=str(name),
            keywords=[str(k) for k in keywords],
            started_at=str(entry.get("started_at", "")),
        ))

    return results


def score_uptake(
    beat: NarrativeBeat,
    org: str,
    days: int = 14,
    conn: sqlite3.Connection | None = None,
) -> UptakeResult | None:
    """Score keyword uptake for a single narrative beat.

    Returns None if corpus is below threshold (< MIN_AUTHORS or < MIN_TWEETS).
    """
    if conn is None:
        from sable.pulse.meta.db import get_conn
        conn = get_conn()

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    # Check corpus thresholds
    stats = conn.execute(
        """SELECT COUNT(*) as cnt, COUNT(DISTINCT author_handle) as authors
           FROM scanned_tweets WHERE org = ? AND posted_at >= ?""",
        (org, cutoff),
    ).fetchone()
    total_tweets = stats["cnt"]
    total_authors = stats["authors"]

    if total_authors < MIN_AUTHORS or total_tweets < MIN_TWEETS:
        return None

    # Find tweets matching any keyword (case-insensitive substring)
    rows = conn.execute(
        """SELECT tweet_id, author_handle, text
           FROM scanned_tweets
           WHERE org = ? AND posted_at >= ?""",
        (org, cutoff),
    ).fetchall()

    matching_authors: set[str] = set()
    matching_count = 0
    keywords_hit: set[str] = set()

    for row in rows:
        text_lower = (row["text"] or "").lower()
        hit = False
        for kw in beat.keywords:
            if kw.lower() in text_lower:
                keywords_hit.add(kw.lower())
                hit = True
        if hit:
            matching_authors.add(row["author_handle"])
            matching_count += 1

    unique_authors = len(matching_authors)
    uptake_score = unique_authors / total_authors if total_authors > 0 else 0.0

    # Velocity: authors per day since beat started
    uptake_velocity: float | None = None
    if beat.started_at:
        try:
            start_dt = datetime.fromisoformat(beat.started_at)
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=timezone.utc)
            days_since = (datetime.now(timezone.utc) - start_dt).days
            if unique_authors >= 3 and days_since >= 2:
                uptake_velocity = unique_authors / days_since
        except (ValueError, TypeError):
            logger.warning("Unparseable started_at for beat '%s': %s", beat.name, beat.started_at)

    return UptakeResult(
        beat_name=beat.name,
        unique_authors=unique_authors,
        total_authors=total_authors,
        uptake_score=uptake_score,
        uptake_velocity=uptake_velocity,
        matching_tweets=matching_count,
        keywords_matched=sorted(keywords_hit),
    )
