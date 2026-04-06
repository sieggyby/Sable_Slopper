"""Tests for sable.narrative.tracker — keyword spread scoring."""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import yaml

from sable.pulse.meta.db import _SCHEMA
from sable.narrative.models import NarrativeBeat
from sable.narrative.tracker import load_beats, score_uptake

_NOW = datetime.now(timezone.utc)


def _ts(days_ago: int = 0) -> str:
    return (_NOW - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M:%S")


def _make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def _insert_tweet(conn, org, author, text, days_ago=0):
    tid = str(uuid.uuid4())[:12]
    conn.execute(
        """INSERT INTO scanned_tweets
           (tweet_id, org, author_handle, posted_at, text, likes, replies, reposts, quotes, bookmarks)
           VALUES (?, ?, ?, ?, ?, 10, 5, 3, 1, 0)""",
        (tid, org, author, _ts(days_ago), text),
    )
    conn.commit()


def _seed_corpus(conn, org="test_org", n_authors=15, tweets_per_author=5):
    """Seed a corpus that meets thresholds with some keyword-bearing tweets."""
    for i in range(n_authors):
        author = f"@author_{i:03d}"
        for j in range(tweets_per_author):
            if i < 5 and j == 0:
                text = "Excited about Real Yield and our staking narrative"
            elif i < 8 and j == 0:
                text = "The zkrollup tech is changing everything"
            else:
                text = "Another day building in crypto"
            _insert_tweet(conn, org, author, text, days_ago=j)


# ---------------------------------------------------------------------------
# load_beats
# ---------------------------------------------------------------------------

def test_load_beats_valid(tmp_path):
    """Valid YAML with beats is parsed correctly."""
    beats_file = tmp_path / "narrative_beats.yaml"
    beats_file.write_text(yaml.dump({
        "beats": [
            {"name": "real_yield", "keywords": ["real yield", "staking"], "started_at": "2026-01-01"},
            {"name": "zk_tech", "keywords": ["zkrollup", "zk proof"]},
        ]
    }), encoding="utf-8")

    beats = load_beats("org", beats_path=beats_file)
    assert len(beats) == 2
    assert beats[0].name == "real_yield"
    assert beats[0].keywords == ["real yield", "staking"]
    assert beats[0].started_at == "2026-01-01"
    assert beats[1].started_at == ""


def test_load_beats_missing_file(tmp_path):
    """Missing file raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        load_beats("org", beats_path=tmp_path / "nope.yaml")


def test_load_beats_malformed_yaml(tmp_path):
    """Invalid YAML raises ValueError."""
    beats_file = tmp_path / "bad.yaml"
    beats_file.write_text("beats:\n  - name: foo\n    keywords: {bad", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid YAML"):
        load_beats("org", beats_path=beats_file)


def test_load_beats_missing_top_key(tmp_path):
    """YAML without 'beats' key raises ValueError."""
    beats_file = tmp_path / "nokey.yaml"
    beats_file.write_text(yaml.dump({"tracks": []}), encoding="utf-8")

    with pytest.raises(ValueError, match="beats"):
        load_beats("org", beats_path=beats_file)


def test_load_beats_missing_name(tmp_path):
    """Beat without name raises ValueError."""
    beats_file = tmp_path / "noname.yaml"
    beats_file.write_text(yaml.dump({
        "beats": [{"keywords": ["foo"]}]
    }), encoding="utf-8")

    with pytest.raises(ValueError, match="name"):
        load_beats("org", beats_path=beats_file)


def test_load_beats_invalid_keywords(tmp_path):
    """Beat with non-list keywords raises ValueError."""
    beats_file = tmp_path / "badkw.yaml"
    beats_file.write_text(yaml.dump({
        "beats": [{"name": "foo", "keywords": "single_string"}]
    }), encoding="utf-8")

    with pytest.raises(ValueError, match="list of strings"):
        load_beats("org", beats_path=beats_file)


# ---------------------------------------------------------------------------
# score_uptake
# ---------------------------------------------------------------------------

def test_uptake_basic():
    """Known authors/tweets produce expected uptake score."""
    conn = _make_conn()
    _seed_corpus(conn)

    beat = NarrativeBeat(name="real_yield", keywords=["real yield", "staking"])
    result = score_uptake(beat, "test_org", days=14, conn=conn)

    assert result is not None
    assert result.beat_name == "real_yield"
    # 5 authors mention "real yield" or "staking"
    assert result.unique_authors == 5
    assert result.total_authors == 15
    assert result.uptake_score == pytest.approx(5 / 15, rel=1e-3)
    assert result.matching_tweets == 5


def test_uptake_case_insensitive():
    """Keyword matching is case-insensitive."""
    conn = _make_conn()
    _seed_corpus(conn)

    beat = NarrativeBeat(name="zk", keywords=["ZKROLLUP"])
    result = score_uptake(beat, "test_org", days=14, conn=conn)

    assert result is not None
    assert result.unique_authors == 3  # authors 5-7


def test_uptake_no_matches():
    """Beat with no matching keywords returns zero uptake."""
    conn = _make_conn()
    _seed_corpus(conn)

    beat = NarrativeBeat(name="missing", keywords=["nonexistent_term_xyz"])
    result = score_uptake(beat, "test_org", days=14, conn=conn)

    assert result is not None
    assert result.unique_authors == 0
    assert result.uptake_score == 0.0
    assert result.matching_tweets == 0


def test_uptake_below_author_threshold():
    """Fewer than MIN_AUTHORS returns None."""
    conn = _make_conn()
    for i in range(5):
        for j in range(12):
            _insert_tweet(conn, "org", f"@a{i}", "test", days_ago=j % 7)

    beat = NarrativeBeat(name="test", keywords=["test"])
    result = score_uptake(beat, "org", days=14, conn=conn)
    assert result is None


def test_uptake_below_tweet_threshold():
    """Fewer than MIN_TWEETS returns None."""
    conn = _make_conn()
    for i in range(12):
        for j in range(2):
            _insert_tweet(conn, "org", f"@a{i}", "test", days_ago=j)

    beat = NarrativeBeat(name="test", keywords=["test"])
    result = score_uptake(beat, "org", days=14, conn=conn)
    assert result is None


def test_uptake_velocity_with_start_date():
    """Velocity is calculated when started_at is provided."""
    conn = _make_conn()
    _seed_corpus(conn)

    start = (_NOW - timedelta(days=10)).strftime("%Y-%m-%d")
    beat = NarrativeBeat(name="real_yield", keywords=["real yield"], started_at=start)
    result = score_uptake(beat, "test_org", days=14, conn=conn)

    assert result is not None
    assert result.uptake_velocity > 0
    assert result.uptake_velocity == pytest.approx(5 / 10, rel=0.2)


def test_uptake_velocity_no_start_date():
    """Velocity is None when no started_at."""
    conn = _make_conn()
    _seed_corpus(conn)

    beat = NarrativeBeat(name="real_yield", keywords=["real yield"])
    result = score_uptake(beat, "test_org", days=14, conn=conn)

    assert result is not None
    assert result.uptake_velocity is None


def test_uptake_velocity_thin_sample_returns_none():
    """T3-9: Velocity None when unique_authors < 3 or days_since < 2."""
    conn = _make_conn()
    # Seed 15 authors but only 1 mentions "rare_term"
    for i in range(15):
        for j in range(5):
            if i == 0 and j == 0:
                text = "discussing rare_term today"
            else:
                text = "Generic content"
            _insert_tweet(conn, "test_org", f"@author_{i:03d}", text, days_ago=j)

    start = (_NOW - timedelta(days=10)).strftime("%Y-%m-%d")
    beat = NarrativeBeat(name="rare", keywords=["rare_term"], started_at=start)
    result = score_uptake(beat, "test_org", days=14, conn=conn)

    assert result is not None
    assert result.unique_authors == 1  # < 3, so velocity should be None
    assert result.uptake_velocity is None


def test_keywords_matched_tracking():
    """keywords_matched reports which keywords were actually found."""
    conn = _make_conn()
    _seed_corpus(conn)

    beat = NarrativeBeat(name="mixed", keywords=["real yield", "zkrollup", "nonexistent"])
    result = score_uptake(beat, "test_org", days=14, conn=conn)

    assert result is not None
    assert "real yield" in result.keywords_matched
    assert "zkrollup" in result.keywords_matched
    assert "nonexistent" not in result.keywords_matched
