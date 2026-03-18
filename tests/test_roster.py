"""Tests for roster CRUD operations."""
import pytest
import tempfile
import os
from pathlib import Path


@pytest.fixture(autouse=True)
def tmp_sable_home(tmp_path, monkeypatch):
    monkeypatch.setenv("SABLE_HOME", str(tmp_path / ".sable"))


def test_add_and_get_account():
    from sable.roster.models import Account, Persona
    from sable.roster.manager import add_account, get_account

    acc = Account(handle="@test_user", display_name="Test User", org="TestOrg")
    add_account(acc)

    retrieved = get_account("@test_user")
    assert retrieved is not None
    assert retrieved.handle == "@test_user"
    assert retrieved.display_name == "Test User"


def test_handle_normalization():
    from sable.roster.models import Account
    acc = Account(handle="test_user")
    assert acc.handle == "@test_user"

    acc2 = Account(handle="@test_user")
    assert acc2.handle == "@test_user"


def test_duplicate_account_raises():
    from sable.roster.models import Account
    from sable.roster.manager import add_account

    acc = Account(handle="@dup_user")
    add_account(acc)
    with pytest.raises(ValueError, match="already exists"):
        add_account(Account(handle="@dup_user"))


def test_remove_account():
    from sable.roster.models import Account
    from sable.roster.manager import add_account, remove_account, get_account

    add_account(Account(handle="@remove_me"))
    assert get_account("@remove_me") is not None
    removed = remove_account("@remove_me")
    assert removed is True
    assert get_account("@remove_me") is None


def test_list_accounts():
    from sable.roster.models import Account
    from sable.roster.manager import add_account, list_accounts

    add_account(Account(handle="@acc_a", org="OrgA"))
    add_account(Account(handle="@acc_b", org="OrgB"))
    add_account(Account(handle="@acc_c", org="OrgA"))

    all_accs = list_accounts()
    assert len(all_accs) == 3

    org_a = list_accounts(org="OrgA")
    assert len(org_a) == 2


def test_roster_persist(tmp_path, monkeypatch):
    monkeypatch.setenv("SABLE_HOME", str(tmp_path / ".sable2"))
    from importlib import reload
    import sable.shared.paths as paths
    import sable.roster.manager as mgr

    # Re-import to pick up new env
    from sable.roster.models import Account
    from sable.roster.manager import add_account, load_roster

    add_account(Account(handle="@persist_test"))
    roster = load_roster()
    assert roster.get("@persist_test") is not None
