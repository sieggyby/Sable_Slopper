"""Tests for vault/search.py large-result path tuple-unwrap fix."""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest


def _make_fake_notes(n: int) -> list[dict]:
    """Build n fake note dicts."""
    return [
        {
            "id": f"note-{i}",
            "type": "clip",
            "topic": f"crypto topic {i}",
            "topics": ["defi"],
            "keywords": ["crypto"],
            "questions_answered": [],
            "depth": "intermediate",
            "tone": "neutral",
            "caption": "",
            "script_preview": "",
        }
        for i in range(n)
    ]


def test_search_vault_large_result_uses_claude_rank(tmp_path):
    """With >50 candidates, search_vault should call claude_rank with unwrapped notes (not tuples)."""
    from sable.vault.search import search_vault, SearchResult, SearchFilters
    from sable.vault.config import VaultConfig

    notes = _make_fake_notes(60)
    sentinel = [SearchResult(id="note-0", score=99, reason="sentinel", note=notes[0])]

    config = VaultConfig()

    with patch("sable.vault.search.load_candidates", return_value=notes), \
         patch("sable.vault.search.claude_rank", return_value=sentinel) as mock_rank:
        result = search_vault("defi crypto", tmp_path, "testorg", config=config)

    assert result == sentinel
    # Verify claude_rank was called and received a list of dicts (not tuples)
    assert mock_rank.called
    candidates_arg = mock_rank.call_args[0][1]
    assert len(candidates_arg) == 50
    assert isinstance(candidates_arg[0], dict), (
        f"Expected dict, got {type(candidates_arg[0])}"
    )


def test_search_vault_small_result_fallback_on_claude_failure(tmp_path):
    """With <=50 candidates and claude_rank raising, fallback returns list[SearchResult] — no crash."""
    from sable.vault.search import search_vault, SearchResult, SearchFilters
    from sable.vault.config import VaultConfig

    notes = _make_fake_notes(30)
    config = VaultConfig()

    with patch("sable.vault.search.load_candidates", return_value=notes), \
         patch("sable.vault.search.claude_rank", side_effect=RuntimeError("API down")):
        result = search_vault("defi crypto", tmp_path, "testorg", config=config)

    assert isinstance(result, list)
    for r in result:
        assert isinstance(r, SearchResult)
    assert len(result) <= config.max_suggestions


def test_search_vault_small_result_passes_org_to_claude_rank(tmp_path):
    """With <=50 candidates, org is threaded to claude_rank."""
    from sable.vault.search import search_vault, SearchResult
    from sable.vault.config import VaultConfig

    notes = _make_fake_notes(30)
    sentinel = [SearchResult(id="note-0", score=99, reason="test", note=notes[0])]
    config = VaultConfig()

    with patch("sable.vault.search.load_candidates", return_value=notes), \
         patch("sable.vault.search.claude_rank", return_value=sentinel) as mock_rank:
        search_vault("defi crypto", tmp_path, "myorg", config=config)

    assert mock_rank.called
    assert mock_rank.call_args[1].get("org") == "myorg"


def test_search_vault_large_result_passes_org_to_claude_rank(tmp_path):
    """With >50 candidates, org is threaded to claude_rank."""
    from sable.vault.search import search_vault, SearchResult
    from sable.vault.config import VaultConfig

    notes = _make_fake_notes(60)
    sentinel = [SearchResult(id="note-0", score=99, reason="test", note=notes[0])]
    config = VaultConfig()

    with patch("sable.vault.search.load_candidates", return_value=notes), \
         patch("sable.vault.search.claude_rank", return_value=sentinel) as mock_rank:
        search_vault("defi crypto", tmp_path, "myorg", config=config)

    assert mock_rank.called
    assert mock_rank.call_args[1].get("org") == "myorg"


def test_search_vault_large_result_fallback_on_claude_failure(tmp_path):
    """With >50 candidates and claude_rank raising, fallback returns list[SearchResult] — no crash."""
    from sable.vault.search import search_vault, SearchResult, SearchFilters
    from sable.vault.config import VaultConfig

    notes = _make_fake_notes(60)
    config = VaultConfig()

    with patch("sable.vault.search.load_candidates", return_value=notes), \
         patch("sable.vault.search.claude_rank", side_effect=RuntimeError("API down")):
        result = search_vault("defi crypto", tmp_path, "testorg", config=config)

    assert isinstance(result, list)
    for r in result:
        assert isinstance(r, SearchResult)
