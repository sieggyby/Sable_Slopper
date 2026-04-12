"""Shared fixtures for Sable Slopper tests.

Provides CompatConnection-backed in-memory sable.db fixtures that work
with SablePlatform's SQLAlchemy Core text() wrappers.
"""
import pytest
from sqlalchemy import create_engine

from sable_platform.db.compat_conn import CompatConnection
from sable_platform.db.schema import metadata as sa_metadata


@pytest.fixture
def sable_conn():
    """In-memory sable.db wrapped in CompatConnection."""
    engine = create_engine("sqlite:///:memory:")
    sa_metadata.create_all(engine)
    sa_conn = engine.connect()
    conn = CompatConnection(sa_conn)
    yield conn
    conn.close()
    engine.dispose()


@pytest.fixture
def sable_org_conn(sable_conn):
    """CompatConnection with testorg already created."""
    sable_conn.execute(
        "INSERT INTO orgs (org_id, display_name) VALUES (?, ?)",
        ("testorg", "Test Org"),
    )
    sable_conn.commit()
    return sable_conn
