"""Tests for sable.shared.handles — handle normalization utilities."""
from sable.shared.handles import strip_handle, normalize_handle, ensure_handle_prefix


def test_strip_handle_removes_at():
    assert strip_handle("@alice") == "alice"


def test_strip_handle_noop_without_at():
    assert strip_handle("alice") == "alice"


def test_strip_handle_empty():
    assert strip_handle("") == ""


def test_normalize_handle_strips_and_lowercases():
    assert normalize_handle("@Alice") == "alice"


def test_normalize_handle_lowercases_without_at():
    assert normalize_handle("ALICE") == "alice"


def test_normalize_handle_empty():
    assert normalize_handle("") == ""


def test_ensure_handle_prefix_adds_at():
    assert ensure_handle_prefix("alice") == "@alice"


def test_ensure_handle_prefix_noop_with_at():
    assert ensure_handle_prefix("@alice") == "@alice"


def test_ensure_handle_prefix_empty():
    assert ensure_handle_prefix("") == "@"
