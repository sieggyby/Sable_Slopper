# Sable Serve — RBAC Permission Matrix

> Enforced on all `sable serve` API routes. CLI bypasses all permission checks (implicit admin).

## Roles

| Role | Description | Org scoping |
|------|-------------|-------------|
| **admin** | Full access. Sable team lead / account manager. | All orgs (unrestricted) |
| **creator** | Read + write vault actions. Cannot admin vault or export. | Explicit `orgs` list |
| **operator** | Read-only. Client contact, can browse their own org data. | Explicit `orgs` list |

## Permission Matrix

| Action | admin | creator | operator |
|--------|-------|---------|----------|
| `vault_read` (inventory, search, gaps) | Y | Y | Y |
| `vault_write` (suggest, log, assign) | Y | Y | N |
| `vault_admin` (init, sync, topic add/refresh, export) | Y | N | N |
| `pulse_read` (performance, posting-log) | Y | Y | Y |
| `meta_read` (topics, baselines, watchlist) | Y | Y | Y |

## Org Scoping

- **Admin** tokens have no org restriction — they can query any org.
- **Creator** and **operator** tokens carry an explicit `orgs` list in config. Requests for an org not in the list return 403.
- An operator with no `orgs` configured is denied access to all orgs (fail-closed).

## Config Format

```yaml
serve:
  tokens:
    # Admin — full access, all orgs
    sableweb:
      token: "your-secret-token"
      role: admin

    # Operator — read-only, scoped to specific orgs
    operator_jane:
      token: "janes-token"
      role: operator
      orgs:
        - tig_foundation
        - multisynq

    # Creator — read + write, scoped to specific orgs
    creator_bob:
      token: "bobs-token"
      role: creator
      orgs:
        - psy_protocol

    # Legacy format (plain string) — treated as admin for backwards compat
    legacy_client: "plain-string-token"
```

## Implementation

- **Role definitions + permission matrix:** `sable/vault/permissions.py`
- **Token resolution + enforcement:** `sable/serve/auth.py`
- **Route-level checks:** Each route handler calls `require_org_access(request, org, Action.xxx)`
- **Router-level auth:** `verify_token` is a FastAPI dependency on all route groups (vault, pulse, meta)
- **Health endpoint:** `/health` is unauthenticated (no token required)

## Security Notes

- Token comparison uses `hmac.compare_digest` (constant-time) to prevent timing attacks.
- Empty-string tokens are rejected (not matched).
- Unknown roles default to `operator` (least privilege).
- `allowed_orgs` is an immutable tuple — cannot be mutated after construction.
- The CLI (`sable` commands) bypasses all RBAC — it is an admin-only tool by design.
