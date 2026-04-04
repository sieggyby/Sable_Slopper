"""Register content artifacts in sable.db."""
from __future__ import annotations

import json
import logging
import sqlite3

logger = logging.getLogger(__name__)


def register_content_artifact(
    org_id: str,
    artifact_type: str,
    path: str | None,
    metadata: dict | None = None,
) -> None:
    """Register a content artifact in sable.db. Non-fatal on failure.

    Call after meme/clip production when org is resolvable.
    """
    conn = None
    try:
        from sable.platform.db import get_db
        conn = get_db()
        conn.execute(
            """INSERT INTO artifacts
               (org_id, artifact_type, path, metadata_json, stale, degraded)
               VALUES (?, ?, ?, ?, 0, 0)""",
            (org_id, artifact_type, path, json.dumps(metadata or {})),
        )
        conn.commit()
    except Exception as e:
        logger.warning("Failed to register artifact for org %s: %s", org_id, e)
    finally:
        if conn is not None:
            conn.close()
