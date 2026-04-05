"""Tests for TrackingMetadata contract validation (SS-20)."""
from __future__ import annotations

import logging

import pytest


VALID_META = {
    "schema_version": 1,
    "source_tool": "sable_tracking",
    "url": "https://twitter.com/user/status/123",
    "canonical_author_handle": "@testuser",
    "quality_score": 7.5,
    "audience_annotation": "core",
    "timing_annotation": "peak",
    "grok_status": "success",
    "engagement_score": 85.0,
    "lexicon_adoption": 0.6,
    "emotional_valence": "positive",
    "subsquad_signal": "strong",
    "format_type": "thread",
    "intent_type": "educational",
    "topic_tags": ["defi", "restaking"],
    "review_status": "reviewed",
    "outcome_type": "follower_gain",
    "is_reusable_template": True,
}


def test_validate_tracking_meta_valid():
    """Valid metadata passes validation and returns typed fields."""
    from sable.advise.stage1 import _validate_tracking_meta

    result = _validate_tracking_meta(VALID_META)
    assert result.source_tool == "sable_tracking"
    assert result.quality_score == 7.5
    assert result.format_type == "thread"
    assert result.is_reusable_template is True
    assert result.topic_tags == ["defi", "restaking"]


def test_validate_tracking_meta_minimal():
    """Minimal metadata (just source_tool) passes — all others default."""
    from sable.advise.stage1 import _validate_tracking_meta

    result = _validate_tracking_meta({"source_tool": "sable_tracking"})
    assert result.source_tool == "sable_tracking"
    assert result.quality_score is None
    assert result.format_type is None
    assert result.is_reusable_template is False


def test_validate_tracking_meta_unknown_schema_version_warns(caplog):
    """Unknown schema_version logs warning but still returns data."""
    from sable.advise.stage1 import _validate_tracking_meta

    meta = {**VALID_META, "schema_version": 99}
    with caplog.at_level(logging.WARNING):
        result = _validate_tracking_meta(meta)
    assert result.source_tool == "sable_tracking"
    assert result.quality_score == 7.5
    assert any("schema_version 99" in msg for msg in caplog.messages)


def test_validate_tracking_meta_extra_fields_tolerated():
    """Extra fields in metadata are silently ignored (forward compat)."""
    from sable.advise.stage1 import _validate_tracking_meta

    meta = {**VALID_META, "new_field_v2": "some_value"}
    result = _validate_tracking_meta(meta)
    assert result.source_tool == "sable_tracking"


def test_validate_tracking_meta_bad_data_falls_back(caplog):
    """Malformed data falls back gracefully instead of crashing."""
    from sable.advise.stage1 import _validate_tracking_meta

    # source_tool has wrong literal value
    meta = {"source_tool": "wrong_tool", "quality_score": "not_a_number"}
    with caplog.at_level(logging.WARNING):
        result = _validate_tracking_meta(meta)
    # Should still return something usable
    assert result is not None
