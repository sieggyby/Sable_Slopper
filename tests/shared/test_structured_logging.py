"""Tests for structured JSON logging."""
from __future__ import annotations

import json
import logging

from sable.shared.logging import StructuredFormatter, configure_logging


def test_structured_formatter_json_output():
    """StructuredFormatter emits valid JSON."""
    formatter = StructuredFormatter()
    record = logging.LogRecord(
        name="test.module", level=logging.WARNING,
        pathname="", lineno=0, msg="test message",
        args=(), exc_info=None,
    )
    output = formatter.format(record)
    data = json.loads(output)
    assert data["level"] == "WARNING"
    assert data["logger"] == "test.module"
    assert data["message"] == "test message"
    assert "timestamp" in data


def test_structured_formatter_includes_exception():
    """Exception info is included in JSON output."""
    formatter = StructuredFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        import sys
        exc_info = sys.exc_info()

    record = logging.LogRecord(
        name="test", level=logging.ERROR,
        pathname="", lineno=0, msg="failed",
        args=(), exc_info=exc_info,
    )
    output = formatter.format(record)
    data = json.loads(output)
    assert "exception" in data
    assert "ValueError" in data["exception"]


def test_configure_logging_json_mode():
    """configure_logging(json_log=True) installs StructuredFormatter."""
    configure_logging(json_log=True)
    root = logging.getLogger()
    assert len(root.handlers) >= 1
    assert isinstance(root.handlers[-1].formatter, StructuredFormatter)
    # Restore default
    configure_logging(json_log=False)


def test_configure_logging_default_mode():
    """configure_logging(json_log=False) installs standard formatter."""
    configure_logging(json_log=False)
    root = logging.getLogger()
    assert len(root.handlers) >= 1
    assert not isinstance(root.handlers[-1].formatter, StructuredFormatter)
