"""Service-to-service token authentication."""
from __future__ import annotations

import hmac

from fastapi import HTTPException, Request

from sable import config as cfg


def verify_token(request: Request) -> None:
    """Validate Bearer token from Authorization header.

    Token must match ``serve.token`` in ``~/.sable/config.yaml``.

    Phase 2: single token grants access to all orgs. Per-org scoping
    deferred to Phase 3 multi-tenant (see TODO.md).
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed token")
    token = auth[7:]
    expected = cfg.get("serve", {}).get("token") if isinstance(cfg.get("serve"), dict) else None
    if not expected:
        raise HTTPException(status_code=500, detail="serve.token not configured")
    if not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=403, detail="Invalid token")
