"""Tests for _assemble_community_language — CultGrader language injection."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from sable.platform.db import ensure_schema
from sable.advise.stage1 import _assemble_community_language


def _make_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    conn.execute("INSERT INTO orgs (org_id, display_name) VALUES ('testorg', 'Test')")
    conn.commit()
    return conn


def _has_language_columns(conn) -> bool:
    """Check if diagnostic_runs has language columns."""
    try:
        conn.execute(
            "SELECT language_arc_phase FROM diagnostic_runs LIMIT 0"
        )
        return True
    except Exception:
        return False


def _add_diagnostic(conn, org_id, arc_phase=None, terms=None, mantras=None, days_ago=0):
    now = datetime.now(timezone.utc) - timedelta(days=days_ago)
    started_at = now.strftime("%Y-%m-%d %H:%M:%S")

    # Add language columns if they don't exist
    try:
        conn.execute("ALTER TABLE diagnostic_runs ADD COLUMN language_arc_phase TEXT")
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE diagnostic_runs ADD COLUMN emergent_cultural_terms_json TEXT")
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE diagnostic_runs ADD COLUMN mantra_candidates_json TEXT")
    except Exception:
        pass

    conn.execute(
        """INSERT INTO diagnostic_runs
           (org_id, run_type, started_at, language_arc_phase, emergent_cultural_terms_json, mantra_candidates_json)
           VALUES (?, 'cultgrader', ?, ?, ?, ?)""",
        (org_id, started_at,
         arc_phase,
         json.dumps(terms) if terms else None,
         json.dumps(mantras) if mantras else None),
    )
    conn.commit()


def test_fresh_data_rendered():
    """Fresh diagnostic with all fields → section rendered."""
    conn = _make_conn()
    _add_diagnostic(
        conn, "testorg",
        arc_phase="emergent",
        terms=["wagmi", "gm", "ser"],
        mantras=["we're all gonna make it"],
        days_ago=0,
    )

    result = _assemble_community_language("testorg", conn)
    assert "Community Language Signal" in result
    assert "emergent" in result
    assert "wagmi" in result
    assert "we're all gonna make it" in result


def test_stale_data_skipped():
    """Diagnostic older than 14 days → empty string."""
    conn = _make_conn()
    _add_diagnostic(
        conn, "testorg",
        arc_phase="mature",
        terms=["old_term"],
        days_ago=20,
    )

    result = _assemble_community_language("testorg", conn)
    assert result == ""


def test_null_fields_skipped():
    """All language fields null → empty string."""
    conn = _make_conn()
    _add_diagnostic(conn, "testorg", days_ago=0)

    result = _assemble_community_language("testorg", conn)
    assert result == ""


def test_pre_migration_no_columns():
    """Before migration (no language columns) → empty string, no crash."""
    conn = _make_conn()
    # Don't add language columns — they won't exist

    result = _assemble_community_language("testorg", conn)
    assert result == ""


def test_partial_fields():
    """Only arc_phase set → renders just that."""
    conn = _make_conn()
    _add_diagnostic(conn, "testorg", arc_phase="declining", days_ago=1)

    result = _assemble_community_language("testorg", conn)
    assert "Community Language Signal" in result
    assert "declining" in result
    assert "cultural terms" not in result.lower()


def test_malformed_json_in_terms():
    """Malformed JSON in terms column → skipped, other fields still render."""
    conn = _make_conn()
    _add_diagnostic(conn, "testorg", arc_phase="emergent", days_ago=0)
    conn.execute(
        "UPDATE diagnostic_runs SET emergent_cultural_terms_json = 'not json'"
    )
    conn.commit()

    result = _assemble_community_language("testorg", conn)
    assert "Community Language Signal" in result
    assert "emergent" in result
    assert "cultural terms" not in result.lower()
