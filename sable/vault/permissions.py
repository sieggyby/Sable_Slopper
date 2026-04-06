"""
Role-based access control for sable serve.

Roles:
  admin    — Full access to all orgs and all endpoints.
  creator  — Read + write vault actions (search, suggest, log) for allowed orgs.
  operator — Read-only access scoped to specific orgs.

Org scoping:
  admin tokens have no org restriction.
  creator/operator tokens carry an explicit ``orgs`` list in config.
  A request for an org not in the token's list is rejected with 403.

See docs/ROLES.md for the full permission matrix.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Role(str, Enum):
    admin = "admin"
    creator = "creator"
    operator = "operator"


# Actions map to route groups.  Each route checks its required action.
class Action(str, Enum):
    # Vault
    vault_read = "vault_read"         # inventory, search, gaps
    vault_write = "vault_write"       # suggest, log, assign
    vault_admin = "vault_admin"       # init, sync, topic add/refresh, export

    # Pulse
    pulse_read = "pulse_read"         # performance, posting-log

    # Meta
    meta_read = "meta_read"           # topics, baselines, watchlist


# Permission matrix — which roles can perform which actions.
_PERMISSIONS: dict[Role, frozenset[Action]] = {
    Role.admin: frozenset(Action),  # everything
    Role.creator: frozenset({
        Action.vault_read,
        Action.vault_write,
        Action.pulse_read,
        Action.meta_read,
    }),
    Role.operator: frozenset({
        Action.vault_read,
        Action.pulse_read,
        Action.meta_read,
    }),
}


@dataclass(frozen=True)
class ClientIdentity:
    """Resolved identity from a bearer token."""
    name: str
    role: Role
    allowed_orgs: tuple[str, ...] = ()  # empty = all orgs (admin)

    def can(self, action: Action) -> bool:
        """Check if this client's role permits the given action."""
        return action in _PERMISSIONS.get(self.role, frozenset())

    def can_access_org(self, org: str) -> bool:
        """Check if this client may access the given org.

        Admins have no org restriction.  Creators and operators must have
        the org in their explicit ``allowed_orgs`` list.
        """
        if self.role == Role.admin:
            return True
        return org in self.allowed_orgs
