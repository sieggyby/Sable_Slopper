"""Service-to-service token authentication."""
from __future__ import annotations

import hmac
import logging

from fastapi import HTTPException, Request

from sable import config as cfg

logger = logging.getLogger(__name__)


def get_serve_cfg() -> dict:
    """Return the ``serve`` config block as a dict (empty if unconfigured)."""
    raw = cfg.get("serve", {})
    return raw if isinstance(raw, dict) else {}


def _resolve_token(token: str) -> tuple[bool, str]:
    """Check token against config. Returns (valid, client_name).

    Supports two config layouts:
      serve.token: "single-token"          (legacy single-token)
      serve.tokens: {name: "token", ...}   (named multi-token)

    Named tokens are checked first. Falls back to legacy single token.
    """
    serve_cfg = get_serve_cfg()

    # Named tokens (SS-17)
    tokens_map = serve_cfg.get("tokens")
    if isinstance(tokens_map, dict):
        for name, expected in tokens_map.items():
            if expected and hmac.compare_digest(token, str(expected)):
                return True, str(name)

    # Legacy single token
    expected = serve_cfg.get("token")
    if expected and hmac.compare_digest(token, str(expected)):
        return True, "default"

    # Check if any token is configured at all
    if not tokens_map and not expected:
        raise HTTPException(status_code=500, detail="serve.token not configured")

    return False, ""


def resolve_client(request: Request) -> str:
    """Extract client identity from request without raising.

    Returns the client name if a valid Bearer token is present,
    or ``"__anonymous__"`` otherwise.  Used by rate-limit middleware
    and any other pre-auth logic that needs tenant identity.
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return "__anonymous__"
    valid, client_name = _resolve_token(auth[7:])
    return client_name if valid else "__anonymous__"


def verify_token(request: Request) -> None:
    """Validate Bearer token from Authorization header.

    Supports named tokens (serve.tokens) for audit trail and
    legacy single token (serve.token) for backward compatibility.
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed token")
    token = auth[7:]

    valid, client_name = _resolve_token(token)
    if not valid:
        raise HTTPException(status_code=403, detail="Invalid token")

    # Store client name for logging/audit
    request.state.client_name = client_name
    logger.info("Authenticated request: client=%s path=%s", client_name, request.url.path)
