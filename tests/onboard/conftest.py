"""Shared fixtures for onboard tests."""
from pathlib import Path

import pytest
import yaml


@pytest.fixture
def conn(sable_conn):
    return sable_conn


@pytest.fixture
def prospect_yaml(tmp_path):
    """Create a minimal prospect YAML file."""
    prospect = {
        "display_name": "Test Project",
        "project_slug": "test-project",
        "sable_org": "testorg",
        "discord_server_id": "123456789",
        "twitter_handle": "testproject",
        "team_handles": ["@founder"],
    }
    path = tmp_path / "test_project.yaml"
    path.write_text(yaml.dump(prospect), encoding="utf-8")
    return path


@pytest.fixture
def org_conn(sable_org_conn):
    """Connection with testorg already created."""
    return sable_org_conn
