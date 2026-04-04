"""Tests for sable.lexicon.writer — interpretation and report generation."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from sable.lexicon.writer import interpret_terms, render_report


# ---------------------------------------------------------------------------
# interpret_terms
# ---------------------------------------------------------------------------

@patch("sable.shared.api.call_claude_json")
@patch("sable.platform.db.get_db")
@patch("sable.platform.cost.check_budget")
def test_interpret_terms_parses_claude_response(mock_budget, mock_db, mock_claude):
    """Claude response is parsed and merged into term dicts."""
    mock_db.return_value = MagicMock()
    mock_claude.return_value = json.dumps([
        {"term": "zkrollup", "category": "project_term", "gloss": "Zero-knowledge rollup"},
        {"term": "gm", "category": "insider_slang", "gloss": "Good morning greeting"},
    ])

    terms = [
        {"term": "zkrollup", "lsr": 0.5},
        {"term": "gm", "lsr": 0.3},
    ]
    result = interpret_terms(terms, "test_org")
    assert result[0]["category"] == "project_term"
    assert result[0]["gloss"] == "Zero-knowledge rollup"
    assert result[1]["category"] == "insider_slang"


@patch("sable.shared.api.call_claude_json")
@patch("sable.platform.db.get_db")
@patch("sable.platform.cost.check_budget")
def test_interpret_terms_handles_claude_failure(mock_budget, mock_db, mock_claude):
    """Claude failure → terms get 'unknown' category."""
    mock_db.return_value = MagicMock()
    mock_claude.side_effect = Exception("API error")

    terms = [{"term": "foo", "lsr": 0.1}]
    result = interpret_terms(terms, "org")
    assert result[0].get("category") == "unknown"


@patch("sable.platform.db.get_db")
@patch("sable.platform.cost.check_budget")
def test_interpret_terms_budget_exceeded_stops_claude(mock_budget, mock_db):
    """SableError from check_budget propagates — no Claude call made."""
    from sable.platform.errors import SableError
    mock_db.return_value = MagicMock()
    mock_budget.side_effect = SableError("BUDGET_EXCEEDED", "Over budget")

    terms = [{"term": "foo", "lsr": 0.1}]
    with pytest.raises(SableError, match="BUDGET_EXCEEDED"):
        interpret_terms(terms, "org")


@patch("sable.shared.api.call_claude_json")
@patch("sable.platform.db.get_db")
@patch("sable.platform.cost.check_budget")
def test_interpret_terms_handles_wrapped_json(mock_budget, mock_db, mock_claude):
    """Claude returns dict wrapper → terms still parsed."""
    mock_db.return_value = MagicMock()
    mock_claude.return_value = json.dumps({
        "terms": [
            {"term": "zkrollup", "category": "project_term", "gloss": "ZK tech"},
        ]
    })

    terms = [{"term": "zkrollup", "lsr": 0.5}]
    result = interpret_terms(terms, "org")
    assert result[0]["category"] == "project_term"
    assert result[0]["gloss"] == "ZK tech"


def test_interpret_terms_empty_list():
    """Empty term list returns empty."""
    assert interpret_terms([], "org") == []


# ---------------------------------------------------------------------------
# render_report
# ---------------------------------------------------------------------------

def test_render_report_writes_markdown(tmp_path):
    """Report is written as markdown with frontmatter."""
    terms = [
        {"term": "zkrollup", "category": "project_term", "gloss": "ZK tech", "lsr": 0.5},
        {"term": "gm", "category": "insider_slang", "gloss": "Morning", "lsr": 0.3},
    ]
    path = render_report(terms, "test_org", tmp_path)
    assert path.exists()
    content = path.read_text()
    assert "zkrollup" in content
    assert "Community Lexicon" in content
    assert "type: lexicon_report" in content


def test_render_report_empty_terms(tmp_path):
    """Empty terms list → 'no terms detected' message."""
    path = render_report([], "org", tmp_path)
    content = path.read_text()
    assert "No community-specific terms" in content
