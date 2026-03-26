"""Tests for entity merge helpers."""
import pytest

from sable.platform.entities import create_entity, add_handle
from sable.platform.merge import create_merge_candidate, execute_merge, get_pending_merges
from sable.platform.errors import SableError, CROSS_ORG_MERGE_BLOCKED


def test_create_merge_candidate(org_conn):
    a = create_entity(org_conn, "testorg")
    b = create_entity(org_conn, "testorg")
    create_merge_candidate(org_conn, a, b, confidence=0.85)
    rows = org_conn.execute("SELECT * FROM merge_candidates").fetchall()
    assert len(rows) == 1
    assert rows[0]["status"] == "pending"


def test_create_merge_candidate_canonical_ordering(org_conn):
    a = create_entity(org_conn, "testorg")
    b = create_entity(org_conn, "testorg")
    # Pass b, a (wrong order) — should store as a < b
    create_merge_candidate(org_conn, b, a, confidence=0.85)
    row = org_conn.execute("SELECT entity_a_id, entity_b_id FROM merge_candidates").fetchone()
    ids = sorted([a, b])
    assert row["entity_a_id"] == ids[0]
    assert row["entity_b_id"] == ids[1]


def test_low_confidence_candidate_is_expired(org_conn):
    a = create_entity(org_conn, "testorg")
    b = create_entity(org_conn, "testorg")
    create_merge_candidate(org_conn, a, b, confidence=0.50)
    row = org_conn.execute("SELECT status FROM merge_candidates").fetchone()
    assert row["status"] == "expired"


def test_insert_or_ignore_on_duplicate(org_conn):
    a = create_entity(org_conn, "testorg")
    b = create_entity(org_conn, "testorg")
    create_merge_candidate(org_conn, a, b, confidence=0.85)
    create_merge_candidate(org_conn, a, b, confidence=0.90)  # should be ignored
    rows = org_conn.execute("SELECT * FROM merge_candidates").fetchall()
    assert len(rows) == 1


def test_execute_merge_archives_source(org_conn):
    a = create_entity(org_conn, "testorg", display_name="Alice")
    b = create_entity(org_conn, "testorg", display_name="Bob")
    execute_merge(org_conn, source_entity_id=a, target_entity_id=b)
    src = org_conn.execute("SELECT status FROM entities WHERE entity_id=?", (a,)).fetchone()
    assert src["status"] == "archived"


def test_execute_merge_creates_event(org_conn):
    a = create_entity(org_conn, "testorg")
    b = create_entity(org_conn, "testorg")
    execute_merge(org_conn, source_entity_id=a, target_entity_id=b)
    event = org_conn.execute("SELECT * FROM merge_events").fetchone()
    assert event is not None
    assert event["source_entity_id"] == a
    assert event["target_entity_id"] == b


def test_execute_merge_rehomes_handles(org_conn):
    a = create_entity(org_conn, "testorg")
    b = create_entity(org_conn, "testorg")
    add_handle(org_conn, a, "twitter", "alicecrypto")
    execute_merge(org_conn, source_entity_id=a, target_entity_id=b)
    handle = org_conn.execute(
        "SELECT entity_id FROM entity_handles WHERE handle='alicecrypto'"
    ).fetchone()
    assert handle["entity_id"] == b


def test_cross_org_merge_blocked(conn):
    conn.execute("INSERT INTO orgs (org_id, display_name) VALUES ('org1', 'Org 1')")
    conn.execute("INSERT INTO orgs (org_id, display_name) VALUES ('org2', 'Org 2')")
    conn.commit()
    a = create_entity(conn, "org1")
    b = create_entity(conn, "org2")
    with pytest.raises(SableError) as exc:
        execute_merge(conn, source_entity_id=a, target_entity_id=b)
    assert exc.value.code == CROSS_ORG_MERGE_BLOCKED


def test_get_pending_merges(org_conn):
    a = create_entity(org_conn, "testorg")
    b = create_entity(org_conn, "testorg")
    create_merge_candidate(org_conn, a, b, confidence=0.90)
    rows = get_pending_merges(org_conn, "testorg")
    assert len(rows) == 1


def test_shared_handle_creates_merge_candidate(org_conn):
    a = create_entity(org_conn, "testorg")
    b = create_entity(org_conn, "testorg")
    add_handle(org_conn, a, "twitter", "shareduser")
    # Adding the same handle to b should trigger merge candidate creation
    add_handle(org_conn, b, "twitter", "shareduser")
    rows = org_conn.execute("SELECT * FROM merge_candidates").fetchall()
    assert len(rows) == 1
    assert rows[0]["status"] == "pending"
