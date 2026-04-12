"""Fixtures for org_status tests."""
import pytest


@pytest.fixture
def conn(sable_conn):
    return sable_conn


@pytest.fixture
def org_conn(sable_org_conn):
    return sable_org_conn
