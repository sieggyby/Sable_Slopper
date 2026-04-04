"""Tests for sable.cadence.store — persistence."""
from __future__ import annotations

import sqlite3

from sable.pulse.meta.db import _SCHEMA
from sable.cadence.store import upsert_cadence


def _make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def _make_row(handle="@test", org="org", gradient=0.5):
    return {
        "author_handle": handle,
        "org": org,
        "posts_recent_half": 5,
        "posts_prior_half": 10,
        "median_lift_recent": 3.0,
        "median_lift_prior": 5.0,
        "vol_drop": 0.5,
        "eng_drop": 0.4,
        "fmt_reg": 0.3,
        "silence_gradient": gradient,
        "insufficient_data": None,
        "window_days": 30,
    }


def test_insert():
    """Basic insert works."""
    conn = _make_conn()
    count = upsert_cadence([_make_row()], conn)
    assert count == 1

    rows = conn.execute("SELECT * FROM author_cadence").fetchall()
    assert len(rows) == 1
    assert rows[0]["author_handle"] == "@test"


def test_replace_on_conflict():
    """INSERT OR REPLACE updates existing row."""
    conn = _make_conn()
    upsert_cadence([_make_row(gradient=0.3)], conn)
    upsert_cadence([_make_row(gradient=0.9)], conn)

    rows = conn.execute("SELECT * FROM author_cadence").fetchall()
    assert len(rows) == 1
    assert rows[0]["silence_gradient"] == 0.9


def test_multiple_authors():
    """Multiple authors inserted."""
    conn = _make_conn()
    rows = [_make_row(handle=f"@a{i}") for i in range(5)]
    count = upsert_cadence(rows, conn)
    assert count == 5

    db_rows = conn.execute("SELECT * FROM author_cadence").fetchall()
    assert len(db_rows) == 5
