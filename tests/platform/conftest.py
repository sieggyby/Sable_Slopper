"""Shared fixtures for platform tests."""
import sqlite3

import pytest

from sable.platform.db import ensure_schema


@pytest.fixture
def conn(sable_conn):
    return sable_conn


@pytest.fixture
def org_conn(sable_org_conn):
    """Connection with a test org pre-created."""
    return sable_org_conn


@pytest.fixture
def migration_conn():
    """Raw sqlite3 connection created via ensure_schema (migration path).

    Use this for tests that specifically test migration behaviour.
    """
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    ensure_schema(c)
    yield c
    c.close()
