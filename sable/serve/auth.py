"""Service-to-service token authentication with RBAC."""
from __future__ import annotations

import hmac
import logging
from typing import Optional

from fastapi import HTTPException, Request

from sable import config as cfg
from sable.vault.permissions import Action, ClientIdentity, Role

logger = logging.getLogger(__name__)


def get_serve_cfg() -> dict:
    """Return the ``serve`` config block as a dict (empty if unconfigured)."""
    raw = cfg.get("serve", {})
    return raw if isinstance(raw, dict) else {}


def _resolve_token(token: str) -> Optional[ClientIdentity]:
    """Match a bearer token against config and return a ClientIdentity or None.

    Supports two config layouts:

    Legacy (plain string — treated as admin, no org restriction)::

        serve:
          tokens:
            sableweb: "abc123"

    RBAC (dict with role + optional orgs)::

        serve:
          tokens:
            sableweb:
              token: "abc123"
              role: admin
            operator_jane:
              token: "def456"
              role: operator
              orgs: ["tig_foundation", "multisynq"]

    Also supports the legacy single-token shorthand::

        serve:
          token: "abc123"
    """
    serve_cfg = get_serve_cfg()

    # Named tokens
    tokens_map = serve_cfg.get("tokens")
    if isinstance(tokens_map, dict):
        for name, value in tokens_map.items():
            if isinstance(value, str):
                # Legacy plain string — admin, all orgs
                if value and hmac.compare_digest(token, value):
                    return ClientIdentity(name=str(name), role=Role.admin)
            elif isinstance(value, dict):
                expected = value.get("token", "")
                if expected and hmac.compare_digest(token, str(expected)):
                    role_str = value.get("role", "operator")
                    try:
                        role = Role(role_str)
                    except ValueError:
                        logger.warning("Unknown role %r for token %s, defaulting to operator", role_str, name)
                        role = Role.operator
                    orgs = value.get("orgs", [])
                    if not isinstance(orgs, list):
                        orgs = []
                    return ClientIdentity(
                        name=str(name),
                        role=role,
                        allowed_orgs=tuple(str(o) for o in orgs),
                    )

    # Legacy single token
    expected = serve_cfg.get("token")
    if expected and hmac.compare_digest(token, str(expected)):
        return ClientIdentity(name="default", role=Role.admin)

    return None


def _has_any_token_configured() -> bool:
    serve_cfg = get_serve_cfg()
    return bool(serve_cfg.get("tokens") or serve_cfg.get("token"))


def resolve_client(request: Request) -> str:
    """Extract client identity from request without raising.

    Returns the client name if a valid Bearer token is present,
    or ``"__anonymous__"`` otherwise.  Used by rate-limit middleware
    and any other pre-auth logic that needs tenant identity.
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return "__anonymous__"
    identity = _resolve_token(auth[7:])
    return identity.name if identity else "__anonymous__"


def verify_token(request: Request) -> ClientIdentity:
    """Validate Bearer token and return ClientIdentity.

    Stored on ``request.state.identity`` for downstream use.
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed token")
    token = auth[7:]

    identity = _resolve_token(token)
    if identity is None:
        if not _has_any_token_configured():
            raise HTTPException(status_code=500, detail="serve.token not configured")
        raise HTTPException(status_code=403, detail="Invalid token")

    # Store for downstream dependencies
    request.state.identity = identity
    request.state.client_name = identity.name
    logger.info("Authenticated request: client=%s role=%s path=%s",
                identity.name, identity.role.value, request.url.path)
    return identity


def require_org_access(request: Request, org: str, action: Action = Action.vault_read) -> ClientIdentity:
    """Enforce org-scoped access. Call from route handlers after verify_token.

    Raises 403 if the client's role cannot perform the action or
    if the requested org is not in the client's allowed orgs.
    """
    identity: ClientIdentity = request.state.identity

    if not identity.can(action):
        raise HTTPException(
            status_code=403,
            detail=f"Role '{identity.role.value}' cannot perform '{action.value}'",
        )
    if not identity.can_access_org(org):
        raise HTTPException(
            status_code=403,
            detail=f"Access denied for org '{org}'",
        )
    return identity
