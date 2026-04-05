"""Terminal detection utilities."""
from __future__ import annotations

import sys


def is_tty() -> bool:
    """Check if stderr is a TTY (for progress bars / interactive output)."""
    return hasattr(sys.stderr, "isatty") and sys.stderr.isatty()
