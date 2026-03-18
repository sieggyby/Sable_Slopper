"""Tests for the markdown profile file system."""
import pytest


@pytest.fixture(autouse=True)
def tmp_sable_home(tmp_path, monkeypatch):
    monkeypatch.setenv("SABLE_HOME", str(tmp_path / ".sable"))


def test_scaffold_creates_files():
    from sable.roster.profiles import scaffold_profile, PROFILE_FILES, read_profile_file

    d = scaffold_profile("@test_handle")
    assert d.exists()
    for fname in PROFILE_FILES:
        assert (d / f"{fname}.md").exists()


def test_scaffold_idempotent():
    from sable.roster.profiles import scaffold_profile

    d1 = scaffold_profile("@idempotent")
    d2 = scaffold_profile("@idempotent")
    assert d1 == d2


def test_read_write_profile():
    from sable.roster.profiles import scaffold_profile, read_profile_file, write_profile_file

    scaffold_profile("@rw_test")
    write_profile_file("@rw_test", "tone", "# Custom tone\nShitposter vibes only.")
    content = read_profile_file("@rw_test", "tone")
    assert "Shitposter vibes only" in content


def test_load_profiles_dict():
    from sable.roster.profiles import scaffold_profile, load_profiles, write_profile_file

    scaffold_profile("@load_test")
    write_profile_file("@load_test", "tone", "Tone content")
    write_profile_file("@load_test", "interests", "Interests content")

    profiles = load_profiles("@load_test", files=["tone", "interests"])
    assert "tone" in profiles
    assert "interests" in profiles
    assert "Tone content" in profiles["tone"]


def test_missing_file_returns_none():
    from sable.roster.profiles import read_profile_file

    result = read_profile_file("@nonexistent", "tone")
    assert result is None


def test_format_profiles_for_prompt():
    from sable.roster.profiles import format_profiles_for_prompt

    profiles = {
        "tone": "Be edgy.",
        "interests": "DeFi and memes.",
    }
    result = format_profiles_for_prompt(profiles)
    assert "=== TONE PROFILE ===" in result
    assert "Be edgy." in result
    assert "=== INTERESTS PROFILE ===" in result


def test_profile_preview():
    from sable.roster.profiles import scaffold_profile, write_profile_file, profile_preview

    scaffold_profile("@preview_test")
    write_profile_file("@preview_test", "tone", "\n".join(f"Line {i}" for i in range(20)))

    previews = profile_preview("@preview_test", lines=5)
    assert "tone" in previews
    lines = previews["tone"].splitlines()
    assert len(lines) <= 5


def test_profiles_exist():
    from sable.roster.profiles import scaffold_profile, profiles_exist

    assert not profiles_exist("@new_handle")
    scaffold_profile("@new_handle")
    assert profiles_exist("@new_handle")
