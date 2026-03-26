"""Watchlist CRUD, validation, and health diagnostics for pulse meta."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional

import yaml

from sable.shared.paths import watchlist_path


# ---------------------------------------------------------------------------
# Load / save
# ---------------------------------------------------------------------------

def _load_raw() -> dict:
    path = watchlist_path()
    if not path.exists():
        return {"global": [], "orgs": {}}
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    data.setdefault("global", [])
    data.setdefault("orgs", {})
    return data


def _save_raw(data: dict) -> None:
    path = watchlist_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Public CRUD
# ---------------------------------------------------------------------------

def list_watchlist(org: Optional[str] = None) -> list[dict]:
    """Return all handles for the given org (global + org-specific), or all globals."""
    data = _load_raw()
    entries = list(data.get("global", []))
    if org:
        entries += data.get("orgs", {}).get(org, [])
    return entries


def add_handle(handle: str, org: Optional[str], niche: str = "", notes: str = "") -> bool:
    """Add a handle to the watchlist. Returns True if added, False if already present."""
    handle = handle if handle.startswith("@") else f"@{handle}"
    data = _load_raw()

    bucket = data.get("orgs", {}).get(org, []) if org else data.get("global", [])
    existing_handles = {e["handle"] for e in bucket}

    if handle in existing_handles:
        return False

    entry = {"handle": handle, "niche": niche, "notes": notes, "added_at": _now_iso()}
    if org:
        data.setdefault("orgs", {}).setdefault(org, []).append(entry)
    else:
        data.setdefault("global", []).append(entry)

    _save_raw(data)
    return True


def remove_handle(handle: str, org: Optional[str]) -> bool:
    """Remove a handle. Returns True if removed."""
    handle = handle if handle.startswith("@") else f"@{handle}"
    data = _load_raw()
    removed = False

    if org:
        org_list = data.get("orgs", {}).get(org, [])
        new_list = [e for e in org_list if e["handle"] != handle]
        if len(new_list) < len(org_list):
            data["orgs"][org] = new_list
            removed = True
    else:
        global_list = data.get("global", [])
        new_list = [e for e in global_list if e["handle"] != handle]
        if len(new_list) < len(global_list):
            data["global"] = new_list
            removed = True

    if removed:
        _save_raw(data)
    return removed


def validate() -> list[str]:
    """Validate watchlist structure. Returns list of issues (empty = OK)."""
    data = _load_raw()
    issues = []

    for i, entry in enumerate(data.get("global", [])):
        if not isinstance(entry, dict):
            issues.append(f"global[{i}]: not a dict")
            continue
        if not entry.get("handle", "").startswith("@"):
            issues.append(f"global[{i}]: handle missing @ prefix: {entry.get('handle')}")

    for org, entries in data.get("orgs", {}).items():
        for i, entry in enumerate(entries):
            if not isinstance(entry, dict):
                issues.append(f"orgs.{org}[{i}]: not a dict")
                continue
            if not entry.get("handle", "").startswith("@"):
                issues.append(f"orgs.{org}[{i}]: handle missing @ prefix")

    return issues


def stats() -> dict:
    """Return summary stats about the watchlist."""
    data = _load_raw()
    global_count = len(data.get("global", []))
    orgs = data.get("orgs", {})
    org_counts = {org: len(entries) for org, entries in orgs.items()}
    niches: dict[str, int] = {}
    for entry in data.get("global", []):
        niche = entry.get("niche", "")
        if niche:
            niches[niche] = niches.get(niche, 0) + 1
    for entries in orgs.values():
        for entry in entries:
            niche = entry.get("niche", "")
            if niche:
                niches[niche] = niches.get(niche, 0) + 1
    return {
        "global_count": global_count,
        "org_counts": org_counts,
        "total": global_count + sum(org_counts.values()),
        "niches": niches,
    }


def health(org: Optional[str], db=None) -> dict:
    """
    Run health diagnostics on watchlist + existing scan data.
    Returns dict with warnings and metrics.
    No additional API calls.
    """
    entries = list_watchlist(org)
    from typing import Any
    warnings: list[str] = []
    metrics: dict[str, Any] = {}

    total = len(entries)
    metrics["total_accounts"] = total

    if total == 0:
        warnings.append("No accounts in watchlist. Need 20+ for meaningful signal.")
        return {"warnings": warnings, "metrics": metrics}
    if total < 20:
        warnings.append(f"Only {total} accounts in watchlist — 20+ recommended for meaningful signal.")

    niches: dict[str, int] = {}
    for e in entries:
        n = e.get("niche", "")
        if n:
            niches[n] = niches.get(n, 0) + 1
    metrics["niche_distribution"] = niches

    if db is not None:
        _run_db_health(org or "", entries, db, warnings, metrics)

    return {"warnings": warnings, "metrics": metrics}


def _run_db_health(org: str, entries: list[dict], db, warnings: list, metrics: dict) -> None:
    """Check DB-level health metrics."""
    from sable.pulse.meta import db as meta_db

    handles = [e["handle"] for e in entries]

    # Stale accounts: no tweets in 30 days
    stale = []
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    for handle in handles:
        profile = meta_db.get_author_profile(handle, org)
        if profile is None or not profile.get("last_seen"):
            stale.append(handle)
        elif profile["last_seen"] < cutoff:
            stale.append(handle)

    if stale:
        warnings.append(f"{len(stale)} accounts have no tweets in 30 days: {', '.join(stale[:5])}")
    metrics["stale_accounts"] = stale

    # Format diversity
    conn = meta_db.get_conn()
    format_rows = conn.execute(
        """SELECT format_bucket, COUNT(DISTINCT author_handle) as unique_authors
           FROM scanned_tweets WHERE org = ? GROUP BY format_bucket""",
        (org,),
    ).fetchall()
    conn.close()

    total_active = len(handles)
    format_diversity = {}
    low_diversity = []
    for row in format_rows:
        bucket = row["format_bucket"]
        pct = row["unique_authors"] / total_active if total_active else 0
        format_diversity[bucket] = pct
        if pct < 0.20:
            low_diversity.append(f"{bucket} ({pct:.0%})")
    metrics["format_diversity"] = format_diversity
    if low_diversity:
        warnings.append(f"Low format diversity (< 20% participation): {', '.join(low_diversity)}")

    # Author concentration
    conn = meta_db.get_conn()
    conc_rows = conn.execute(
        """SELECT author_handle, SUM(total_lift) as total_signal
           FROM scanned_tweets WHERE org = ? AND total_lift IS NOT NULL
           GROUP BY author_handle ORDER BY total_signal DESC""",
        (org,),
    ).fetchall()
    conn.close()

    if conc_rows:
        total_signal = sum(r["total_signal"] for r in conc_rows)
        top5_signal = sum(r["total_signal"] for r in conc_rows[:5])
        top5_pct = top5_signal / total_signal if total_signal else 0
        metrics["top5_author_concentration"] = top5_pct
        if top5_pct > 0.60:
            warnings.append(
                f"Top 5 accounts drive {top5_pct:.0%} of all signal — potential echo chamber."
            )
