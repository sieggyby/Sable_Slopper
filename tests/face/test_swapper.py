"""Tests for sable.face.swapper — T1-1 regression: no env leak."""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch


def test_get_replicate_does_not_set_env():
    """_get_replicate must return a Client instance without touching os.environ."""
    fake_client = MagicMock(name="replicate.Client")
    fake_replicate = MagicMock(name="replicate_module")
    fake_replicate.Client.return_value = fake_client

    env_before = os.environ.get("REPLICATE_API_TOKEN")

    with patch.dict("sys.modules", {"replicate": fake_replicate}), \
         patch("sable.config.require_key", return_value="test-token-1234"):
        from sable.face.swapper import _get_replicate
        client = _get_replicate()

    env_after = os.environ.get("REPLICATE_API_TOKEN")

    # Key must not have been written
    assert env_after == env_before, "REPLICATE_API_TOKEN leaked into os.environ"
    # Returned object must be a Client, not the module
    fake_replicate.Client.assert_called_once_with(api_token="test-token-1234")
    assert client is fake_client
