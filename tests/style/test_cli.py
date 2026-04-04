"""CLI smoke tests for sable style-delta command."""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from sable.pulse.db import _SCHEMA as PULSE_SCHEMA
from sable.pulse.meta.db import _SCHEMA as META_SCHEMA
from sable.style.cli import style_delta_command

_NOW = datetime.now(timezone.utc)


def _ts(days_ago: int = 0) -> str:
    return (_NOW - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M:%S")


def _make_pulse_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(PULSE_SCHEMA)
    return conn


def _make_meta_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(META_SCHEMA)
    return conn


def _seed(pulse_conn, meta_conn, handle="@test", org="test_org"):
    """Seed both DBs with enough data for fingerprinting."""
    for i in range(12):
        pid = str(uuid.uuid4())[:12]
        ct = "text" if i < 8 else "clip"
        pulse_conn.execute(
            "INSERT INTO posts (id, account_handle, sable_content_type, posted_at) VALUES (?, ?, ?, ?)",
            (pid, handle, ct, _ts(i)),
        )
    pulse_conn.commit()

    for i in range(10):
        for j in range(6):
            tid = str(uuid.uuid4())[:12]
            fmt = "standalone_text" if j < 4 else "short_clip"
            meta_conn.execute(
                """INSERT INTO scanned_tweets
                   (tweet_id, org, author_handle, posted_at, text, format_bucket, total_lift,
                    has_image, has_video, has_link, is_thread, thread_length,
                    likes, replies, reposts, quotes, bookmarks)
                   VALUES (?, ?, ?, ?, 'test', ?, ?, 0, 0, 0, 0, 1, 10, 5, 3, 1, 0)""",
                (tid, org, f"@a{i}", _ts(j), fmt, float(5 + i)),
            )
    meta_conn.commit()


def test_style_delta_smoke(tmp_path):
    """Full style-delta run with seeded data."""
    pulse = _make_pulse_conn()
    meta = _make_meta_conn()
    _seed(pulse, meta)

    # Write DBs to tmp files
    pulse_path = tmp_path / "pulse.db"
    meta_path = tmp_path / "meta.db"

    # Copy in-memory to file
    file_pulse = sqlite3.connect(str(pulse_path))
    pulse.backup(file_pulse)
    file_pulse.close()

    file_meta = sqlite3.connect(str(meta_path))
    meta.backup(file_meta)
    file_meta.close()

    runner = CliRunner()
    with patch("sable.shared.paths.pulse_db_path", return_value=pulse_path), \
         patch("sable.shared.paths.meta_db_path", return_value=meta_path):
        result = runner.invoke(style_delta_command, ["--handle", "@test", "--org", "test_org"])

    assert result.exit_code == 0
    assert "Style Delta" in result.output


def test_style_delta_output(tmp_path):
    """--output writes markdown report."""
    pulse = _make_pulse_conn()
    meta = _make_meta_conn()
    _seed(pulse, meta)

    pulse_path = tmp_path / "pulse.db"
    meta_path = tmp_path / "meta.db"

    file_pulse = sqlite3.connect(str(pulse_path))
    pulse.backup(file_pulse)
    file_pulse.close()

    file_meta = sqlite3.connect(str(meta_path))
    meta.backup(file_meta)
    file_meta.close()

    output = tmp_path / "report.md"
    runner = CliRunner()
    with patch("sable.shared.paths.pulse_db_path", return_value=pulse_path), \
         patch("sable.shared.paths.meta_db_path", return_value=meta_path):
        result = runner.invoke(style_delta_command, [
            "--handle", "@test", "--org", "test_org", "--output", str(output),
        ])

    assert result.exit_code == 0
    assert output.exists()
    content = output.read_text()
    assert "Style Delta" in content
