"""Tests for pulse content performance outcomes sync."""
from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy import create_engine

from sable_platform.db.compat_conn import CompatConnection
from sable_platform.db.schema import metadata as sa_metadata


def _make_conn(org_id="psy", org_name="PSY Protocol"):
    """Create an in-memory CompatConnection with full sable.db schema."""
    engine = create_engine("sqlite:///:memory:")
    sa_metadata.create_all(engine)
    sa_conn = engine.connect()
    conn = CompatConnection(sa_conn)
    conn.execute(
        "INSERT INTO orgs (org_id, display_name) VALUES (?, ?)",
        (org_id, org_name),
    )
    conn.commit()
    return conn


def _make_posts():
    """Return sample posts grouped by content type."""
    return [
        {"id": "1", "sable_content_type": "clip", "text": "clip1", "posted_at": "2026-04-01"},
        {"id": "2", "sable_content_type": "clip", "text": "clip2", "posted_at": "2026-04-02"},
        {"id": "3", "sable_content_type": "meme", "text": "meme1", "posted_at": "2026-04-01"},
        {"id": "4", "sable_content_type": "text", "text": "text1", "posted_at": "2026-04-03"},
    ]


def _make_snapshot(post_id, likes=10, retweets=5, replies=3, quotes=2, views=1000):
    return {
        "post_id": post_id,
        "likes": likes,
        "retweets": retweets,
        "replies": replies,
        "quotes": quotes,
        "views": views,
        "bookmarks": 0,
    }


SNAPSHOTS = {
    "1": _make_snapshot("1", likes=10, retweets=5, replies=3, quotes=2, views=1000),
    "2": _make_snapshot("2", likes=20, retweets=10, replies=5, quotes=3, views=2000),
    "3": _make_snapshot("3", likes=50, retweets=20, replies=10, quotes=5, views=5000),
    "4": _make_snapshot("4", likes=5, retweets=2, replies=1, quotes=0, views=500),
}


def test_sync_creates_outcomes_per_type():
    """One outcome per content type + one aggregate."""
    conn = _make_conn()

    with patch("sable.pulse.db.get_posts_for_account", return_value=_make_posts()), \
         patch("sable.pulse.db.get_latest_snapshot", side_effect=lambda pid: SNAPSHOTS.get(pid, {})):
        from sable.pulse.outcomes import sync_content_outcomes
        count = sync_content_outcomes("psy", "@test", conn=conn)

    # 3 types (clip, meme, text) + 1 aggregate = 4
    assert count == 4

    rows = conn.execute("SELECT * FROM outcomes ORDER BY metric_name").fetchall()
    names = [r["metric_name"] for r in rows]
    assert "engagement_rate_clip" in names
    assert "engagement_rate_meme" in names
    assert "engagement_rate_text" in names
    assert "engagement_rate_overall" in names

    # Verify clip engagement: post1=(10+5+3+2)/1000=0.02, post2=(20+10+5+3)/2000=0.019 → avg=0.0195
    clip_row = [r for r in rows if r["metric_name"] == "engagement_rate_clip"][0]
    assert abs(clip_row["metric_after"] - 0.0195) < 0.001


def test_sync_no_posts_returns_zero():
    """No posts → zero outcomes, no crash."""
    conn = _make_conn()

    with patch("sable.pulse.db.get_posts_for_account", return_value=[]):
        from sable.pulse.outcomes import sync_content_outcomes
        count = sync_content_outcomes("psy", "@test", conn=conn)

    assert count == 0


def test_sync_no_snapshots_returns_zero():
    """Posts with no snapshots → zero outcomes."""
    conn = _make_conn()

    with patch("sable.pulse.db.get_posts_for_account", return_value=_make_posts()), \
         patch("sable.pulse.db.get_latest_snapshot", return_value={}):
        from sable.pulse.outcomes import sync_content_outcomes
        count = sync_content_outcomes("psy", "@test", conn=conn)

    assert count == 0


