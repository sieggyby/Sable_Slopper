"""Tests for churn CLI commands."""
from __future__ import annotations

import json
import os
import tempfile
from unittest.mock import patch, MagicMock

import pytest
from click.testing import CliRunner

from sable.churn.cli import churn_group
from sable.churn.interventions import InterventionResult

# Lazy imports in CLI handler — patch at source
_GET_DB = "sable.platform.db.get_db"
_GEN_PB = "sable.churn.interventions.generate_playbook"


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def input_file():
    data = [
        {
            "handle": "@alice",
            "decay_score": 0.7,
            "topics": ["DeFi"],
            "last_active": "2026-03-15",
            "role": "member",
            "notes": "",
        }
    ]
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as f:
        json.dump(data, f)
        path = f.name
    yield path
    os.unlink(path)


def test_dry_run(runner, input_file):
    """--dry-run prints estimates, no API calls."""
    result = runner.invoke(
        churn_group,
        ["intervene", "--org", "testorg", "--input", input_file, "--dry-run"],
    )
    assert result.exit_code == 0
    assert "Estimated Claude calls: 1" in result.output


def test_intervene_smoke(runner, input_file):
    """Successful generation prints results."""
    mock_results = [
        InterventionResult(
            handle="@alice",
            interest_tags=["defi", "governance"],
            role_recommendation="Delegate",
            spotlight_suggestion="Feature in recap",
            engagement_prompts=["Ask about proposal"],
            urgency="high",
        )
    ]
    with patch(_GET_DB, return_value=MagicMock()), \
         patch(_GEN_PB, return_value=mock_results):
        result = runner.invoke(
            churn_group,
            ["intervene", "--org", "testorg", "--input", input_file],
        )
    assert result.exit_code == 0
    assert "@alice" in result.output
    assert "high" in result.output


def test_intervene_output_file(runner, input_file):
    """--output writes JSON file."""
    mock_results = [
        InterventionResult(
            handle="@alice",
            interest_tags=["defi"],
            role_recommendation="Delegate",
            spotlight_suggestion="Spotlight",
            engagement_prompts=["prompt1"],
            urgency="medium",
        )
    ]
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as out:
        out_path = out.name

    try:
        with patch(_GET_DB, return_value=MagicMock()), \
             patch(_GEN_PB, return_value=mock_results):
            result = runner.invoke(
                churn_group,
                ["intervene", "--org", "testorg", "--input", input_file, "--output", out_path],
            )
        assert result.exit_code == 0
        with open(out_path, encoding="utf-8") as f:
            data = json.load(f)
        assert len(data) == 1
        assert data[0]["handle"] == "@alice"
    finally:
        os.unlink(out_path)


def test_invalid_input_file(runner):
    """Non-JSON input → error."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as f:
        f.write("not valid json")
        path = f.name

    try:
        result = runner.invoke(
            churn_group,
            ["intervene", "--org", "testorg", "--input", path],
        )
        assert result.exit_code == 1
        assert "Error reading input" in result.output
    finally:
        os.unlink(path)


def test_sable_error_handled(runner, input_file):
    """SableError from generate_playbook → printed and exit 1."""
    from sable.platform.errors import SableError
    with patch(_GET_DB, return_value=MagicMock()), \
         patch(_GEN_PB, side_effect=SableError("BUDGET_EXCEEDED", "over budget")):
        result = runner.invoke(
            churn_group,
            ["intervene", "--org", "testorg", "--input", input_file],
        )
    assert result.exit_code == 1
    assert "BUDGET_EXCEEDED" in result.output
