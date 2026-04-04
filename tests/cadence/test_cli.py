"""CLI smoke tests for sable silence-gradient command."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from click.testing import CliRunner

from sable.pulse.meta.db import _SCHEMA
from sable.cadence.cli import silence_gradient_command

_NOW = datetime.now(timezone.utc)


def _ts(days_ago: int = 0) -> str:
    return (_NOW - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M:%S")


def _make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def _seed(conn, org="test_org"):
    """Seed authors with declining + stable patterns."""
    # Declining author
    for i in range(10):
        tid = str(uuid.uuid4())[:12]
        conn.execute(
            """INSERT INTO scanned_tweets
               (tweet_id, org, author_handle, posted_at, text, total_lift, format_bucket,
                likes, replies, reposts, quotes, bookmarks)
               VALUES (?, ?, '@declining', ?, 'test', 5.0, 'standalone_text', 10, 5, 3, 1, 0)""",
            (tid, org, _ts(16 + i)),
        )
    tid = str(uuid.uuid4())[:12]
    conn.execute(
        """INSERT INTO scanned_tweets
           (tweet_id, org, author_handle, posted_at, text, total_lift, format_bucket,
            likes, replies, reposts, quotes, bookmarks)
           VALUES (?, ?, '@declining', ?, 'test', 2.0, 'standalone_text', 10, 5, 3, 1, 0)""",
        (tid, org, _ts(1)),
    )

    # Stable author
    for i in range(30):
        tid = str(uuid.uuid4())[:12]
        conn.execute(
            """INSERT INTO scanned_tweets
               (tweet_id, org, author_handle, posted_at, text, total_lift, format_bucket,
                likes, replies, reposts, quotes, bookmarks)
               VALUES (?, ?, '@stable', ?, 'test', 5.0, 'standalone_text', 10, 5, 3, 1, 0)""",
            (tid, org, _ts(i)),
        )
    conn.commit()


def _invoke(conn, args):
    runner = CliRunner()
    with patch("sable.pulse.meta.db.get_conn", return_value=conn), \
         patch("sable.pulse.meta.db.migrate"):
        return runner.invoke(silence_gradient_command, args)


def test_basic_output():
    """Basic invocation shows table."""
    conn = _make_conn()
    _seed(conn)
    result = _invoke(conn, ["--org", "test_org"])
    assert result.exit_code == 0
    assert "Silence Gradient" in result.output


def test_empty_org():
    """Empty org shows warning."""
    conn = _make_conn()
    result = _invoke(conn, ["--org", "empty"])
    assert result.exit_code == 0
    assert "No authors" in result.output


def test_include_insufficient():
    """--include-insufficient shows all authors."""
    conn = _make_conn()
    _seed(conn)
    result = _invoke(conn, ["--org", "test_org", "--include-insufficient"])
    assert result.exit_code == 0


def test_output_json(tmp_path):
    """--output writes JSON."""
    conn = _make_conn()
    _seed(conn)
    output = tmp_path / "report.json"
    result = _invoke(conn, ["--org", "test_org", "--output", str(output)])
    assert result.exit_code == 0
    assert output.exists()
    data = json.loads(output.read_text())
    assert len(data) >= 1


def test_odd_window_error():
    """Odd window_days → error."""
    conn = _make_conn()
    result = _invoke(conn, ["--org", "test_org", "--window", "31"])
    assert result.exit_code != 0
