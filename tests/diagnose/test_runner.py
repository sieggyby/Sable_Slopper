"""Tests for sable/diagnose/runner.py — 12 tests covering all five audit sections."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from sable.diagnose.runner import (
    DiagnosisReport,
    Finding,
    FindingSeverity,
    _attach_suggested_commands,
    _audit_engagement_trend,
    _audit_format_portfolio,
    _audit_posting_cadence,
    _audit_topic_freshness,
    _audit_vault_utilization,
    render_diagnosis,
    run_diagnosis,
    save_diagnosis_artifact,
)
from sable.platform.db import ensure_schema
from sable.pulse.account_report import AccountFormatReport, FormatLiftEntry


# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------

_PULSE_SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    id TEXT PRIMARY KEY,
    account_handle TEXT NOT NULL,
    platform TEXT DEFAULT 'twitter',
    url TEXT,
    text TEXT,
    posted_at TEXT,
    sable_content_type TEXT,
    sable_content_path TEXT,
    is_thread INTEGER DEFAULT 0,
    thread_length INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id TEXT NOT NULL,
    taken_at TEXT DEFAULT (datetime('now')),
    likes INTEGER DEFAULT 0,
    retweets INTEGER DEFAULT 0,
    replies INTEGER DEFAULT 0,
    views INTEGER DEFAULT 0,
    bookmarks INTEGER DEFAULT 0,
    quotes INTEGER DEFAULT 0
);
"""

_META_SCHEMA = """
CREATE TABLE IF NOT EXISTS topic_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    org TEXT NOT NULL,
    term TEXT NOT NULL,
    avg_lift REAL DEFAULT 1.0,
    unique_authors INTEGER DEFAULT 1
);
"""


def _make_pulse_db(tmp_path: Path) -> Path:
    path = tmp_path / "pulse.db"
    conn = sqlite3.connect(str(path))
    conn.executescript(_PULSE_SCHEMA)
    conn.commit()
    conn.close()
    return path


def _make_meta_db(tmp_path: Path) -> Path:
    path = tmp_path / "meta.db"
    conn = sqlite3.connect(str(path))
    conn.executescript(_META_SCHEMA)
    conn.commit()
    conn.close()
    return path


def _iso(days_ago: int = 1) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return dt.isoformat()


def _insert_post(
    conn: sqlite3.Connection,
    post_id: str,
    handle: str,
    ct: str = "text",
    days_ago: int = 1,
    text: str = "hello world",
) -> None:
    conn.execute(
        """INSERT INTO posts (id, account_handle, text, posted_at, sable_content_type)
           VALUES (?, ?, ?, ?, ?)""",
        (post_id, handle, text, _iso(days_ago), ct),
    )


def _insert_snapshot(
    conn: sqlite3.Connection,
    post_id: str,
    likes: int = 0,
) -> None:
    conn.execute(
        """INSERT INTO snapshots (post_id, likes, retweets, replies, views, bookmarks, quotes)
           VALUES (?, ?, 0, 0, 0, 0, 0)""",
        (post_id, likes),
    )


def _make_format_report(
    total_posts: int = 10,
    entries: list[FormatLiftEntry] | None = None,
    missing_niche_formats: list[str] | None = None,
) -> AccountFormatReport:
    return AccountFormatReport(
        handle="@alice",
        org="testorg",
        days=30,
        total_posts=total_posts,
        entries=entries or [],
        missing_niche_formats=missing_niche_formats or [],
        generated_at=_iso(0),
    )


# ---------------------------------------------------------------------------
# Test 1: format over-indexing
# ---------------------------------------------------------------------------

def test_format_over_indexing(tmp_path):
    """80% standalone_text out of 10 posts → WARNING about over-indexing."""
    entry = FormatLiftEntry(
        format_bucket="standalone_text",
        account_lift=1.2,
        niche_lift=None,
        niche_trend_status=None,
        niche_confidence=None,
        post_count=8,
        account_confidence="C",
        divergence_signal="NEUTRAL",
    )
    report = _make_format_report(total_posts=10, entries=[entry])
    pulse_db = _make_pulse_db(tmp_path)

    with patch("sable.diagnose.runner.compute_account_format_lift", return_value=report):
        findings = _audit_format_portfolio(
            "@alice", "testorg", 30, pulse_db, None
        )

    warnings = [f for f in findings if f.severity == FindingSeverity.WARNING]
    assert len(warnings) >= 1
    assert any("standalone_text" in w.message for w in warnings)
    assert any("Over-indexed" in w.message for w in warnings)


