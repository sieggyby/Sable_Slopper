"""Tests for vault API routes."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from fastapi.testclient import TestClient

from fastapi import Request

from sable.serve.app import create_app
from sable.serve.auth import verify_token
from sable.roster.models import Account
from sable.vault.permissions import ClientIdentity, Role
from tests.serve.conftest import make_sqlite, PULSE_SCHEMA


def _bypass_auth(request: Request):
    request.state.identity = ClientIdentity(name="test", role=Role.admin)
    request.state.client_name = "test"


_ACCOUNTS = [Account(handle="@test_acct", org="testorg")]


def _make_vault_notes(vault_path: Path, notes: list[dict]) -> None:
    content_dir = vault_path / "content"
    content_dir.mkdir(parents=True, exist_ok=True)
    for i, note in enumerate(notes):
        fm = yaml.dump(note, default_flow_style=False)
        path = content_dir / f"note_{i}.md"
        path.write_text(f"---\n{fm}---\n\nBody text.\n")


def _make_client(pulse_db, vault_path, accounts=None):
    app = create_app()
    app.dependency_overrides[verify_token] = _bypass_auth
    patches = [
        patch("sable.serve.routes.vault.get_pulse_db", return_value=pulse_db),
        patch("sable.serve.routes.vault.resolve_vault_path", return_value=vault_path),
        patch("sable.serve.routes.vault.list_accounts", return_value=accounts if accounts is not None else _ACCOUNTS),
    ]
    for p in patches:
        p.start()
    client = TestClient(app)
    client._patches = patches  # type: ignore[attr-defined]
    return client


def _stop(client):
    for p in client._patches:  # type: ignore[attr-defined]
        p.stop()


def test_inventory_empty_vault(tmp_path):
    vault = tmp_path / "vault" / "testorg"
    pulse = make_sqlite(PULSE_SCHEMA)
    c = _make_client(pulse, vault)
    try:
        resp = c.get("/api/vault/inventory/testorg")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_produced"] == 0
        assert data["total_posted"] == 0
        assert data["total_unused"] == 0
    finally:
        _stop(c)


def test_inventory_with_notes(tmp_path):
    vault = tmp_path / "vault" / "testorg"
    pulse = make_sqlite(PULSE_SCHEMA)
    _make_vault_notes(vault, [
        {"id": "n1", "type": "meme", "topic": "ZK proofs", "posted_by": [{"account": "@test_acct"}]},
        {"id": "n2", "type": "meme", "topic": "Token launch"},
        {"id": "n3", "type": "clip", "topic": "Interview recap"},
    ])

    c = _make_client(pulse, vault)
    try:
        resp = c.get("/api/vault/inventory/testorg")
        data = resp.json()
        assert data["total_produced"] == 3
        assert data["total_posted"] == 1
        assert data["total_unused"] == 2
        assert len(data["by_format"]) == 2
    finally:
        _stop(c)


def test_inventory_posted_via_pulse(tmp_path):
    vault = tmp_path / "vault" / "testorg"
    pulse = make_sqlite(PULSE_SCHEMA)
    _make_vault_notes(vault, [
        {"id": "n1", "type": "meme", "topic": "ZK proofs"},
    ])
    note_path = str(vault / "content" / "note_0.md")
    pulse.execute(
        "INSERT INTO posts (id, account_handle, posted_at, sable_content_path) VALUES (?, ?, ?, ?)",
        ("p1", "@test_acct", "2026-04-01", note_path),
    )
    pulse.commit()

    c = _make_client(pulse, vault)
    try:
        resp = c.get("/api/vault/inventory/testorg")
        data = resp.json()
        assert data["total_posted"] == 1
    finally:
        _stop(c)


def test_search_empty_vault(tmp_path):
    vault = tmp_path / "vault" / "testorg"
    pulse = make_sqlite(PULSE_SCHEMA)
    c = _make_client(pulse, vault)
    try:
        resp = c.get("/api/vault/search/testorg?q=zkproofs")
        assert resp.status_code == 200
        assert resp.json() == []
    finally:
        _stop(c)


def test_search_with_matches(tmp_path):
    vault = tmp_path / "vault" / "testorg"
    pulse = make_sqlite(PULSE_SCHEMA)
    _make_vault_notes(vault, [
        {"id": "n1", "type": "meme", "topic": "ZK proofs explained"},
        {"id": "n2", "type": "clip", "topic": "Token launch strategy"},
        {"id": "n3", "type": "meme", "topic": "Zero knowledge deep dive"},
    ])

    c = _make_client(pulse, vault, accounts=[])
    try:
        resp = c.get("/api/vault/search/testorg?q=proofs")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["title"] == "ZK proofs explained"
        assert data[0]["score"] > 0
    finally:
        _stop(c)


def test_search_respects_limit(tmp_path):
    vault = tmp_path / "vault" / "testorg"
    pulse = make_sqlite(PULSE_SCHEMA)
    _make_vault_notes(vault, [
        {"id": f"n{i}", "type": "meme", "topic": f"Topic {i} about governance"}
        for i in range(5)
    ])

    c = _make_client(pulse, vault, accounts=[])
    try:
        resp = c.get("/api/vault/search/testorg?q=governance&limit=2")
        data = resp.json()
        assert len(data) == 2
    finally:
        _stop(c)


def test_search_no_query_returns_422(tmp_path):
    vault = tmp_path / "vault" / "testorg"
    pulse = make_sqlite(PULSE_SCHEMA)
    c = _make_client(pulse, vault)
    try:
        resp = c.get("/api/vault/search/testorg")
        assert resp.status_code == 422
    finally:
        _stop(c)


def test_path_traversal_rejected(tmp_path):
    """Org slug with path traversal characters → rejected by vault_dir()."""
    from sable.serve.deps import resolve_vault_path
    from sable.platform.errors import SableError
    with pytest.raises(SableError):
        resolve_vault_path("../../etc")
