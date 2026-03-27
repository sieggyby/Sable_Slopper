"""Tests for compute_signal_gaps and render_signal_gaps in sable.vault.gaps."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from sable.pulse.meta.db import _SCHEMA


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _NoClose:
    """Proxy that makes close() a no-op so the in-memory DB stays alive."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self.row_factory = conn.row_factory

    def execute(self, *a, **kw):
        return self._conn.execute(*a, **kw)

    def executemany(self, *a, **kw):
        return self._conn.executemany(*a, **kw)

    def executescript(self, *a, **kw):
        return self._conn.executescript(*a, **kw)

    def commit(self):
        return self._conn.commit()

    def close(self):
        pass

    def __enter__(self):
        return self._conn.__enter__()

    def __exit__(self, *a):
        return self._conn.__exit__(*a)


def _make_meta_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def _insert_scan_run(conn, org, completed=True, failed=False):
    claude_raw = "FAILED: err" if failed else None
    completed_at = "2026-01-01 12:00:00" if completed else None
    cursor = conn.execute(
        """INSERT INTO scan_runs (org, started_at, completed_at, mode, claude_raw)
           VALUES (?, '2026-01-01 11:00:00', ?, 'full', ?)""",
        (org, completed_at, claude_raw),
    )
    conn.commit()
    return cursor.lastrowid


def _insert_signal(conn, org, scan_id, term, avg_lift=2.0, acceleration=1.5,
                   unique_authors=3, mention_count=6):
    conn.execute(
        """INSERT INTO topic_signals (org, scan_id, term, mention_count, unique_authors,
           avg_lift, prev_scan_mentions, acceleration)
           VALUES (?, ?, ?, ?, ?, ?, 0, ?)""",
        (org, scan_id, term, mention_count, unique_authors, avg_lift, acceleration),
    )
    conn.commit()


def _make_vault_note(vault_path: Path, note_id: str, topics=None, keywords=None,
                     topic=None, caption=None) -> Path:
    """Create a minimal vault content note."""
    content_dir = vault_path / "content"
    content_dir.mkdir(parents=True, exist_ok=True)

    fm_lines = [f"id: {note_id}", "type: clip"]
    if topics:
        topics_str = "\n".join(f"  - {t}" for t in topics)
        fm_lines.append(f"topics:\n{topics_str}")
    if keywords:
        kw_str = "\n".join(f"  - {k}" for k in keywords)
        fm_lines.append(f"keywords:\n{kw_str}")
    if topic:
        fm_lines.append(f"topic: {topic}")
    if caption:
        fm_lines.append(f"caption: {caption}")

    fm = "\n".join(fm_lines)
    note_path = content_dir / f"{note_id}.md"
    note_path.write_text(f"---\n{fm}\n---\n\nBody.\n", encoding="utf-8")
    return note_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_empty_vault_all_signals_are_gaps(tmp_path):
    """When vault has no notes, all signals should be returned as gaps."""
    from sable.vault.gaps import compute_signal_gaps

    vault_path = tmp_path / "vault"
    vault_path.mkdir()

    conn = _make_meta_conn()
    proxy = _NoClose(conn)

    scan_id = _insert_scan_run(conn, "testorg")
    _insert_signal(conn, "testorg", scan_id, "defi", avg_lift=2.0, acceleration=1.5,
                   unique_authors=3)
    _insert_signal(conn, "testorg", scan_id, "staking", avg_lift=1.5, acceleration=1.0,
                   unique_authors=2)

    gaps = compute_signal_gaps("testorg", vault_path=vault_path, meta_db=proxy,
                                min_unique_authors=1)

    terms = [g.term for g in gaps]
    assert "defi" in terms
    assert "staking" in terms


def test_full_coverage_empty_gaps(tmp_path):
    """When all signal terms are covered in the vault, no gaps returned."""
    from sable.vault.gaps import compute_signal_gaps

    vault_path = tmp_path / "vault"
    _make_vault_note(vault_path, "n1", topics=["defi", "staking"])

    conn = _make_meta_conn()
    proxy = _NoClose(conn)

    scan_id = _insert_scan_run(conn, "testorg")
    _insert_signal(conn, "testorg", scan_id, "defi", unique_authors=3)
    _insert_signal(conn, "testorg", scan_id, "staking", unique_authors=3)

    gaps = compute_signal_gaps("testorg", vault_path=vault_path, meta_db=proxy,
                                min_unique_authors=1)
    assert gaps == []