def test_sync_zero_views_no_division_error():
    """Posts with 0 views → engagement calculated without division error."""
    conn = _make_conn()

    posts = [{"id": "1", "sable_content_type": "text", "text": "t", "posted_at": "2026-04-01"}]
    snap = _make_snapshot("1", likes=5, retweets=0, replies=0, quotes=0, views=0)

    with patch("sable.pulse.db.get_posts_for_account", return_value=posts), \
         patch("sable.pulse.db.get_latest_snapshot", return_value=snap):
        from sable.pulse.outcomes import sync_content_outcomes
        count = sync_content_outcomes("psy", "@test", conn=conn)

    assert count == 2  # 1 type + 1 aggregate
    row = conn.execute(
        "SELECT metric_after FROM outcomes WHERE metric_name='engagement_rate_text'"
    ).fetchone()
    # (5+0+0+0)/max(0,1) = 5.0
    assert row["metric_after"] == 5.0


def test_sync_delta_from_prior_outcome():
    """Second sync picks up prior metric_after as metric_before."""
    conn = _make_conn()

    posts = [{"id": "1", "sable_content_type": "text", "text": "t", "posted_at": "2026-04-01"}]
    snap = _make_snapshot("1", likes=10, views=1000)

    with patch("sable.pulse.db.get_posts_for_account", return_value=posts), \
         patch("sable.pulse.db.get_latest_snapshot", return_value=snap):
        from sable.pulse.outcomes import sync_content_outcomes
        sync_content_outcomes("psy", "@test", conn=conn)

    # Second run with higher engagement
    snap2 = _make_snapshot("1", likes=20, views=1000)
    with patch("sable.pulse.db.get_posts_for_account", return_value=posts), \
         patch("sable.pulse.db.get_latest_snapshot", return_value=snap2):
        from sable.pulse.outcomes import sync_content_outcomes
        sync_content_outcomes("psy", "@test", conn=conn)

    rows = conn.execute(
        "SELECT * FROM outcomes WHERE metric_name='engagement_rate_text'"
    ).fetchall()
    assert len(rows) == 2  # one from each run

    # The second-run outcome should have metric_before set
    with_before = [r for r in rows if r["metric_before"] is not None]
    assert len(with_before) == 1, "Second run should populate metric_before"
    assert with_before[0]["metric_after"] > with_before[0]["metric_before"]


def test_sync_data_json_contains_handle():
    """data_json includes handle and content type info."""
    conn = _make_conn()

    posts = [{"id": "1", "sable_content_type": "meme", "text": "m", "posted_at": "2026-04-01"}]
    snap = _make_snapshot("1")

    with patch("sable.pulse.db.get_posts_for_account", return_value=posts), \
         patch("sable.pulse.db.get_latest_snapshot", return_value=snap):
        from sable.pulse.outcomes import sync_content_outcomes
        sync_content_outcomes("psy", "@test", conn=conn)

    row = conn.execute(
        "SELECT data_json FROM outcomes WHERE metric_name='engagement_rate_meme'"
    ).fetchone()
    data = json.loads(row["data_json"])
    assert data["handle"] == "@test"
    assert data["content_type"] == "meme"
    assert data["post_count"] == 1


def test_sync_recorded_by():
    """All outcomes have recorded_by='pulse_outcomes'."""
    conn = _make_conn()

    posts = [{"id": "1", "sable_content_type": "text", "text": "t", "posted_at": "2026-04-01"}]
    snap = _make_snapshot("1")

    with patch("sable.pulse.db.get_posts_for_account", return_value=posts), \
         patch("sable.pulse.db.get_latest_snapshot", return_value=snap):
        from sable.pulse.outcomes import sync_content_outcomes
        sync_content_outcomes("psy", "@test", conn=conn)

    rows = conn.execute("SELECT recorded_by FROM outcomes").fetchall()
    assert all(r["recorded_by"] == "pulse_outcomes" for r in rows)


def test_cli_outcomes_smoke():
    """CLI pulse outcomes command invokes sync_content_outcomes."""
    from click.testing import CliRunner
    from sable.pulse.cli import pulse_outcomes

    with patch("sable.pulse.outcomes.sync_content_outcomes", return_value=3) as mock_sync:
        runner = CliRunner()
        result = runner.invoke(pulse_outcomes, ["--org", "psy", "--handle", "@test"])

    assert result.exit_code == 0
    assert "3 outcome record(s)" in result.output
    mock_sync.assert_called_once_with(org_id="psy", handle="@test")
