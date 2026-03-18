"""Tweet bank integration — append approved tweets to roster."""
from __future__ import annotations

from sable.roster.manager import append_tweet, require_account


def save_to_bank(handle: str, tweet: str) -> None:
    """Append a tweet to the account's bank after approval."""
    require_account(handle)
    append_tweet(handle, tweet)


def interactive_approve(handle: str, candidates: list[str]) -> list[str]:
    """
    CLI interactive loop: show each candidate, ask y/n/edit.
    Returns list of approved tweets.
    """
    approved = []
    for i, tweet in enumerate(candidates):
        print(f"\n[{i+1}/{len(candidates)}] {tweet}")
        choice = input("Save to bank? [y/n/e(edit)/q(quit)]: ").strip().lower()
        if choice == "y":
            save_to_bank(handle, tweet)
            approved.append(tweet)
            print("  ✓ Saved")
        elif choice == "e":
            edited = input("Edit tweet: ").strip()
            if edited:
                save_to_bank(handle, edited)
                approved.append(edited)
                print("  ✓ Saved (edited)")
        elif choice == "q":
            break
    return approved
