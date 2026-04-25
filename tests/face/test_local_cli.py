"""Smoke test: `sable face local` CLI registration and lazy-import isolation.

These tests intentionally do not require insightface / cv2 / FaceFusion —
the CLI surface must be discoverable on a fresh clone before the heavy
[face-local] extras are installed.
"""
from __future__ import annotations

from click.testing import CliRunner


def test_face_local_help_lists_all_subcommands():
    from sable.cli import main
    r = CliRunner().invoke(main, ["face", "local", "--help"])
    assert r.exit_code == 0, r.output
    for sub in ("preflight", "extract", "filter", "closed", "faceset", "swap", "salvage"):
        assert sub in r.output, f"missing subcommand: {sub}"


def test_face_local_swap_help_renders_without_facefusion():
    """`swap --help` must work even when FaceFusion isn't installed."""
    from sable.cli import main
    r = CliRunner().invoke(main, ["face", "local", "swap", "--help"])
    assert r.exit_code == 0, r.output
    assert "hyperswap_1c_256" in r.output


def test_face_local_extract_help_renders_without_insightface():
    """`extract --help` must not trigger heavy imports."""
    from sable.cli import main
    r = CliRunner().invoke(main, ["face", "local", "extract", "--help"])
    assert r.exit_code == 0, r.output
    assert "--every" in r.output


def test_local_cli_module_importable_without_extras():
    """The cli module itself must import without insightface/cv2 installed."""
    import importlib
    importlib.import_module("sable.face.local.cli")
    importlib.import_module("sable.face.local.config")
    importlib.import_module("sable.face.local.preflight")
    # common.py contains heavy imports inside functions; module-level must be light
    importlib.import_module("sable.face.local.common")


def test_swap_build_command_shape():
    """build_command produces the expected argv structure."""
    from pathlib import Path
    from sable.face.local.swap import build_command, SwapParams

    argv = build_command(
        Path("/tmp/src.png"),
        Path("/tmp/tgt.mp4"),
        Path("/tmp/out.mp4"),
        SwapParams(enhance=True),
    )
    # Spot-check the recipe pieces from FACE_SWAP_LESSONS.md
    assert "headless-run" in argv
    assert "--face-swapper-model" in argv
    assert "hyperswap_1c_256" in argv
    assert "--face-swapper-pixel-boost" in argv
    assert "512x512" in argv
    assert "face_swapper" in argv
    assert "face_enhancer" in argv
    assert "--face-enhancer-model" in argv
    assert "codeformer" in argv


def test_facefusion_path_override():
    """Config override beats default."""
    from pathlib import Path
    from sable.face.local.config import facefusion_path
    p = facefusion_path("/tmp/custom_facefusion")
    assert p == Path("/tmp/custom_facefusion")