# ---------------------------------------------------------------------------
# Test 2: format execution gap
# ---------------------------------------------------------------------------

def test_format_execution_gap(tmp_path):
    """Primary format has EXECUTION GAP divergence signal → WARNING."""
    entry = FormatLiftEntry(
        format_bucket="thread",
        account_lift=0.5,
        niche_lift=1.7,
        niche_trend_status="rising",
        niche_confidence="B",
        post_count=8,
        account_confidence="C",
        divergence_signal="EXECUTION GAP",
    )
    report = _make_format_report(total_posts=8, entries=[entry])
    pulse_db = _make_pulse_db(tmp_path)

    with patch("sable.diagnose.runner.compute_account_format_lift", return_value=report):
        findings = _audit_format_portfolio(
            "@alice", "testorg", 30, pulse_db, None
        )

    warnings = [f for f in findings if f.severity == FindingSeverity.WARNING]
    assert len(warnings) >= 1
    assert any("Execution gap" in w.message for w in warnings)
    assert any("thread" in w.message for w in warnings)


# ---------------------------------------------------------------------------
# Test 3: format gap (niche surging but account never used)
# ---------------------------------------------------------------------------

def test_format_gap(tmp_path):
    """Niche has surging short_clip but account never used it → INFO finding."""
    report = _make_format_report(
        total_posts=4,
        entries=[],
        missing_niche_formats=["short_clip"],
    )
    pulse_db = _make_pulse_db(tmp_path)

    with patch("sable.diagnose.runner.compute_account_format_lift", return_value=report):
        findings = _audit_format_portfolio(
            "@alice", "testorg", 30, pulse_db, None
        )

    infos = [f for f in findings if f.severity == FindingSeverity.INFO]
    assert len(infos) >= 1
    assert any("short_clip" in f.message for f in infos)


# ---------------------------------------------------------------------------
# Test 4: topic gap
# ---------------------------------------------------------------------------

def test_topic_gap(tmp_path):
    """'solana infra' in meta.db topic_signals but absent from last-20-posts → INFO."""
    pulse_db = _make_pulse_db(tmp_path)
    meta_db = _make_meta_db(tmp_path)

    # Account posts with no mention of "solana infra"
    pconn = sqlite3.connect(str(pulse_db))
    for i in range(5):
        _insert_post(pconn, f"p{i}", "@alice", text="Bitcoin price update today")
    pconn.commit()
    pconn.close()

    # Niche signal for "solana infra"
    mconn = sqlite3.connect(str(meta_db))
    mconn.execute(
        "INSERT INTO topic_signals (org, term, avg_lift, unique_authors) VALUES (?,?,?,?)",
        ("testorg", "solana infra", 2.0, 10),
    )
    mconn.commit()
    mconn.close()

    findings = _audit_topic_freshness("@alice", "testorg", pulse_db, meta_db)

    infos = [f for f in findings if f.severity == FindingSeverity.INFO]
    assert any("solana infra" in f.message for f in infos)


# ---------------------------------------------------------------------------
# Test 5: vault stale unposted
# ---------------------------------------------------------------------------

def test_vault_stale_unposted(tmp_path):
    """5 notes assembled 10 days ago with no posted_by → WARNING with count=5."""
    stale_ts = _iso(10)
    fake_notes = [
        {
            "account": "@alice",
            "assembled_at": stale_ts,
            "_note_path": f"/fake/note{i}.md",
        }
        for i in range(5)
    ]
    meta_db = _make_meta_db(tmp_path)
    vault_root = tmp_path / "vault"
    vault_root.mkdir()

    with patch("sable.diagnose.runner.load_all_notes", return_value=fake_notes):
        findings = _audit_vault_utilization("@alice", "testorg", vault_root, meta_db)

    warnings = [f for f in findings if f.severity == FindingSeverity.WARNING]
    assert len(warnings) >= 1
    assert any("5" in w.message for w in warnings)
    assert any("Stale inventory" in w.message for w in warnings)


# ---------------------------------------------------------------------------
# Test 6: vault hot topic unposted
# ---------------------------------------------------------------------------

