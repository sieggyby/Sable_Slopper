# Sable Vault — Permission Matrix

> Phase 1 (CLI): All operations run as implicit admin. This matrix applies from Phase 2 (web UI) onward.

## Roles

| Role | Description |
|------|-------------|
| **admin** | Full access. Sable team lead / account manager. |
| **creator** | Can view and search vault, suggest replies, log posts. Cannot export or modify topics. |
| **operator** | Read-only. Client contact, can browse and export their own org vault. |

## Permission Matrix

| Action | admin | creator | operator |
|--------|-------|---------|----------|
| `vault init` | ✓ | ✗ | ✗ |
| `vault sync` | ✓ | ✗ | ✗ |
| `vault status` | ✓ | ✓ | ✓ |
| `vault search` | ✓ | ✓ | ✓ |
| `vault suggest` | ✓ | ✓ | ✗ |
| `vault log` | ✓ | ✓ | ✗ |
| `vault assign` | ✓ | ✓ | ✗ |
| `vault gaps` | ✓ | ✓ | ✓ |
| `vault export` | ✓ | ✗ | ✓ (own org) |
| `vault topic add` | ✓ | ✗ | ✗ |
| `vault topic list` | ✓ | ✓ | ✓ |
| `vault topic refresh` | ✓ | ✗ | ✗ |

## Implementation Notes

- Phase 2: token-based auth, roles stored in `~/.sable/vault_users.yaml`
- Operators are scoped to a single org; admins/creators can access any org
- The CLI bypasses all permission checks (admin-only tool)
- See `sable/vault/permissions.py` for the implementation stub
