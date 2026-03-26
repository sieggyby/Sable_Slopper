"""Tests for sable.pulse.linker — confirms no-op behavior."""
from __future__ import annotations


def test_auto_link_posts_is_noop():
    """auto_link_posts always returns [] — intentional permanent no-op."""
    from sable.pulse.linker import auto_link_posts

    result = auto_link_posts()
    assert result == []


def test_auto_link_posts_ignores_threshold():
    """Threshold parameter is accepted but has no effect."""
    from sable.pulse.linker import auto_link_posts

    assert auto_link_posts(threshold=0.0) == []
    assert auto_link_posts(threshold=100.0) == []
