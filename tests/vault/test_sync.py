"""Tests for sable/vault/sync.py warning hardening (P5)."""
from __future__ import annotations

import logging
from unittest.mock import patch

from sable.vault.config import VaultConfig
from sable.vault.sync import sync


def test_sync_supporting_page_refresh_failure_warns(tmp_path, caplog):
    """refresh_topics crash → WARNING logged with org name, sync still returns SyncReport."""
    vault_path = tmp_path / "vault"
    vault_path.mkdir()
    workspace_path = tmp_path / "workspace"
    workspace_path.mkdir()

    config = VaultConfig(auto_enrich=False)

    with patch("sable.vault.topics.refresh_topics", side_effect=RuntimeError("down")), \
         patch("sable.vault.voices.generate_voice_profiles"), \
         patch("sable.vault.dashboard.regenerate_index"), \
         caplog.at_level(logging.WARNING, logger="sable.vault.sync"):
        report = sync("testorg", vault_path, workspace_path, config=config)

    warnings = [r for r in caplog.records if "supporting page refresh" in r.message]
    assert len(warnings) >= 1
    assert "testorg" in warnings[0].message
    assert report is not None
