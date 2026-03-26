"""Entity tag helpers for sable.db."""
from __future__ import annotations

import sqlite3

# Tags in this set use replace-current semantics: deactivate prior rows, then INSERT.
# All other tags use append-history semantics: INSERT directly.
_REPLACE_CURRENT_TAGS: frozenset[str] = frozenset({
    "high_lift_account",
    "top_contributor",
    "team_member",
    "cabal_member",
    "watchlist_account",
    "bd_prospect",
})

_ACTIVE_PREDICATE = "is_current = 1 AND (expires_at IS NULL OR expires_at > datetime('now'))"


def _record_tag_history(
    conn: sqlite3.Connection,
    entity_id: str,
    org_id: str,
    tag: str,
    change_type: str,
    source: str | None,
    confidence: float,
    expires_at: str | None,
) -> None:
    try:
        conn.execute(
            """
            INSERT INTO entity_tag_history
                (entity_id, org_id, tag, change_type, source, confidence, expires_at, effective_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (entity_id, org_id, tag, change_type, source, confidence, expires_at),
        )
    except sqlite3.OperationalError:
        pass  # entity_tag_history absent before migration 008


def add_tag(
    conn: sqlite3.Connection,
    entity_id: str,
    tag: str,
    source: str | None = None,
    confidence: float = 1.0,
    expires_at: str | None = None,
) -> None:
    org_row = conn.execute("SELECT org_id FROM entities WHERE entity_id=?", (entity_id,)).fetchone()
    org_id = org_row["org_id"] if org_row else ""

    if tag in _REPLACE_CURRENT_TAGS:
        # Deactivate all prior active rows for this (entity, tag)
        conn.execute(
            f"""
            UPDATE entity_tags
            SET is_current = 0, deactivated_at = datetime('now')
            WHERE entity_id = ? AND tag = ? AND {_ACTIVE_PREDICATE}
            """,
            (entity_id, tag),
        )
        _record_tag_history(conn, entity_id, org_id, tag, "replaced", source, confidence, expires_at)
    else:
        _record_tag_history(conn, entity_id, org_id, tag, "added", source, confidence, expires_at)

    conn.execute(
        """
        INSERT INTO entity_tags (entity_id, tag, source, confidence, is_current, expires_at)
        VALUES (?, ?, ?, ?, 1, ?)
        """,
        (entity_id, tag, source, confidence, expires_at),
    )
    conn.execute(
        "UPDATE entities SET updated_at=datetime('now') WHERE entity_id=?",
        (entity_id,),
    )
    conn.commit()


def get_active_tags(conn: sqlite3.Connection, entity_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        f"""
        SELECT * FROM entity_tags
        WHERE entity_id = ? AND {_ACTIVE_PREDICATE}
        ORDER BY added_at
        """,
        (entity_id,),
    ).fetchall()


def get_entities_by_tag(
    conn: sqlite3.Connection,
    org_id: str,
    tag: str,
) -> list[sqlite3.Row]:
    return conn.execute(
        f"""
        SELECT DISTINCT e.entity_id, e.display_name, e.status, e.org_id
        FROM entities e
        JOIN entity_tags t ON e.entity_id = t.entity_id
        WHERE e.org_id = ?
          AND t.tag = ?
          AND {_ACTIVE_PREDICATE.replace('is_current', 't.is_current')
               .replace('expires_at', 't.expires_at')}
          AND e.status != 'archived'
        """,
        (org_id, tag),
    ).fetchall()
