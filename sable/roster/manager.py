"""CRUD operations on roster.yaml."""
from __future__ import annotations

import fcntl
import os
from datetime import datetime, timezone
from typing import Optional
import yaml

from sable.shared.files import atomic_write
from sable.shared.paths import roster_path
from sable.roster.models import Account, Roster


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_roster() -> Roster:
    path = roster_path()
    if not path.exists():
        return Roster()
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    accounts_data = data.get("accounts", [])
    accounts = [Account.from_yaml_dict(a) for a in accounts_data]
    return Roster(version=data.get("version", 1), accounts=accounts)


def save_roster(roster: Roster) -> None:
    path = roster_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = str(path) + ".lock"
    data = {
        "version": roster.version,
        "accounts": [a.to_yaml_dict() for a in roster.accounts],
    }
    content = yaml.dump(data, default_flow_style=False, allow_unicode=True)
    with open(lock_path, "w") as lock_f:
        fcntl.flock(lock_f, fcntl.LOCK_EX)
        try:
            atomic_write(path, content)
        finally:
            fcntl.flock(lock_f, fcntl.LOCK_UN)


def get_account(handle: str) -> Optional[Account]:
    return load_roster().get(handle)


def require_account(handle: str) -> Account:
    acc = get_account(handle)
    if acc is None:
        handle = handle if handle.startswith("@") else f"@{handle}"
        raise ValueError(f"Account {handle} not found in roster. Run: sable roster add {handle}")
    return acc


def add_account(account: Account) -> Account:
    roster = load_roster()
    account.created_at = _now()
    account.updated_at = _now()
    if roster.get(account.handle):
        raise ValueError(f"Account {account.handle} already exists. Use update instead.")
    roster.upsert(account)
    save_roster(roster)
    return account


def update_account(handle: str, **kwargs) -> Account:
    roster = load_roster()
    account = roster.get(handle)
    if account is None:
        raise ValueError(f"Account {handle} not found.")
    for key, value in kwargs.items():
        if hasattr(account, key):
            setattr(account, key, value)
    account.updated_at = _now()
    roster.upsert(account)
    save_roster(roster)
    return account


def remove_account(handle: str) -> bool:
    roster = load_roster()
    removed = roster.remove(handle)
    if removed:
        save_roster(roster)
    return removed


def list_accounts(org: Optional[str] = None, active_only: bool = False) -> list[Account]:
    roster = load_roster()
    accounts = roster.accounts
    if org:
        accounts = [a for a in accounts if a.org == org]
    if active_only:
        accounts = [a for a in accounts if a.active]
    return accounts


def append_tweet(handle: str, tweet: str) -> None:
    roster = load_roster()
    account = roster.get(handle)
    if account is None:
        raise ValueError(f"Account {handle} not found.")
    if tweet not in account.tweet_bank:
        account.tweet_bank.append(tweet)
        account.updated_at = _now()
        roster.upsert(account)
        save_roster(roster)


def update_learned_preferences(handle: str, prefs: dict) -> None:
    roster = load_roster()
    account = roster.get(handle)
    if account is None:
        raise ValueError(f"Account {handle} not found.")
    account.learned_preferences.update(prefs)
    account.updated_at = _now()
    roster.upsert(account)
    save_roster(roster)
