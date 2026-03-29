"""Thin re-export: entity CRUD helpers live in sable_platform."""
from sable_platform.db.entities import (  # noqa: F401
    create_entity, find_entity_by_handle, get_entity,
    update_display_name, add_handle, archive_entity,
)
