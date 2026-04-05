"""CLI smoke tests for character_explainer/cli.py."""
from __future__ import annotations

from click.testing import CliRunner

from sable.character_explainer.cli import explainer_group, generate_cmd, list_characters_cmd


class TestCliSmoke:
    def test_explainer_group_exists(self):
        """The click group is importable and has subcommands."""
        assert explainer_group.name == "character-explainer"
        command_names = [c for c in explainer_group.commands]
        assert "generate" in command_names
        assert "list-characters" in command_names

    def test_generate_cmd_has_expected_options(self):
        param_names = [p.name for p in generate_cmd.params]
        for expected in ["topic", "character", "bg_video", "output", "tts_backend",
                         "target_duration", "no_talking_head", "orientation", "platform", "org"]:
            assert expected in param_names, f"Missing option: {expected}"

    def test_generate_missing_required_fails(self):
        runner = CliRunner()
        result = runner.invoke(explainer_group, ["generate"])
        assert result.exit_code != 0
        assert "Missing" in result.output or "required" in result.output.lower() or "Error" in result.output

    def test_list_characters_runs(self, monkeypatch):
        """list-characters should run without error even with no characters."""
        monkeypatch.setattr(
            "sable.character_explainer.cli.list_characters_cmd",
            list_characters_cmd,
        )
        # Mock list_characters to return empty list
        monkeypatch.setattr(
            "sable.character_explainer.characters.list_characters",
            lambda: [],
        )
        runner = CliRunner()
        result = runner.invoke(explainer_group, ["list-characters"])
        assert result.exit_code == 0
