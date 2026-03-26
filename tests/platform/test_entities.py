"""Tests for entity CRUD helpers."""
import pytest

from sable.platform.entities import (
    create_entity,
    add_handle,
    archive_entity,
    find_entity_by_handle,
    update_display_name,
)
from sable.platform.errors import SableError, ENTITY_ARCHIVED, ORG_NOT_FOUND


def test_create_entity(org_conn):
    eid = create_entity(org_conn, "testorg", display_name="Alice")
    row = org_conn.execute("SELECT * FROM entities WHERE entity_id=?", (eid,)).fetchone()
    assert row["display_name"] == "Alice"
    assert row["status"] == "candidate"
    assert row["org_id"] == "testorg"


def test_create_entity_unknown_org(conn):
    with pytest.raises(SableError) as exc:
        create_entity(conn, "nonexistent_org")
    assert exc.value.code == ORG_NOT_FOUND


def test_add_handle(org_conn):
    eid = create_entity(org_conn, "testorg")
    add_handle(org_conn, eid, "discord", "alice#1234")
    row = org_conn.execute(
        "SELECT * FROM entity_handles WHERE entity_id=?", (eid,)
    ).fetchone()
    assert row["handle"] == "alice#1234"
    assert row["platform"] == "discord"


def test_add_handle_strips_at_sign(org_conn):
    eid = create_entity(org_conn, "testorg")
    add_handle(org_conn, eid, "twitter", "@cryptoalice")
    row = org_conn.execute(
        "SELECT handle FROM entity_handles WHERE entity_id=?", (eid,)
    ).fetchone()
    assert row["handle"] == "cryptoalice"


def test_add_handle_lowercases(org_conn):
    eid = create_entity(org_conn, "testorg")
    add_handle(org_conn, eid, "twitter", "CryptoAlice")
    row = org_conn.execute(
        "SELECT handle FROM entity_handles WHERE entity_id=?", (eid,)
    ).fetchone()
    assert row["handle"] == "cryptoalice"


def test_find_entity_by_handle(org_conn):
    eid = create_entity(org_conn, "testorg")
    add_handle(org_conn, eid, "twitter", "cryptoalice")
    found = find_entity_by_handle(org_conn, "testorg", "twitter", "cryptoalice")
    assert found is not None
    assert found["entity_id"] == eid


def test_find_entity_by_handle_not_found(org_conn):
    result = find_entity_by_handle(org_conn, "testorg", "twitter", "nobody")
    assert result is None


def test_find_entity_excludes_archived(org_conn):
    eid = create_entity(org_conn, "testorg")
    add_handle(org_conn, eid, "twitter", "archiveduser")
    archive_entity(org_conn, eid)
    result = find_entity_by_handle(org_conn, "testorg", "twitter", "archiveduser")
    assert result is None


def test_archive_entity(org_conn):
    eid = create_entity(org_conn, "testorg")
    archive_entity(org_conn, eid)
    row = org_conn.execute("SELECT status FROM entities WHERE entity_id=?", (eid,)).fetchone()
    assert row["status"] == "archived"


def test_add_handle_to_archived_raises(org_conn):
    eid = create_entity(org_conn, "testorg")
    archive_entity(org_conn, eid)
    with pytest.raises(SableError) as exc:
        add_handle(org_conn, eid, "twitter", "newhandle")
    assert exc.value.code == ENTITY_ARCHIVED


def test_update_display_name_auto_on_candidate(org_conn):
    eid = create_entity(org_conn, "testorg", display_name="Old Name")
    update_display_name(org_conn, eid, "New Name", source="auto")
    row = org_conn.execute("SELECT display_name FROM entities WHERE entity_id=?", (eid,)).fetchone()
    assert row["display_name"] == "New Name"


def test_update_display_name_auto_on_confirmed_noop(org_conn):
    eid = create_entity(org_conn, "testorg", display_name="Confirmed Name", status="confirmed")
    update_display_name(org_conn, eid, "Ignored", source="auto")
    row = org_conn.execute("SELECT display_name FROM entities WHERE entity_id=?", (eid,)).fetchone()
    assert row["display_name"] == "Confirmed Name"


def test_update_display_name_manual_on_confirmed(org_conn):
    eid = create_entity(org_conn, "testorg", display_name="Old", status="confirmed")
    update_display_name(org_conn, eid, "Manual Override", source="manual")
    row = org_conn.execute("SELECT display_name FROM entities WHERE entity_id=?", (eid,)).fetchone()
    assert row["display_name"] == "Manual Override"