def test_vault_hot_topic_unposted(tmp_path):
    """Unposted note topic matches niche signal → WARNING about hot topic."""
    fake_notes = [
        {
            "account": "@alice",
            "topic": "solana",
            "assembled_at": _iso(2),
            "_note_path": "/fake/note.md",
        }
    ]
    meta_db = _make_meta_db(tmp_path)
    mconn = sqlite3.connect(str(meta_db))
    mconn.execute(
        "INSERT INTO topic_signals (org, term, avg_lift, unique_authors) VALUES (?,?,?,?)",
        ("testorg", "solana", 2.5, 15),
    )
    mconn.commit()
    mconn.close()

    vault_root = tmp_path / "vault"
    vault_root.mkdir()

    with patch("sable.diagnose.runner.load_all_notes", return_value=fake_notes):
        findings = _audit_vault_utilization("@alice", "testorg", vault_root, meta_db)

    warnings = [f for f in findings if f.severity == FindingSeverity.WARNING]
    assert any("Hot topic" in w.message for w in warnings)
    assert any("solana" in w.message for w in warnings)


# ---------------------------------------------------------------------------
# Test 7: cadence dry spell
# ---------------------------------------------------------------------------

def test_cadence_dry_spell(tmp_path):
    """7-day gap between first and second post cluster → WARNING with 'dry spell'."""
    pulse_db = _make_pulse_db(tmp_path)
    conn = sqlite3.connect(str(pulse_db))

    # 5 posts on each of days 29, 21, 14, 7, 1 ago → avg = 25/30 = 0.83/day (no low-activity)
    # gap between day 29 ago and day 21 ago = (29-21) - 1 = 7 days → WARNING
    for cluster_day in (29, 21, 14, 7, 1):
        for i in range(5):
            _insert_post(conn, f"d{cluster_day}_{i}", "@alice", days_ago=cluster_day)
    conn.commit()
    conn.close()

    findings = _audit_posting_cadence("@alice", pulse_db, 30)

    warnings = [f for f in findings if f.severity == FindingSeverity.WARNING]
    assert any("dry spell" in w.message.lower() for w in warnings)
    # Longest dry spell = 7 days (between day 29 and day 21)
    assert any("7" in w.message for w in warnings)


# ---------------------------------------------------------------------------
# Test 8: cadence low activity
# ---------------------------------------------------------------------------

def test_cadence_low_activity(tmp_path):
    """5 posts in 30 days (avg < 0.5/day) → WARNING about low activity."""
    pulse_db = _make_pulse_db(tmp_path)
    conn = sqlite3.connect(str(pulse_db))
    for i in range(5):
        _insert_post(conn, f"p{i}", "@alice", days_ago=i + 1)
    conn.commit()
    conn.close()

    findings = _audit_posting_cadence("@alice", pulse_db, 30)

    warnings = [f for f in findings if f.severity == FindingSeverity.WARNING]
    assert any("Low activity" in w.message for w in warnings)


# ---------------------------------------------------------------------------
# Test 9: engagement trend declining
# ---------------------------------------------------------------------------

def test_engagement_trend_declining(tmp_path):
    """Two consecutive week-over-week drops > 20% → WARNING."""
    pulse_db = _make_pulse_db(tmp_path)
    conn = sqlite3.connect(str(pulse_db))

    # Window 0 (oldest, ~21-27 days ago): 3 posts, 100 likes each
    for i in range(3):
        _insert_post(conn, f"w0p{i}", "@alice", days_ago=22 + i)
        _insert_snapshot(conn, f"w0p{i}", likes=100)

    # Window 1 (14-20 days ago): 3 posts, 70 likes each (30% drop)
    for i in range(3):
        _insert_post(conn, f"w1p{i}", "@alice", days_ago=15 + i)
        _insert_snapshot(conn, f"w1p{i}", likes=70)

    # Window 2 (7-13 days ago): 3 posts, 49 likes each (30% drop)
    for i in range(3):
        _insert_post(conn, f"w2p{i}", "@alice", days_ago=8 + i)
        _insert_snapshot(conn, f"w2p{i}", likes=49)

    # Window 3 (0-6 days ago): 3 posts, 34 likes each (30% drop)
    for i in range(3):
        _insert_post(conn, f"w3p{i}", "@alice", days_ago=1 + i)
        _insert_snapshot(conn, f"w3p{i}", likes=34)

    conn.commit()
    conn.close()

    findings = _audit_engagement_trend("@alice", pulse_db)

    assert len(findings) == 1
    assert findings[0].severity == FindingSeverity.WARNING
    assert "declining" in findings[0].message.lower()


# ---------------------------------------------------------------------------
# Test 10: all clear — healthy data produces 0 warnings
# ---------------------------------------------------------------------------

