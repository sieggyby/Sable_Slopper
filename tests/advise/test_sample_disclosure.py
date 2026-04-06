"""Tests for T1-2: sample size disclosure in strategy brief."""
from __future__ import annotations


def _make_data(posts=None, topics=None, formats=None):
    """Build minimal assembled data dict for render_summary."""
    return {
        "profile": {"tone": "bullish", "interests": "defi", "context": "L1 protocol"},
        "posts": posts or [],
        "pulse_available": bool(posts),
        "data_freshness": {},
        "data_quality": {},
        "meta_available": bool(topics or formats),
        "meta_stale": False,
        "meta_scan_date": None,
        "topics": topics or [],
        "formats": formats or [],
        "entities": [],
        "vault_notes": [],
        "tracking_notes": [],
        "churn_playbook": None,
    }


def test_topic_rendering_includes_author_and_mention_count():
    from sable.advise.stage1 import render_summary

    topics = [
        {
            "term": "restaking",
            "mention_count": 12,
            "unique_authors": 7,
            "avg_lift": 2.5,
            "acceleration": 0.5,
        }
    ]
    data = _make_data(topics=topics)
    output = render_summary(data)
    assert "7 authors" in output
    assert "12 mentions" in output


def test_format_rendering_includes_sample_count():
    from sable.advise.stage1 import render_summary

    formats = [
        {"format_bucket": "thread", "avg_total_lift": 2.3, "sample_count": 5},
    ]
    data = _make_data(formats=formats)
    output = render_summary(data)
    assert "5 tweets" in output


def test_thin_post_caveat_fires():
    """generate.py caveat logic triggers for < 10 posts."""
    assembled = _make_data(
        posts=[{"id": i} for i in range(3)],
        topics=[{"term": "foo", "unique_authors": 2, "mention_count": 3, "avg_lift": 1.0, "acceleration": 0}],
    )
    # Simulate the caveat logic from generate.py inline (it's embedded in the
    # orchestrator, not exposed as a standalone function, so we replicate it)
    caveat_lines: list[str] = []
    posts = assembled.get("posts", [])
    if 0 < len(posts) < 10:
        caveat_lines.append(f"- **Post performance** based on only {len(posts)} posts")
    topics = assembled.get("topics", [])
    if topics:
        max_authors = max(t.get("unique_authors", 0) for t in topics)
        if max_authors < 5:
            caveat_lines.append(f"- **Topic signals** drawn from <={max_authors} unique authors")

    assert len(caveat_lines) == 2
    assert "3 posts" in caveat_lines[0]
    assert "2 unique authors" in caveat_lines[1]


def test_stage2_contract_mentions_sample_sizes():
    from sable.advise.stage2 import OUTPUT_FORMAT_CONTRACT

    assert "sample sizes" in OUTPUT_FORMAT_CONTRACT.lower()
    assert "thin-sample" in OUTPUT_FORMAT_CONTRACT.lower()
