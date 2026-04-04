"""Data models for narrative velocity tracking."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class NarrativeBeat:
    """A single narrative beat (keyword cluster) to track uptake for."""
    name: str
    keywords: list[str]
    started_at: str = ""  # ISO date, optional


@dataclass
class UptakeResult:
    """Uptake measurement for a single narrative beat."""
    beat_name: str
    unique_authors: int
    total_authors: int
    uptake_score: float      # unique_authors / total_authors
    uptake_velocity: float   # unique_authors / days_since_start (0 if no start date)
    matching_tweets: int
    keywords_matched: list[str] = field(default_factory=list)
