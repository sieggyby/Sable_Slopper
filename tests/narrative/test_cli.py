"""CLI smoke tests for sable narrative commands."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import yaml
from click.testing import CliRunner

from sable.pulse.meta.db import _SCHEMA
from sable.narrative.cli import narrative_group


def _make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def _invoke(conn, args):
    runner = CliRunner()
    with patch("sable.pulse.meta.db.get_conn", return_value=conn), \
         patch("sable.pulse.meta.db.migrate"):
        return runner.invoke(narrative_group, args)


def _write_beats(path: Path, beats: list[dict]) -> Path:
    beats_file = path / "narrative_beats.yaml"
    beats_file.write_text(yaml.dump({"beats": beats}), encoding="utf-8")
    return beats_file


def test_score_missing_beats(tmp_path):
    """Score with missing beats file shows error."""
    conn = _make_conn()
    result = _invoke(conn, ["score", "--org", "test", "--beats", str(tmp_path / "nope.yaml")])
    assert result.exit_code != 0
    assert "not found" in result.output


def test_score_malformed_beats(tmp_path):
    """Score with malformed beats file shows error."""
    conn = _make_conn()
    bad_file = tmp_path / "bad.yaml"
    bad_file.write_text("beats: not_a_list", encoding="utf-8")
    result = _invoke(conn, ["score", "--org", "test", "--beats", str(bad_file)])
    assert result.exit_code != 0
    assert "Invalid" in result.output


def test_score_insufficient_data(tmp_path):
    """Score with empty corpus shows insufficient data."""
    conn = _make_conn()
    beats_file = _write_beats(tmp_path, [{"name": "test", "keywords": ["foo"]}])
    result = _invoke(conn, ["score", "--org", "empty", "--beats", str(beats_file)])
    assert result.exit_code == 0
    assert "Insufficient data" in result.output


def test_score_output_file(tmp_path):
    """--output writes JSON report."""
    import uuid
    from datetime import datetime, timedelta, timezone

    conn = _make_conn()
    now = datetime.now(timezone.utc)

    # Seed enough data
    for i in range(15):
        for j in range(5):
            tid = str(uuid.uuid4())[:12]
            ts = (now - timedelta(days=j)).strftime("%Y-%m-%d %H:%M:%S")
            text = "real yield staking" if i < 5 and j == 0 else "crypto building"
            conn.execute(
                """INSERT INTO scanned_tweets
                   (tweet_id, org, author_handle, posted_at, text, likes, replies, reposts, quotes, bookmarks)
                   VALUES (?, ?, ?, ?, ?, 10, 5, 3, 1, 0)""",
                (tid, "test_org", f"@a{i}", ts, text),
            )
    conn.commit()

    beats_file = _write_beats(tmp_path, [{"name": "yield", "keywords": ["real yield"]}])
    output = tmp_path / "report.json"
    result = _invoke(conn, [
        "score", "--org", "test_org", "--beats", str(beats_file), "--output", str(output),
    ])

    assert result.exit_code == 0
    assert output.exists()
    data = json.loads(output.read_text())
    assert len(data) == 1
    assert data[0]["beat"] == "yield"
    assert data[0]["uptake_score"] > 0
