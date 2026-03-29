"""Sable platform error codes — re-exported from sable_platform.

NOTE: redact_error is defined locally here (not re-exported from sable_platform)
because Slopper's version covers two additional patterns that sable_platform.errors
does not yet include:
  - ELEVENLABS_API_KEY env var assignments
  - ElevenLabs xi-api-key header values
Existing Slopper tests (test_redact_error.py) verify these patterns. Once
sable_platform.errors is updated to include them, redact_error can be re-exported
too and this local copy removed.
"""
from __future__ import annotations

import re

from sable_platform.errors import (  # noqa: F401
    SableError,
    ORG_EXISTS, ORG_NOT_FOUND, ENTITY_NOT_FOUND, ENTITY_ARCHIVED,
    HANDLE_NOT_IN_ROSTER, NO_ORG_FOR_HANDLE, CROSS_ORG_MERGE_BLOCKED,
    SLUG_ORG_CONFLICT, STALE_DIAGNOSTIC, NO_DISCORD_DIAGNOSTIC, INVALID_CONFIG,
    ORG_MAPPING_ERROR, BUDGET_EXCEEDED, BRIEF_CAP_EXCEEDED, MAX_RETRIES_EXCEEDED,
    AMBIGUOUS_INPUT, AWAITING_OPERATOR_INPUT, INVALID_ORG_ID, INVALID_PATH,
    WORKFLOW_NOT_FOUND, STEP_EXECUTION_ERROR,
)

# ---------------------------------------------------------------------------
# Error message redaction (for DB persistence paths)
# Local copy covers ELEVENLABS_API_KEY and xi-api-key patterns not yet in
# sable_platform.errors.redact_error.
# ---------------------------------------------------------------------------

_SECRET_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Real Anthropic API key prefix (sk-ant-api03-...)
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"), "[REDACTED]"),
    # Known env var assignments with sensitive values
    (
        re.compile(
            r"(ANTHROPIC_API_KEY|REPLICATE_API_TOKEN|SOCIALDATA_API_KEY|ELEVENLABS_API_KEY)\s*=\s*\S+"
        ),
        r"\1=[REDACTED]",
    ),
    # Authorization Bearer tokens
    (re.compile(r"Bearer\s+[A-Za-z0-9._\-]{20,}", re.IGNORECASE), "Bearer [REDACTED]"),
    # ElevenLabs xi-api-key header values
    (re.compile(r"xi-api-key[:\s]+[A-Za-z0-9_\-]{10,}", re.IGNORECASE), "xi-api-key: [REDACTED]"),
]


def redact_error(message: str) -> str:
    """Redact key-like strings from error messages before DB persistence.

    Covers Anthropic API key prefixes, known env var assignments (including
    ELEVENLABS_API_KEY), Bearer tokens, and ElevenLabs xi-api-key header values.
    Safe to call on clean messages — returns unchanged if no patterns match.
    """
    for pattern, replacement in _SECRET_PATTERNS:
        message = pattern.sub(replacement, message)
    return message
