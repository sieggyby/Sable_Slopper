"""Tests for sable.meme.bank — save_to_bank and interactive_approve."""
from __future__ import annotations

from unittest.mock import patch, MagicMock, call

import pytest


class TestSaveToBank:
    def test_calls_require_account_and_append(self, monkeypatch):
        mock_require = MagicMock()
        mock_append = MagicMock()
        monkeypatch.setattr("sable.meme.bank.require_account", mock_require)
        monkeypatch.setattr("sable.meme.bank.append_tweet", mock_append)

        from sable.meme.bank import save_to_bank
        save_to_bank("@test", "gm frens")

        mock_require.assert_called_once_with("@test")
        mock_append.assert_called_once_with("@test", "gm frens")

    def test_propagates_require_account_error(self, monkeypatch):
        monkeypatch.setattr("sable.meme.bank.require_account",
                            MagicMock(side_effect=ValueError("unknown handle")))
        monkeypatch.setattr("sable.meme.bank.append_tweet", MagicMock())

        from sable.meme.bank import save_to_bank
        with pytest.raises(ValueError, match="unknown handle"):
            save_to_bank("@nobody", "tweet")


class TestInteractiveApprove:
    def test_approve_yes(self, monkeypatch):
        monkeypatch.setattr("sable.meme.bank.require_account", MagicMock())
        monkeypatch.setattr("sable.meme.bank.append_tweet", MagicMock())
        monkeypatch.setattr("builtins.input", lambda _: "y")

        from sable.meme.bank import interactive_approve
        result = interactive_approve("@test", ["tweet1", "tweet2"])
        assert result == ["tweet1", "tweet2"]

    def test_approve_quit(self, monkeypatch):
        monkeypatch.setattr("sable.meme.bank.require_account", MagicMock())
        monkeypatch.setattr("sable.meme.bank.append_tweet", MagicMock())
        monkeypatch.setattr("builtins.input", lambda _: "q")

        from sable.meme.bank import interactive_approve
        result = interactive_approve("@test", ["tweet1", "tweet2"])
        assert result == []

    def test_approve_skip(self, monkeypatch):
        monkeypatch.setattr("sable.meme.bank.require_account", MagicMock())
        monkeypatch.setattr("sable.meme.bank.append_tweet", MagicMock())
        monkeypatch.setattr("builtins.input", lambda _: "n")

        from sable.meme.bank import interactive_approve
        result = interactive_approve("@test", ["tweet1"])
        assert result == []
