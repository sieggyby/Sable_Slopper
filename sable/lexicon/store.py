"""Lexicon store — CRUD for lexicon_terms table in meta.db."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


def upsert_term(
    conn: sqlite3.Connection,
    org: str,
    term: str,
    category: str | None = None,
    gloss: str | None = None,
    lsr: float | None = None,
) -> None:
    """Insert or update a lexicon term."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO lexicon_terms (org, term, category, gloss, lsr, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(org, term) DO UPDATE SET
               category = COALESCE(excluded.category, category),
               gloss = COALESCE(excluded.gloss, gloss),
               lsr = COALESCE(excluded.lsr, lsr),
               updated_at = excluded.updated_at""",
        (org, term, category, gloss, lsr, now),
    )
    conn.commit()


def list_terms(
    org: str,
    conn: sqlite3.Connection | None = None,
) -> list[dict]:
    """List all lexicon terms for an org, sorted by LSR descending."""
    if conn is None:
        from sable.pulse.meta.db import get_conn
        conn = get_conn()

    rows = conn.execute(
        """SELECT term, category, gloss, lsr, updated_at
           FROM lexicon_terms WHERE org = ? ORDER BY lsr DESC""",
        (org,),
    ).fetchall()
    return [dict(r) for r in rows]


def remove_term(conn: sqlite3.Connection, org: str, term: str) -> bool:
    """Remove a term. Returns True if a row was deleted."""
    cursor = conn.execute(
        "DELETE FROM lexicon_terms WHERE org = ? AND term = ?",
        (org, term),
    )
    conn.commit()
    return cursor.rowcount > 0


def add_manual_term(
    conn: sqlite3.Connection,
    org: str,
    term: str,
    gloss: str = "",
) -> None:
    """Add a manually defined term (category='manual')."""
    upsert_term(conn, org, term, category="manual", gloss=gloss)
