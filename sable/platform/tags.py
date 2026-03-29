"""Thin re-export: entity tag helpers live in sable_platform."""
from sable_platform.db.tags import (  # noqa: F401
    add_tag, get_active_tags, get_entities_by_tag, _REPLACE_CURRENT_TAGS,
)
