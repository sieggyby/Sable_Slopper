"""CLI tests for sable pulse meta watchlist amplifiers."""
from __future__ import annotations

import json
import sqlite3
from unittest.mock import patch

from click.testing import CliRunner

from sable.pulse.meta.db import _SCHEMA
from sable.pulse.meta.cli import meta_group


def _make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def _seed_data(conn):
    """Insert 3 authors with distinct amplification profiles."""
    import uuid
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    for author, reposts, replies, quotes in [
        ("@alpha", 50, 5, 2),
        ("@beta", 10, 50, 5),
        ("@gamma", 5, 5, 50),
    ]:
        for day_offset in range(3):
            tid = str(uuid.uuid4())[:12]
            ts = (now - timedelta(days=day_offset)).strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                """INSERT INTO scanned_tweets
                   (tweet_id, org, author_handle, posted_at, likes, replies,
                    reposts, quotes, bookmarks, text)
                   VALUES (?, 'test_org', ?, ?, 10, ?, ?, ?, 0, 'test')""",
                (tid, author, ts, replies, reposts, quotes),
            )
    conn.commit()


def _invoke(conn, org="test_org", extra_args=None):
    """Invoke the amplifiers CLI command with patched DB."""
    args = ["watchlist", "amplifiers", "--org", org]
    if extra_args:
        args.extend(extra_args)
    runner = CliRunner()
    with patch("sable.pulse.meta.db.get_conn", return_value=conn), \
         patch("sable.pulse.meta.db.migrate"), \
         patch("sable.pulse.meta.amplifiers.sable_cfg") as mock_cfg:
        mock_cfg.load_config.return_value = {}
        return runner.invoke(meta_group, args)


def test_amplifiers_cli_table_output():
    """CLI renders a Rich table with ranked amplifiers."""
    conn = _make_conn()
    _seed_data(conn)
    result = _invoke(conn)
    assert result.exit_code == 0, result.output
    assert "Amp Score" in result.output
    # At least one author should appear
    assert "@alpha" in result.output or "@beta" in result.output or "@gamma" in result.output


def test_amplifiers_cli_json_output():
    """--json flag produces valid JSON array."""
    conn = _make_conn()
    _seed_data(conn)
    result = _invoke(conn, extra_args=["--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert isinstance(data, list)
    assert len(data) == 3
    assert "amp_score" in data[0]
    assert "author" in data[0]


def test_amplifiers_cli_top_truncation():
    """--top 1 returns only the top amplifier."""
    conn = _make_conn()
    _seed_data(conn)
    result = _invoke(conn, extra_args=["--top", "1", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert len(data) == 1


def test_amplifiers_cli_empty_org():
    """Empty org shows informative message."""
    conn = _make_conn()
    result = _invoke(conn, org="empty_org")
    assert result.exit_code == 0
    assert "No tweet data" in result.output
