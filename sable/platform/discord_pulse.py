"""Thin re-export: discord_pulse_runs helpers live in sable_platform."""
from sable_platform.db.discord_pulse import (  # noqa: F401
    upsert_discord_pulse_run, get_discord_pulse_runs,
)
