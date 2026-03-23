"""Shared fixtures for advise tests."""
import sqlite3
import uuid
import pytest

from sable.platform.db import ensure_schema


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    ensure_schema(c)
    c.execute("INSERT INTO orgs (org_id, display_name) VALUES ('testorg', 'Test Org')")
    c.commit()
    yield c
    c.close()


@pytest.fixture
def org_id():
    return "testorg"
