"""Fixtures for org_status tests."""
import sqlite3
import pytest
from sable.platform.db import ensure_schema


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    ensure_schema(c)
    yield c
    c.close()


@pytest.fixture
def org_conn(conn):
    conn.execute("INSERT INTO orgs (org_id, display_name) VALUES ('testorg', 'Test Org')")
    conn.commit()
    return conn
