"""Tests for sable config show — secret masking (AUDIT-1)."""
from __future__ import annotations

from unittest.mock import patch

from click.testing import CliRunner

from sable.cli import main


def _make_config(**overrides):
    """Return a config dict with optional secret overrides."""
    base = {
        "anthropic_api_key": "",
        "replicate_api_key": "",
        "socialdata_api_key": "",
        "default_model": "claude-sonnet-4-6",
        "workspace": "/tmp/sable-workspace",
    }
    base.update(overrides)
    return base


def test_config_show_masks_set_secret():
    """A populated API key renders as '(set)', not as a prefix or full value."""
    runner = CliRunner()
    cfg = _make_config(anthropic_api_key="sk-ant-api03-REALKEYMATERIAL")

    with patch("sable.config.load_config", return_value=cfg):
        result = runner.invoke(main, ["config", "show"])

    assert result.exit_code == 0
    assert "(set)" in result.output
    assert "sk-ant" not in result.output
    assert "REALKEYMATERIAL" not in result.output


def test_config_show_masks_replicate_key():
    """Replicate API key renders as '(set)'."""
    runner = CliRunner()
    cfg = _make_config(replicate_api_key="r8_abcdef1234567890")

    with patch("sable.config.load_config", return_value=cfg):
        result = runner.invoke(main, ["config", "show"])

    assert "(set)" in result.output
    assert "r8_abcdef" not in result.output


def test_config_show_masks_socialdata_key():
    """SocialData API key renders as '(set)'."""
    runner = CliRunner()
    cfg = _make_config(socialdata_api_key="sd_secret_value_here")

    with patch("sable.config.load_config", return_value=cfg):
        result = runner.invoke(main, ["config", "show"])

    assert "(set)" in result.output
    assert "sd_secret" not in result.output


def test_config_show_masks_elevenlabs_key():
    """ElevenLabs API key renders as '(set)'."""
    runner = CliRunner()
    cfg = _make_config(elevenlabs_api_key="el_secret_api_key_value")

    with patch("sable.config.load_config", return_value=cfg):
        result = runner.invoke(main, ["config", "show"])

    assert "(set)" in result.output
    assert "el_secret" not in result.output


def test_config_show_unset_secret_shows_not_set():
    """An empty API key renders as '(not set)'."""
    runner = CliRunner()
    cfg = _make_config(anthropic_api_key="")

    with patch("sable.config.load_config", return_value=cfg):
        result = runner.invoke(main, ["config", "show"])

    assert "(not set)" in result.output


def test_config_show_non_secret_values_visible():
    """Non-secret config values like 'default_model' are shown in full."""
    runner = CliRunner()
    cfg = _make_config(default_model="claude-sonnet-4-6")

    with patch("sable.config.load_config", return_value=cfg):
        result = runner.invoke(main, ["config", "show"])

    assert "claude-sonnet-4-6" in result.output


def test_config_set_secret_warns_about_env_var(tmp_path):
    """Setting a secret key warns the operator to prefer env vars."""
    runner = CliRunner()

    with patch("sable.config.config_path", return_value=tmp_path / "config.yaml"):
        result = runner.invoke(main, ["config", "set", "anthropic_api_key", "sk-test"])

    assert "Prefer setting secrets via environment variable" in result.output
    assert "ANTHROPIC_API_KEY" in result.output


def test_config_set_non_secret_no_warning(tmp_path):
    """Setting a non-secret key does not warn about env vars."""
    runner = CliRunner()

    with patch("sable.config.config_path", return_value=tmp_path / "config.yaml"):
        result = runner.invoke(main, ["config", "set", "default_model", "claude-haiku-4-5-20251001"])

    assert "Prefer setting secrets" not in result.output
    assert "✓ Set default_model" in result.output
