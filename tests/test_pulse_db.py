"""Tests for pulse/db.py handle normalization."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def tmp_sable_home(tmp_path, monkeypatch):
    monkeypatch.setenv("SABLE_HOME", str(tmp_path / ".sable"))
    monkeypatch.setattr("sable.shared.paths.sable_home", lambda: tmp_path / ".sable")


def _migrate(tmp_path):
    from sable.pulse.db import migrate
    migrate()


def test_insert_post_normalizes_handle(tmp_path, monkeypatch):
    """Insert with bare handle (no @); get_posts_for_account with @ should find it."""
    monkeypatch.setattr("sable.shared.paths.sable_home", lambda: tmp_path)
    _migrate(tmp_path)

    from sable.pulse.db import insert_post, get_posts_for_account

    inserted = insert_post("post1", "alice", text="hello")
    assert inserted is True

    # Query with @ prefix — should find the post
    posts = get_posts_for_account("@alice")
    assert len(posts) == 1
    assert posts[0]["id"] == "post1"
    assert posts[0]["account_handle"] == "@alice"


def test_insert_post_at_prefix_idempotent(tmp_path, monkeypatch):
    """Insert with @ prefix — should not produce @@alice."""
    monkeypatch.setattr("sable.shared.paths.sable_home", lambda: tmp_path)
    _migrate(tmp_path)

    from sable.pulse.db import insert_post, get_posts_for_account

    inserted = insert_post("post2", "@alice", text="world")
    assert inserted is True

    posts = get_posts_for_account("@alice")
    assert len(posts) == 1
    assert posts[0]["account_handle"] == "@alice"
