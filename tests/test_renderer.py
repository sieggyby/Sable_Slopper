"""Tests for meme renderer (placeholder mode — no image files needed)."""
import pytest


@pytest.fixture(autouse=True)
def tmp_sable_home(tmp_path, monkeypatch):
    monkeypatch.setenv("SABLE_HOME", str(tmp_path / ".sable"))


def test_render_placeholder(tmp_path):
    from sable.meme.renderer import render_meme

    out = tmp_path / "test_meme.png"
    result = render_meme(
        "drake",
        {"top": "Old boring thing", "bottom": "New shiny thing"},
        out,
    )
    assert result.exists()
    assert result.stat().st_size > 0


def test_render_all_templates(tmp_path):
    from sable.meme.templates import load_registry
    from sable.meme.renderer import render_meme

    registry = load_registry()
    for tmpl in registry[:3]:  # test first 3
        texts = {z["id"]: f"Test text for {z['id']}" for z in tmpl.get("zones", [])}
        out = tmp_path / f"{tmpl['id']}.png"
        result = render_meme(tmpl["id"], texts, out)
        assert result.exists()


def test_font_size_auto(tmp_path):
    from sable.meme.renderer import render_meme

    # Very long text should still render without crashing
    out = tmp_path / "long_text.png"
    result = render_meme(
        "this-is-fine",
        {"caption": "This is a very long piece of text that should be automatically sized down to fit within the meme template boundaries without overflowing or crashing"},
        out,
    )
    assert result.exists()
