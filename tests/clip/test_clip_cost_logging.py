"""Tests for clip process --org flag and cost logging wiring."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from sable.roster.models import Account, Persona, ContentSettings


def _make_account(handle="@test", org="psy"):
    return Account(
        handle=handle,
        display_name="Test",
        org=org,
        persona=Persona(),
        content=ContentSettings(),
    )


def test_select_clips_accepts_org_id():
    """select_clips signature accepts org_id parameter."""
    import inspect
    from sable.clip.selector import select_clips
    sig = inspect.signature(select_clips)
    assert "org_id" in sig.parameters


def test_evaluate_variants_batch_accepts_org_id():
    """_evaluate_variants_batch signature accepts org_id parameter."""
    import inspect
    from sable.clip.selector import _evaluate_variants_batch
    sig = inspect.signature(_evaluate_variants_batch)
    assert "org_id" in sig.parameters


def test_clip_cli_org_flag_exists():
    """clip process command accepts --org flag."""
    from click.testing import CliRunner
    from sable.clip.cli import clip_process
    runner = CliRunner()
    # Just check --help includes --org
    result = runner.invoke(clip_process, ["--help"])
    assert "--org" in result.output
