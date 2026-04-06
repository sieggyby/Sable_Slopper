"""AQ-34: Face reference library CRUD tests."""
from __future__ import annotations

from unittest.mock import patch

import pytest


def test_add_reference_creates_entry(tmp_path):
    """add_reference with valid image → entry in index."""
    img = tmp_path / "face.jpg"
    img.write_bytes(b"\xff\xd8\xff")  # JPEG header stub
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()

    with patch("sable.face.library.face_library_dir", return_value=lib_dir):
        from sable.face.library import add_reference, load_index
        entry = add_reference(img, name="alice", consent=True)

    assert entry["name"] == "alice"
    assert entry["consent"] is True

    with patch("sable.face.library.face_library_dir", return_value=lib_dir):
        from sable.face.library import load_index
        idx = load_index()
    assert len(idx) == 1
    assert idx[0]["name"] == "alice"


def test_add_reference_missing_file_raises(tmp_path):
    """add_reference with nonexistent file → FileNotFoundError."""
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    with patch("sable.face.library.face_library_dir", return_value=lib_dir):
        from sable.face.library import add_reference
        with pytest.raises(FileNotFoundError):
            add_reference(tmp_path / "nope.jpg", name="bob")


def test_get_reference_found(tmp_path):
    """get_reference retrieves by name."""
    img = tmp_path / "face.jpg"
    img.write_bytes(b"\xff\xd8\xff")
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()

    with patch("sable.face.library.face_library_dir", return_value=lib_dir):
        from sable.face.library import add_reference, get_reference
        add_reference(img, name="charlie")
        ref = get_reference("charlie")
    assert ref["name"] == "charlie"


def test_get_reference_not_found(tmp_path):
    """get_reference raises ValueError for unknown name."""
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    with patch("sable.face.library.face_library_dir", return_value=lib_dir):
        from sable.face.library import get_reference
        with pytest.raises(ValueError, match="not found"):
            get_reference("nobody")


def test_remove_reference(tmp_path):
    """remove_reference deletes entry from index."""
    img = tmp_path / "face.jpg"
    img.write_bytes(b"\xff\xd8\xff")
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()

    with patch("sable.face.library.face_library_dir", return_value=lib_dir):
        from sable.face.library import add_reference, remove_reference, load_index
        add_reference(img, name="dave")
        assert remove_reference("dave") is True
        assert load_index() == []


def test_remove_reference_not_found(tmp_path):
    """remove_reference returns False if name doesn't exist."""
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()
    with patch("sable.face.library.face_library_dir", return_value=lib_dir):
        from sable.face.library import remove_reference
        assert remove_reference("ghost") is False


def test_list_references_consent_filter(tmp_path):
    """list_references(consent_only=True) filters non-consented."""
    img1 = tmp_path / "yes.jpg"
    img2 = tmp_path / "no.jpg"
    img1.write_bytes(b"\xff\xd8\xff")
    img2.write_bytes(b"\xff\xd8\xff")
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()

    with patch("sable.face.library.face_library_dir", return_value=lib_dir):
        from sable.face.library import add_reference, list_references
        add_reference(img1, name="consented", consent=True)
        add_reference(img2, name="not_consented", consent=False)
        all_refs = list_references()
        consented = list_references(consent_only=True)

    assert len(all_refs) == 2
    assert len(consented) == 1
    assert consented[0]["name"] == "consented"


def test_add_reference_deduplicates_by_name(tmp_path):
    """Adding same name twice → replaces, not duplicates."""
    img = tmp_path / "face.jpg"
    img.write_bytes(b"\xff\xd8\xff")
    lib_dir = tmp_path / "lib"
    lib_dir.mkdir()

    with patch("sable.face.library.face_library_dir", return_value=lib_dir):
        from sable.face.library import add_reference, load_index
        add_reference(img, name="eve", notes="v1")
        add_reference(img, name="eve", notes="v2")
        idx = load_index()
    assert len(idx) == 1
    assert idx[0]["notes"] == "v2"