def test_all_clear(tmp_path):
    """Healthy account data produces no WARNING findings."""
    pulse_db = _make_pulse_db(tmp_path)
    conn = sqlite3.connect(str(pulse_db))

    # 28 posts over 28 days (1/day), alternating text/clip, stable engagement
    for i in range(28):
        ct = "text" if i % 2 == 0 else "clip"
        _insert_post(conn, f"p{i}", "@alice", ct=ct, days_ago=i + 1)
        _insert_snapshot(conn, f"p{i}", likes=100)
    conn.commit()
    conn.close()

    # Monkeypatch format report to return healthy state (diverse formats, no gaps)
    healthy_report = AccountFormatReport(
        handle="@alice",
        org="",
        days=30,
        total_posts=28,
        entries=[
            FormatLiftEntry(
                format_bucket="standalone_text",
                account_lift=1.0,
                niche_lift=None,
                niche_trend_status=None,
                niche_confidence=None,
                post_count=14,
                account_confidence="B",
                divergence_signal="NEUTRAL",
            ),
            FormatLiftEntry(
                format_bucket="short_clip",
                account_lift=1.0,
                niche_lift=None,
                niche_trend_status=None,
                niche_confidence=None,
                post_count=14,
                account_confidence="B",
                divergence_signal="NEUTRAL",
            ),
        ],
        missing_niche_formats=[],
        generated_at=_iso(0),
    )

    with patch("sable.diagnose.runner.compute_account_format_lift", return_value=healthy_report):
        report = run_diagnosis(
            handle="@alice",
            org="",
            days=30,
            pulse_db_path=pulse_db,
            meta_db_path=None,
            vault_root=None,
            sable_db_path=tmp_path / "sable.db",
        )

    warnings = [f for f in report.findings if f.severity == FindingSeverity.WARNING]
    assert len(warnings) == 0


# ---------------------------------------------------------------------------
# Test 11: artifact saved
# ---------------------------------------------------------------------------

