"""Thin re-export: entity merge helpers live in sable_platform."""
from sable_platform.db.merge import (  # noqa: F401
    create_merge_candidate, get_pending_merges, execute_merge, reconsider_expired_merges,
)
