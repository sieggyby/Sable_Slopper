"""Structured JSON logging for sable.

Enable via ``--json-log`` flag on the CLI. When active, all log output
is JSON-lines format suitable for log aggregation.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone


class StructuredFormatter(logging.Formatter):
    """Emit log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Include exception info if present
        if record.exc_info and record.exc_info[0] is not None:
            entry["exception"] = self.formatException(record.exc_info)

        # Include extra fields from LoggerAdapter or extra={}
        extras: dict[str, object] = {}
        for key in ("client_name", "org_id", "call_type", "cost_usd", "model"):
            val = getattr(record, key, None)
            if val is not None:
                extras[key] = val
        if extras:
            entry["extra"] = extras

        return json.dumps(entry, default=str)


def configure_logging(json_log: bool = False) -> None:
    """Configure root logger. Call once at CLI startup."""
    root = logging.getLogger()

    # Remove existing handlers to avoid double output
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    handler = logging.StreamHandler()
    if json_log:
        handler.setFormatter(StructuredFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(levelname)s %(name)s: %(message)s")
        )

    root.addHandler(handler)
    root.setLevel(logging.INFO)
