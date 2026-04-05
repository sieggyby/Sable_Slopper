"""Tests for Anthropic client retry logic and timeout configuration."""
from __future__ import annotations

from unittest.mock import MagicMock, patch, PropertyMock

import pytest


def test_client_disables_sdk_retry():
    """get_client() disables the SDK's built-in retry to prevent double-retry."""
    import sable.shared.api as api_mod

    # Reset singleton
    api_mod._client = None

    with patch("sable.shared.api.cfg") as mock_cfg:
        mock_cfg.require_key.return_value = "fake-key"

        import anthropic
        with patch.object(anthropic, "Anthropic") as MockClient:
            mock_instance = MagicMock()
            MockClient.return_value = mock_instance
            api_mod.get_client()

            # Verify max_retries=0 was passed
            _, kwargs = MockClient.call_args
            assert kwargs["max_retries"] == 0

    # Reset singleton
    api_mod._client = None


def test_client_has_timeout():
    """get_client() sets appropriate timeout values."""
    import sable.shared.api as api_mod

    api_mod._client = None

    with patch("sable.shared.api.cfg") as mock_cfg:
        mock_cfg.require_key.return_value = "fake-key"

        import anthropic
        with patch.object(anthropic, "Anthropic") as MockClient:
            MockClient.return_value = MagicMock()
            api_mod.get_client()

            _, kwargs = MockClient.call_args
            timeout = kwargs["timeout"]
            assert timeout.read == 300.0
            assert timeout.connect == 10.0

    api_mod._client = None


def test_call_with_retry_raises_after_max_attempts():
    """_call_with_retry raises last exception after exhausting all attempts."""
    import anthropic
    from sable.shared.api import _call_with_retry, _MAX_RETRIES

    mock_client = MagicMock()
    error = anthropic.APIStatusError(
        message="rate limited",
        response=MagicMock(status_code=429),
        body=None,
    )
    mock_client.messages.create.side_effect = error

    with patch("sable.shared.api.time.sleep"):  # skip delays
        with pytest.raises(anthropic.APIStatusError):
            _call_with_retry(mock_client, {"model": "test", "messages": [], "max_tokens": 10})

    assert mock_client.messages.create.call_count == _MAX_RETRIES


def test_call_with_retry_no_retry_on_400():
    """_call_with_retry does not retry on non-retryable errors (400, 401, 403)."""
    import anthropic
    from sable.shared.api import _call_with_retry

    mock_client = MagicMock()
    error = anthropic.APIStatusError(
        message="bad request",
        response=MagicMock(status_code=400),
        body=None,
    )
    mock_client.messages.create.side_effect = error

    with pytest.raises(anthropic.APIStatusError):
        _call_with_retry(mock_client, {"model": "test", "messages": [], "max_tokens": 10})

    assert mock_client.messages.create.call_count == 1
