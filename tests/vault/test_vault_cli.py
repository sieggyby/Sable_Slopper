"""Tests for sable.vault.cli — T3-4: vault CLI subcommands."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from sable.vault.cli import vault_group
from sable.vault.search import SearchResult


def test_init_creates_directory_structure(tmp_path):
    """vault init creates directory structure via init_vault."""
    runner = CliRunner()
    vault_path = tmp_path / "test_vault"

    with patch("sable.vault.cli._resolve_vault", return_value=vault_path), \
         patch("sable.vault.init.init_vault") as mock_init:
        result = runner.invoke(vault_group, ["init", "--org", "testorg"])

    assert result.exit_code == 0
    mock_init.assert_called_once_with("testorg", vault_path)


def test_search_delegates_to_search_vault(tmp_path):
    """vault search calls search_vault with correct args."""
    runner = CliRunner()
    vault_path = tmp_path / "test_vault"
    vault_path.mkdir()

    mock_results = [
        SearchResult(
            id="note-1",
            score=9,
            reason="keyword match on defi topic",
            note={"type": "clip", "account": "@alice", "title": "test note"},
        )
    ]

    with patch("sable.vault.cli._resolve_vault", return_value=vault_path), \
         patch("sable.vault.search.search_vault", return_value=mock_results) as mock_search:
        result = runner.invoke(vault_group, ["search", "defi", "--org", "testorg"])

    assert result.exit_code == 0
    mock_search.assert_called_once()
    call_kwargs = mock_search.call_args
    assert call_kwargs[1].get("query") == "defi" or call_kwargs[0][0] == "defi"


def test_status_runs(tmp_path):
    """vault status renders without crash."""
    runner = CliRunner()
    vault_path = tmp_path / "test_vault"
    content = vault_path / "content"
    content.mkdir(parents=True)

    with patch("sable.vault.cli._resolve_vault", return_value=vault_path):
        result = runner.invoke(vault_group, ["status", "--org", "testorg"])

    assert result.exit_code == 0
