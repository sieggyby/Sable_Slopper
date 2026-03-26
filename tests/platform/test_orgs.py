"""Tests for org creation and lookup."""
import pytest

from sable.platform.errors import SableError, ORG_EXISTS, ORG_NOT_FOUND


def test_create_org(conn):
    conn.execute("INSERT INTO orgs (org_id, display_name) VALUES ('myorg', 'My Org')")
    conn.commit()
    row = conn.execute("SELECT * FROM orgs WHERE org_id='myorg'").fetchone()
    assert row["display_name"] == "My Org"
    assert row["status"] == "active"


def test_org_id_unique(conn):
    conn.execute("INSERT INTO orgs (org_id, display_name) VALUES ('myorg', 'My Org')")
    conn.commit()
    with pytest.raises(Exception):
        conn.execute("INSERT INTO orgs (org_id, display_name) VALUES ('myorg', 'Duplicate')")
        conn.commit()


def test_org_config_json_defaults_to_empty(conn):
    conn.execute("INSERT INTO orgs (org_id, display_name) VALUES ('o1', 'Org 1')")
    conn.commit()
    row = conn.execute("SELECT config_json FROM orgs WHERE org_id='o1'").fetchone()
    assert row["config_json"] == "{}"


def test_org_status_defaults_active(conn):
    conn.execute("INSERT INTO orgs (org_id, display_name) VALUES ('o2', 'Org 2')")
    conn.commit()
    row = conn.execute("SELECT status FROM orgs WHERE org_id='o2'").fetchone()
    assert row["status"] == "active"
