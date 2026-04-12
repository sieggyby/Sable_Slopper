"""Shared fixtures for advise tests."""
import pytest


@pytest.fixture
def conn(sable_org_conn):
    return sable_org_conn


@pytest.fixture
def org_id():
    return "testorg"
