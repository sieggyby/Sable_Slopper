"""Tests for sable.onboard.orchestrator — T3-3: onboarding wiring."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml


def test_load_prospect_yaml(tmp_path):
    """Valid prospect YAML is loaded correctly."""
    from sable.onboard.orchestrator import _load_prospect_yaml

    prospect_file = tmp_path / "test_prospect.yaml"
    prospect_file.write_text(yaml.dump({
        "project_slug": "test_project",
        "sable_org": "testorg",
        "twitter_accounts": ["@alice"],
    }), encoding="utf-8")

    result = _load_prospect_yaml(prospect_file)
    assert result["sable_org"] == "testorg"
    assert result["twitter_accounts"] == ["@alice"]


def test_missing_prospect_yaml_raises():
    """run_onboard with missing YAML raises SableError."""
    from sable.onboard.orchestrator import run_onboard
    from sable.platform.errors import SableError

    with pytest.raises(SableError, match="not found"):
        run_onboard("/nonexistent/path.yaml")


def test_load_prospect_yaml_malformed(tmp_path):
    """Malformed prospect YAML raises ValueError."""
    from sable.onboard.orchestrator import _load_prospect_yaml

    bad_file = tmp_path / "bad.yaml"
    bad_file.write_text("{bad yaml: [", encoding="utf-8")

    from sable.platform.errors import SableError
    with pytest.raises(SableError, match="Failed to parse"):
        _load_prospect_yaml(bad_file)
