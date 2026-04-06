"""Tests for RBAC: role-based access control on sable serve."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from sable.serve.app import create_app
from sable.serve.auth import _resolve_token
from sable.vault.permissions import Action, ClientIdentity, Role
from sable.roster.models import Account
from tests.serve.conftest import make_sqlite, PULSE_SCHEMA, META_SCHEMA


# ---------------------------------------------------------------------------
# Token resolution unit tests
# ---------------------------------------------------------------------------

def test_resolve_legacy_string_token(monkeypatch):
    """Plain string token → admin, no org restriction."""
    monkeypatch.setattr(
        "sable.serve.auth.cfg.get",
        lambda key, default=None: {"tokens": {"sableweb": "tok123"}} if key == "serve" else default,
    )
    identity = _resolve_token("tok123")
    assert identity is not None
    assert identity.name == "sableweb"
    assert identity.role == Role.admin
    assert identity.allowed_orgs == ()


def test_resolve_rbac_admin_token(monkeypatch):
    """Dict token with role=admin → admin, no org restriction."""
    monkeypatch.setattr(
        "sable.serve.auth.cfg.get",
        lambda key, default=None: {
            "tokens": {"sableweb": {"token": "tok123", "role": "admin"}}
        } if key == "serve" else default,
    )
    identity = _resolve_token("tok123")
    assert identity is not None
    assert identity.role == Role.admin
    assert identity.allowed_orgs == ()


def test_resolve_rbac_operator_token(monkeypatch):
    """Dict token with role=operator + orgs → operator, scoped orgs."""
    monkeypatch.setattr(
        "sable.serve.auth.cfg.get",
        lambda key, default=None: {
            "tokens": {
                "jane": {"token": "optok", "role": "operator", "orgs": ["tig", "multisynq"]}
            }
        } if key == "serve" else default,
    )
    identity = _resolve_token("optok")
    assert identity is not None
    assert identity.name == "jane"
    assert identity.role == Role.operator
    assert identity.allowed_orgs == ("tig", "multisynq")


def test_resolve_rbac_creator_token(monkeypatch):
    """Dict token with role=creator → creator, scoped orgs."""
    monkeypatch.setattr(
        "sable.serve.auth.cfg.get",
        lambda key, default=None: {
            "tokens": {
                "alice": {"token": "crtok", "role": "creator", "orgs": ["psy_protocol"]}
            }
        } if key == "serve" else default,
    )
    identity = _resolve_token("crtok")
    assert identity is not None
    assert identity.role == Role.creator
    assert identity.allowed_orgs == ("psy_protocol",)


def test_resolve_unknown_role_defaults_to_operator(monkeypatch):
    """Unknown role string → defaults to operator."""
    monkeypatch.setattr(
        "sable.serve.auth.cfg.get",
        lambda key, default=None: {
            "tokens": {"x": {"token": "t", "role": "superadmin", "orgs": ["org1"]}}
        } if key == "serve" else default,
    )
    identity = _resolve_token("t")
    assert identity is not None
    assert identity.role == Role.operator


def test_resolve_wrong_token_returns_none(monkeypatch):
    monkeypatch.setattr(
        "sable.serve.auth.cfg.get",
        lambda key, default=None: {"tokens": {"x": "correct"}} if key == "serve" else default,
    )
    assert _resolve_token("wrong") is None


def test_resolve_legacy_single_token(monkeypatch):
    """Legacy serve.token (single token) → admin."""
    monkeypatch.setattr(
        "sable.serve.auth.cfg.get",
        lambda key, default=None: {"token": "legacy"} if key == "serve" else default,
    )
    identity = _resolve_token("legacy")
    assert identity is not None
    assert identity.role == Role.admin
    assert identity.name == "default"


# ---------------------------------------------------------------------------
# ClientIdentity permission tests
# ---------------------------------------------------------------------------

def test_admin_can_access_any_org():
    identity = ClientIdentity(name="admin", role=Role.admin)
    assert identity.can_access_org("anything")
    assert identity.can(Action.vault_admin)


def test_operator_cannot_access_unallowed_org():
    identity = ClientIdentity(name="op", role=Role.operator, allowed_orgs=("tig",))
    assert identity.can_access_org("tig")
    assert not identity.can_access_org("secret_client")


def test_operator_cannot_vault_write():
    identity = ClientIdentity(name="op", role=Role.operator, allowed_orgs=("tig",))
    assert identity.can(Action.vault_read)
    assert identity.can(Action.pulse_read)
    assert identity.can(Action.meta_read)
    assert not identity.can(Action.vault_write)
    assert not identity.can(Action.vault_admin)


def test_creator_can_vault_write_not_admin():
    identity = ClientIdentity(name="cr", role=Role.creator, allowed_orgs=("tig",))
    assert identity.can(Action.vault_read)
    assert identity.can(Action.vault_write)
    assert not identity.can(Action.vault_admin)


# ---------------------------------------------------------------------------
# Integration: org scoping on routes
# ---------------------------------------------------------------------------

def _rbac_cfg(tokens_dict):
    def _get(key, default=None):
        if key == "serve":
            return {"tokens": tokens_dict, "rate_limit_rpm": 9999}
        return default
    return _get


def _make_app_and_client(monkeypatch, tokens_dict):
    monkeypatch.setattr("sable.serve.auth.cfg.get", _rbac_cfg(tokens_dict))
    app = create_app()
    return app, TestClient(app)


def test_operator_can_access_allowed_org(monkeypatch):
    """Operator with orgs=["testorg"] can read pulse for testorg."""
    tokens = {"op": {"token": "optok", "role": "operator", "orgs": ["testorg"]}}
    app, client = _make_app_and_client(monkeypatch, tokens)

    pulse = make_sqlite(PULSE_SCHEMA)
    accounts = [Account(handle="@test", org="testorg")]

    with patch("sable.serve.routes.pulse.get_pulse_db", return_value=pulse), \
         patch("sable.serve.routes.pulse.get_meta_db", return_value=make_sqlite(META_SCHEMA)), \
         patch("sable.serve.routes.pulse.list_accounts", return_value=accounts):
        resp = client.get(
            "/api/pulse/performance/testorg",
            headers={"Authorization": "Bearer optok"},
        )

    assert resp.status_code == 200


def test_operator_denied_for_other_org(monkeypatch):
    """Operator with orgs=["testorg"] gets 403 for secret_client."""
    tokens = {"op": {"token": "optok", "role": "operator", "orgs": ["testorg"]}}
    app, client = _make_app_and_client(monkeypatch, tokens)

    resp = client.get(
        "/api/pulse/performance/secret_client",
        headers={"Authorization": "Bearer optok"},
    )

    assert resp.status_code == 403
    assert "Access denied" in resp.json()["detail"]


def test_admin_can_access_any_org_integration(monkeypatch):
    """Admin token can access any org."""
    tokens = {"admin": {"token": "admtok", "role": "admin"}}
    app, client = _make_app_and_client(monkeypatch, tokens)

    pulse = make_sqlite(PULSE_SCHEMA)
    accounts = [Account(handle="@test", org="anyorg")]

    with patch("sable.serve.routes.pulse.get_pulse_db", return_value=pulse), \
         patch("sable.serve.routes.pulse.get_meta_db", return_value=make_sqlite(META_SCHEMA)), \
         patch("sable.serve.routes.pulse.list_accounts", return_value=accounts):
        resp = client.get(
            "/api/pulse/performance/anyorg",
            headers={"Authorization": "Bearer admtok"},
        )

    assert resp.status_code == 200


def test_legacy_string_token_is_admin(monkeypatch):
    """Plain string token (legacy format) works as admin — backwards compat."""
    tokens = {"sableweb": "legacytok"}
    app, client = _make_app_and_client(monkeypatch, tokens)

    pulse = make_sqlite(PULSE_SCHEMA)
    accounts = [Account(handle="@test", org="anyorg")]

    with patch("sable.serve.routes.pulse.get_pulse_db", return_value=pulse), \
         patch("sable.serve.routes.pulse.get_meta_db", return_value=make_sqlite(META_SCHEMA)), \
         patch("sable.serve.routes.pulse.list_accounts", return_value=accounts):
        resp = client.get(
            "/api/pulse/performance/anyorg",
            headers={"Authorization": "Bearer legacytok"},
        )

    assert resp.status_code == 200


def test_operator_denied_vault_routes(monkeypatch, tmp_path):
    """Operator scoped to org1 gets 403 on vault for org2."""
    tokens = {"op": {"token": "optok", "role": "operator", "orgs": ["org1"]}}
    app, client = _make_app_and_client(monkeypatch, tokens)

    resp = client.get(
        "/api/vault/inventory/org2",
        headers={"Authorization": "Bearer optok"},
    )
    assert resp.status_code == 403


def test_operator_denied_meta_routes(monkeypatch):
    """Operator scoped to org1 gets 403 on meta for org2."""
    tokens = {"op": {"token": "optok", "role": "operator", "orgs": ["org1"]}}
    app, client = _make_app_and_client(monkeypatch, tokens)

    resp = client.get(
        "/api/meta/topics/org2",
        headers={"Authorization": "Bearer optok"},
    )
    assert resp.status_code == 403


def test_operator_allowed_meta_routes(monkeypatch):
    """Operator scoped to org1 can access meta for org1."""
    tokens = {"op": {"token": "optok", "role": "operator", "orgs": ["org1"]}}
    app, client = _make_app_and_client(monkeypatch, tokens)

    meta = make_sqlite(META_SCHEMA)

    with patch("sable.serve.routes.meta.get_meta_db", return_value=meta):
        resp = client.get(
            "/api/meta/topics/org1",
            headers={"Authorization": "Bearer optok"},
        )

    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Edge case / security boundary tests
# ---------------------------------------------------------------------------

def test_empty_string_token_rejected(monkeypatch):
    """Config with empty-string token must NOT match empty Bearer value."""
    monkeypatch.setattr(
        "sable.serve.auth.cfg.get",
        lambda key, default=None: {"tokens": {"bad": ""}} if key == "serve" else default,
    )
    assert _resolve_token("") is None


def test_empty_bearer_value_rejected(monkeypatch):
    """Bearer header with empty value after 'Bearer ' must be rejected."""
    tokens = {"x": {"token": "real", "role": "admin"}}
    app, client = _make_app_and_client(monkeypatch, tokens)

    resp = client.get(
        "/api/pulse/performance/testorg",
        headers={"Authorization": "Bearer "},
    )
    # Empty token after "Bearer " should fail auth
    assert resp.status_code in (401, 403)


def test_empty_tokens_map_returns_none(monkeypatch):
    """Empty tokens dict → no match."""
    monkeypatch.setattr(
        "sable.serve.auth.cfg.get",
        lambda key, default=None: {"tokens": {}} if key == "serve" else default,
    )
    assert _resolve_token("anything") is None


def test_operator_empty_orgs_denies_all(monkeypatch):
    """Operator with no orgs configured is denied access to every org."""
    monkeypatch.setattr(
        "sable.serve.auth.cfg.get",
        lambda key, default=None: {
            "tokens": {"op": {"token": "optok", "role": "operator"}}
        } if key == "serve" else default,
    )
    identity = _resolve_token("optok")
    assert identity is not None
    assert identity.role == Role.operator
    assert not identity.can_access_org("anything")