def test_artifact_saved(tmp_path):
    """save_diagnosis_artifact inserts a row in sable.db with artifact_type='account_diagnosis'."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    conn.execute("INSERT INTO orgs (org_id, display_name) VALUES ('testorg', 'Test Org')")
    conn.commit()

    report = DiagnosisReport(
        handle="@alice",
        org="testorg",
        days=30,
        generated_at=_iso(0),
        findings=[
            Finding(section="Posting Cadence", severity=FindingSeverity.WARNING, message="Test"),
        ],
    )

    with patch("sable.diagnose.runner.get_db", return_value=conn):
        artifact_id = save_diagnosis_artifact(report, "testorg")

    assert artifact_id != ""
    row = conn.execute(
        "SELECT artifact_type, metadata_json FROM artifacts WHERE artifact_id = ?",
        (int(artifact_id),),
    ).fetchone()
    assert row is not None
    assert row["artifact_type"] == "account_diagnosis"

    import json
    meta = json.loads(row["metadata_json"])
    assert meta["handle"] == "@alice"
    assert meta["warning_count"] == 1


# ---------------------------------------------------------------------------
# Test 12: insufficient data — graceful handling
# ---------------------------------------------------------------------------

def test_insufficient_data_graceful(tmp_path):
    """3 posts total → Section 5 returns INFO 'insufficient data', no crash."""
    pulse_db = _make_pulse_db(tmp_path)
    conn = sqlite3.connect(str(pulse_db))
    for i in range(3):
        _insert_post(conn, f"p{i}", "@alice", days_ago=i + 1)
        _insert_snapshot(conn, f"p{i}", likes=100)
    conn.commit()
    conn.close()

    findings = _audit_engagement_trend("@alice", pulse_db)

    assert len(findings) == 1
    assert findings[0].severity == FindingSeverity.INFO
    assert "insufficient" in findings[0].message.lower()


# ---------------------------------------------------------------------------
# Test 13: suggested_command — over-indexed WARNING
# ---------------------------------------------------------------------------

def test_suggested_command_over_indexed():
    """Over-indexed WARNING gets --watchlist-wire command."""
    findings = [
        Finding(
            section="Format Portfolio",
            severity=FindingSeverity.WARNING,
            message="Over-indexed on standalone_text (8/10 posts, 80%)",
        )
    ]
    _attach_suggested_commands(findings, "@alice", "testorg")
    assert findings[0].suggested_command is not None
    assert "--watchlist-wire" in findings[0].suggested_command
    assert "@alice" in findings[0].suggested_command


# ---------------------------------------------------------------------------
# Test 14: suggested_command — stale inventory WARNING
# ---------------------------------------------------------------------------

def test_suggested_command_stale_inventory():
    """Stale inventory WARNING gets vault search --available command."""
    findings = [
        Finding(
            section="Vault Utilization",
            severity=FindingSeverity.WARNING,
            message="Stale inventory: 5 unposted note(s) older than 7 days",
        )
    ]
    _attach_suggested_commands(findings, "@alice", "testorg")
    cmd = findings[0].suggested_command
    assert cmd is not None
    assert "vault search" in cmd
    assert "@alice" in cmd
    assert "--available" in cmd


# ---------------------------------------------------------------------------
# Test 15: suggested_command — hot topic WARNING extracts topic
# ---------------------------------------------------------------------------

def test_suggested_command_hot_topic():
    """Hot topic WARNING extracts topic name into --topic flag."""
    findings = [
        Finding(
            section="Vault Utilization",
            severity=FindingSeverity.WARNING,
            message="Hot topic sitting idle: note on 'solana' matches niche signal but is unposted",
        )
    ]
    _attach_suggested_commands(findings, "@alice", "testorg")
    cmd = findings[0].suggested_command
    assert cmd is not None
    assert "--topic" in cmd
    assert "solana" in cmd


# ---------------------------------------------------------------------------
# Test 16: suggested_command — topic gap INFO with --watchlist-wire
# ---------------------------------------------------------------------------

def test_suggested_command_topic_gap():
    """Topic gap INFO gets --topic and --watchlist-wire command."""
    findings = [
        Finding(
            section="Topic Freshness",
            severity=FindingSeverity.INFO,
            message="Topic gap: 'defi rails' trending in niche but absent from recent posts",
        )
    ]
    _attach_suggested_commands(findings, "@bob", "psy")
    cmd = findings[0].suggested_command
    assert cmd is not None
    assert "--topic" in cmd
    assert "defi rails" in cmd
    assert "--watchlist-wire" in cmd
    assert "@bob" in cmd


# ---------------------------------------------------------------------------
# Test 17: suggested_command — niche surging format unused INFO
# ---------------------------------------------------------------------------

def test_suggested_command_niche_format():
    """Niche surging format unused INFO gets --format command."""
    findings = [
        Finding(
            section="Format Portfolio",
            severity=FindingSeverity.INFO,
            message="Niche surging format unused by account: short_clip",
        )
    ]
    _attach_suggested_commands(findings, "@carol", "grvt")
    cmd = findings[0].suggested_command
    assert cmd is not None
    assert "--format" in cmd
    assert "short_clip" in cmd
    assert "@carol" in cmd


# ---------------------------------------------------------------------------
# Test 18: render_diagnosis shows → Run: line inline
# ---------------------------------------------------------------------------

def test_render_diagnosis_shows_action_line():
    """render_diagnosis emits '→ Run:' line for findings with suggested_command."""
    report = DiagnosisReport(
        handle="@alice",
        org="testorg",
        days=30,
        generated_at=_iso(0),
        findings=[
            Finding(
                section="Posting Cadence",
                severity=FindingSeverity.WARNING,
                message="Low activity: 0.10 posts/day avg over 30 days",
                suggested_command="sable write @alice --watchlist-wire",
            )
        ],
    )
    output = render_diagnosis(report)
    assert "→ Run:" in output
    assert "sable write @alice --watchlist-wire" in output


# ---------------------------------------------------------------------------
# Test 19: render_diagnosis Quick Actions block
# ---------------------------------------------------------------------------

def test_render_diagnosis_quick_actions_block():
    """render_diagnosis emits 'Quick Actions:' section for WARNING findings with commands."""
    report = DiagnosisReport(
        handle="@alice",
        org="testorg",
        days=30,
        generated_at=_iso(0),
        findings=[
            Finding(
                section="Posting Cadence",
                severity=FindingSeverity.WARNING,
                message="Low activity: 0.10 posts/day avg over 30 days",
                suggested_command="sable write @alice --watchlist-wire",
            ),
            Finding(
                section="Format Portfolio",
                severity=FindingSeverity.INFO,
                message="Niche surging format unused by account: short_clip",
                suggested_command="sable write @alice --format short_clip",
            ),
        ],
    )
    output = render_diagnosis(report)
    assert "Quick Actions:" in output
    # WARNING command appears in Quick Actions; INFO command does NOT
    assert "1. sable write @alice --watchlist-wire" in output
    # INFO finding's command should NOT appear in Quick Actions block
    lines = output.splitlines()
    qa_start = next(i for i, line in enumerate(lines) if "Quick Actions:" in line)
    qa_section = "\n".join(lines[qa_start:])
    assert "short_clip" not in qa_section
