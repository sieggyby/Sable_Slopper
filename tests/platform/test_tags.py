"""Tests for entity tag helpers."""
import pytest

from sable.platform.entities import create_entity
from sable.platform.tags import add_tag, get_active_tags, get_entities_by_tag


def test_add_and_get_active_tag(org_conn):
    eid = create_entity(org_conn, "testorg")
    add_tag(org_conn, eid, "cultist_candidate", source="auto", confidence=0.9)
    tags = get_active_tags(org_conn, eid)
    assert len(tags) == 1
    assert tags[0]["tag"] == "cultist_candidate"


def test_append_history_tag_accumulates(org_conn):
    eid = create_entity(org_conn, "testorg")
    add_tag(org_conn, eid, "cultist_candidate")
    add_tag(org_conn, eid, "cultist_candidate")
    tags = get_active_tags(org_conn, eid)
    assert len(tags) == 2


def test_replace_current_tag_deactivates_prior(org_conn):
    eid = create_entity(org_conn, "testorg")
    add_tag(org_conn, eid, "high_lift_account")
    add_tag(org_conn, eid, "high_lift_account")
    tags = get_active_tags(org_conn, eid)
    assert len(tags) == 1  # only the new one is current


def test_get_entities_by_tag(org_conn):
    eid1 = create_entity(org_conn, "testorg")
    eid2 = create_entity(org_conn, "testorg")
    add_tag(org_conn, eid1, "watchlist_account")
    add_tag(org_conn, eid2, "cultist_candidate")

    watchlist = get_entities_by_tag(org_conn, "testorg", "watchlist_account")
    entity_ids = [r["entity_id"] for r in watchlist]
    assert eid1 in entity_ids
    assert eid2 not in entity_ids


def test_expired_tag_not_returned(org_conn):
    eid = create_entity(org_conn, "testorg")
    add_tag(org_conn, eid, "cultist_candidate", expires_at="2000-01-01T00:00:00")
    tags = get_active_tags(org_conn, eid)
    assert len(tags) == 0
