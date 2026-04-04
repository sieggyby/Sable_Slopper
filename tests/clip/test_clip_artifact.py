"""Tests for clip artifact registration integration."""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest


def test_clip_process_help_shows_org():
    """clip process --help shows --org flag."""
    from click.testing import CliRunner
    from sable.clip.cli import clip_process
    runner = CliRunner()
    result = runner.invoke(clip_process, ["--help"])
    assert "--org" in result.output
    assert "cost logging" in result.output.lower() or "org slug" in result.output.lower()
