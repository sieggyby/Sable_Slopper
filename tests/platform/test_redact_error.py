"""Tests for platform.errors.redact_error — secret scrubbing before DB persistence."""
from __future__ import annotations


def test_redact_error_strips_anthropic_api_key_assignment():
    """ANTHROPIC_API_KEY=<value> is redacted; the key name is preserved."""
    from sable.platform.errors import redact_error

    raw = "Connection failed. ANTHROPIC_API_KEY=test-secret was rejected."
    redacted = redact_error(raw)

    assert "test-secret" not in redacted
    assert "ANTHROPIC_API_KEY" in redacted
    assert "[REDACTED]" in redacted


def test_redact_error_strips_anthropic_key_prefix():
    """Real sk-ant-... key shapes are redacted."""
    from sable.platform.errors import redact_error

    key = "sk-ant-api03-abcdefghijklmnopqrstuvwxyz"
    raw = f"Error: api key {key} is invalid"
    redacted = redact_error(raw)

    assert key not in redacted
    assert "[REDACTED]" in redacted


def test_redact_error_strips_replicate_token():
    """REPLICATE_API_TOKEN=<value> is redacted."""
    from sable.platform.errors import redact_error

    raw = "Auth failed: REPLICATE_API_TOKEN=r8_XyzAbcDef1234567890"
    redacted = redact_error(raw)

    assert "r8_XyzAbcDef1234567890" not in redacted
    assert "REPLICATE_API_TOKEN" in redacted


def test_redact_error_strips_bearer_token():
    """Bearer tokens long enough to be real credentials are redacted."""
    from sable.platform.errors import redact_error

    raw = "Request failed: Authorization: Bearer eyJhbGciOiJSUzI1NiJ9.verylongtoken123"
    redacted = redact_error(raw)

    assert "eyJhbGciOiJSUzI1NiJ9.verylongtoken123" not in redacted
    assert "[REDACTED]" in redacted


def test_redact_error_is_noop_for_clean_messages():
    """Ordinary error messages pass through unchanged."""
    from sable.platform.errors import redact_error

    clean = "SQLite error: no such table: posts"
    assert redact_error(clean) == clean


def test_redact_error_handles_empty_string():
    from sable.platform.errors import redact_error

    assert redact_error("") == ""


def test_fail_scan_run_redacts_secret_in_claude_raw(tmp_path):
    """fail_scan_run stores redacted error in meta.db scan_runs.claude_raw."""
    import sqlite3
    from sable.pulse.meta.db import _SCHEMA, fail_scan_run, create_scan_run

    db = tmp_path / "meta.db"
    # Initialise schema
    setup_conn = sqlite3.connect(str(db))
    setup_conn.executescript(_SCHEMA)
    setup_conn.commit()
    setup_conn.close()

    def make_conn():
        c = sqlite3.connect(str(db))
        c.row_factory = sqlite3.Row
        return c

    import sable.pulse.meta.db as meta_db_module
    orig = meta_db_module.get_conn
    meta_db_module.get_conn = make_conn

    try:
        scan_id = create_scan_run("testorg", "full", watchlist_size=1)
        fail_scan_run(scan_id, "ANTHROPIC_API_KEY=sk-ant-secret-1234 rejected")
        check = make_conn()
        row = check.execute(
            "SELECT claude_raw FROM scan_runs WHERE id=?", (scan_id,)
        ).fetchone()
        check.close()
        assert "sk-ant-secret-1234" not in row["claude_raw"]
        assert "[REDACTED]" in row["claude_raw"]
    finally:
        meta_db_module.get_conn = orig


def test_redact_error_strips_socialdata_key_assignment():
    """SOCIALDATA_API_KEY=<value> is redacted; key name is preserved."""
    from sable.platform.errors import redact_error

    raw = "Request failed: SOCIALDATA_API_KEY=sd_abc123xyz was rejected."
    redacted = redact_error(raw)

    assert "sd_abc123xyz" not in redacted
    assert "SOCIALDATA_API_KEY" in redacted
    assert "[REDACTED]" in redacted


def test_redact_error_strips_elevenlabs_key_assignment():
    """ELEVENLABS_API_KEY=<value> is redacted; key name is preserved."""
    from sable.platform.errors import redact_error

    raw = "ElevenLabs auth failed. ELEVENLABS_API_KEY=el_abc123xyz was rejected."
    redacted = redact_error(raw)

    assert "el_abc123xyz" not in redacted
    assert "ELEVENLABS_API_KEY" in redacted
    assert "[REDACTED]" in redacted


def test_redact_error_strips_xi_api_key_header():
    """xi-api-key header values are redacted."""
    from sable.platform.errors import redact_error

    raw = "Request failed: xi-api-key: abc123defghij456"
    redacted = redact_error(raw)

    assert "abc123defghij456" not in redacted
    assert "[REDACTED]" in redacted