def test_partial_coverage_correct_gaps(tmp_path):
    """Only uncovered signal terms appear as gaps."""
    from sable.vault.gaps import compute_signal_gaps

    vault_path = tmp_path / "vault"
    _make_vault_note(vault_path, "n1", topics=["defi"])

    conn = _make_meta_conn()
    proxy = _NoClose(conn)

    scan_id = _insert_scan_run(conn, "testorg")
    _insert_signal(conn, "testorg", scan_id, "defi", unique_authors=3)
    _insert_signal(conn, "testorg", scan_id, "nft royalties", unique_authors=3)

    gaps = compute_signal_gaps("testorg", vault_path=vault_path, meta_db=proxy,
                                min_unique_authors=1)

    terms = [g.term for g in gaps]
    assert "nft royalties" in terms
    assert "defi" not in terms


def test_no_meta_db_returns_empty(tmp_path, monkeypatch):
    """When meta_db=None and no meta.db file exists, returns []."""
    from sable.vault.gaps import compute_signal_gaps

    vault_path = tmp_path / "vault"
    vault_path.mkdir()

    # Ensure the meta_db_path points to a non-existent file
    fake_db = tmp_path / "nonexistent_meta.db"

    monkeypatch.setattr(
        "sable.vault.gaps.Path",
        lambda *a, **kw: fake_db if "meta" in str(a) else Path(*a, **kw),
    )
    # Patch _meta_db_path to return non-existent path
    import sable.shared.paths as paths_mod
    monkeypatch.setattr(paths_mod, "meta_db_path", lambda: fake_db)

    gaps = compute_signal_gaps("testorg", vault_path=vault_path, meta_db=None)
    assert gaps == []


def test_min_unique_authors_filter(tmp_path):
    """Signals with unique_authors < min_unique_authors are excluded."""
    from sable.vault.gaps import compute_signal_gaps

    vault_path = tmp_path / "vault"
    vault_path.mkdir()

    conn = _make_meta_conn()
    proxy = _NoClose(conn)

    scan_id = _insert_scan_run(conn, "testorg")
    _insert_signal(conn, "testorg", scan_id, "popular_term", unique_authors=5)
    _insert_signal(conn, "testorg", scan_id, "lone_term", unique_authors=1)

    gaps = compute_signal_gaps("testorg", vault_path=vault_path, meta_db=proxy,
                                min_unique_authors=2)

    terms = [g.term for g in gaps]
    assert "popular_term" in terms
    assert "lone_term" not in terms


def test_sorted_by_signal_score_descending(tmp_path):
    """Gaps are sorted by signal_score (avg_lift * max(accel,0.1) * unique_authors) desc."""
    from sable.vault.gaps import compute_signal_gaps

    vault_path = tmp_path / "vault"
    vault_path.mkdir()

    conn = _make_meta_conn()
    proxy = _NoClose(conn)

    scan_id = _insert_scan_run(conn, "testorg")
    # score_high = 3.0 * 2.0 * 4 = 24.0
    # score_mid  = 2.0 * 1.5 * 3 = 9.0
    # score_low  = 1.0 * 1.0 * 1 = 1.0
    _insert_signal(conn, "testorg", scan_id, "low_term", avg_lift=1.0, acceleration=1.0, unique_authors=1)
    _insert_signal(conn, "testorg", scan_id, "high_term", avg_lift=3.0, acceleration=2.0, unique_authors=4)
    _insert_signal(conn, "testorg", scan_id, "mid_term", avg_lift=2.0, acceleration=1.5, unique_authors=3)

    gaps = compute_signal_gaps("testorg", vault_path=vault_path, meta_db=proxy,
                                min_unique_authors=1)

    terms = [g.term for g in gaps]
    assert terms == ["high_term", "mid_term", "low_term"]


def test_render_signal_gaps_empty():
    """render_signal_gaps with empty list shows no-gaps message."""
    from sable.vault.gaps import render_signal_gaps
    output = render_signal_gaps([], "testorg")
    assert "no" in output.lower() or "No" in output


def test_render_signal_gaps_shows_terms(tmp_path):
    """render_signal_gaps includes term names in output."""
    from sable.vault.gaps import VaultSignalGap, render_signal_gaps

    gaps = [
        VaultSignalGap(
            term="defi yields",
            signal_score=12.0,
            avg_lift=2.0,
            acceleration=2.0,
            unique_authors=3,
            recommended_type="explainer",
        )
    ]
    output = render_signal_gaps(gaps, "testorg")
    assert "defi yields" in output
    assert "testorg" in output
