"""Onboarding orchestrator for sable onboard command."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

from sable.platform.db import get_db
from sable.platform.errors import (
    SableError, ORG_NOT_FOUND, ORG_EXISTS, INVALID_CONFIG, SLUG_ORG_CONFLICT,
    AMBIGUOUS_INPUT, AWAITING_OPERATOR_INPUT,
)
from sable.platform.jobs import create_job, add_step, start_step, complete_step, fail_step


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_prospect_yaml(path: Path) -> dict:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise SableError(INVALID_CONFIG, f"Prospect YAML must be a mapping: {path}")
        return data
    except SableError:
        raise
    except Exception as e:
        raise SableError(INVALID_CONFIG, f"Failed to parse prospect YAML: {e}")


def _step_create_org(conn, job_id: str, step_id: int, org_id: str, prospect: dict) -> None:
    """Step 1: Create org if it doesn't exist."""
    existing = conn.execute("SELECT 1 FROM orgs WHERE org_id=?", (org_id,)).fetchone()
    if existing:
        complete_step(conn, step_id, output={"skipped": True, "reason": "org already exists"})
        return

    display_name = prospect.get("display_name") or prospect.get("project_name") or org_id
    discord_server_id = prospect.get("discord_server_id")
    twitter_handle = prospect.get("twitter_handle")

    conn.execute(
        "INSERT INTO orgs (org_id, display_name, discord_server_id, twitter_handle) VALUES (?, ?, ?, ?)",
        (org_id, display_name, discord_server_id, twitter_handle)
    )
    conn.commit()
    complete_step(conn, step_id, output={"created": True})


def _step_run_cult_doctor(conn, job_id: str, step_id: int, org_id: str, prospect_yaml_path: Path) -> None:
    """Step 2: Run Cult Doctor pipeline as subprocess (skip if recent run exists)."""
    # Check for recent run (within 30 days)
    project_slug = prospect_yaml_path.stem
    recent = conn.execute(
        """SELECT 1 FROM diagnostic_runs
           WHERE org_id=? AND status='completed'
             AND started_at >= datetime('now', '-30 days')
           LIMIT 1""",
        (org_id,)
    ).fetchone()

    if recent:
        complete_step(conn, step_id, output={"skipped": True, "reason": "recent diagnostic exists"})
        return

    try:
        result = subprocess.run(
            [sys.executable, "-m", "sable_cult_grader.pipeline", str(prospect_yaml_path)],
            capture_output=True, text=True, timeout=600
        )
    except subprocess.TimeoutExpired as e:
        stdout_snippet = (e.stdout or "")[:500]
        fail_step(conn, step_id, f"Cult Doctor pipeline timed out after 600s. stdout: {stdout_snippet}")
        raise SableError(INVALID_CONFIG, "Cult Doctor pipeline timed out after 10 minutes.")
    except FileNotFoundError:
        fail_step(conn, step_id, "sable_cult_grader package not found")
        raise SableError(INVALID_CONFIG, "sable_cult_grader package not found. Install it to use onboarding.")

    if result.returncode != 0:
        err_snippet = result.stderr[:1000]
        fail_step(conn, step_id, err_snippet)
        raise SableError(INVALID_CONFIG, f"Cult Doctor pipeline failed: {result.stderr[:200]}")

    complete_step(conn, step_id, output={"ran": True})


def _step_verify_entities(conn, job_id: str, step_id: int, org_id: str) -> None:
    """Step 3: Verify entities were created by Cult Doctor sync."""
    diag_run = conn.execute(
        "SELECT 1 FROM diagnostic_runs WHERE org_id=? AND status='completed' LIMIT 1",
        (org_id,)
    ).fetchone()

    if not diag_run:
        fail_step(conn, step_id, "No completed diagnostic_runs found — Cult Doctor sync may not have run")
        raise SableError(INVALID_CONFIG, "No completed diagnostic run found for org. Ensure sable_org is set in prospect config.")

    entity_count = conn.execute(
        "SELECT COUNT(*) FROM entities WHERE org_id=?", (org_id,)
    ).fetchone()[0]

    if entity_count == 0:
        fail_step(conn, step_id, "No entities found in sable.db for org after Cult Doctor run")
        raise SableError(INVALID_CONFIG, "Cult Doctor ran but no entities were synced. Check sable_org field in prospect config.")

    complete_step(conn, step_id, output={"entity_count": entity_count})


def _step_seed_roster(
    conn, job_id: str, step_id: int, org_id: str, prospect: dict,
    yes: bool = False, interactive: bool = True
) -> None:
    """Step 4: Seed managed handles into roster."""
    from sable.roster.manager import load_roster, save_roster
    from sable.roster.models import Account

    # Extract main twitter handle from prospect
    twitter_handle = prospect.get("twitter_handle")
    if not twitter_handle:
        complete_step(conn, step_id, output={"skipped": True, "reason": "no twitter_handle in prospect"})
        return

    # Normalize
    handle = twitter_handle.lstrip("@")

    roster = load_roster()
    existing = roster.get(handle)

    if existing:
        complete_step(conn, step_id, output={"skipped": True, "reason": f"@{handle} already in roster"})
        return

    if interactive and not yes and sys.stdin.isatty():
        import click
        if not click.confirm(f"Add @{handle} to roster for org {org_id}?", default=True):
            complete_step(conn, step_id, output={"declined": True})
            return
    elif interactive and not yes and not sys.stdin.isatty():
        # Non-TTY: pause
        conn.execute(
            "UPDATE job_steps SET status='awaiting_input' WHERE step_id=?", (step_id,)
        )
        conn.commit()
        raise SableError(AWAITING_OPERATOR_INPUT, "Step 4 awaiting operator input (stdin not a TTY)")

    account = Account(
        handle=f"@{handle}",
        display_name=prospect.get("display_name") or handle,
        org=org_id,
    )
    roster.upsert(account)
    save_roster(roster)
    complete_step(conn, step_id, output={"added": [handle]})


def _step_seed_watchlist(
    conn, job_id: str, step_id: int, org_id: str, prospect: dict,
    checkpoint_path: Optional[str] = None,
    yes: bool = False, interactive: bool = True
) -> None:
    """Step 5: Seed watchlist from Cult Doctor subsquad data."""
    from sable.shared.paths import watchlist_path

    # Gather candidate handles from checkpoint
    candidates = []
    team_handles = set(h.lstrip("@").lower() for h in (prospect.get("team_handles") or []))

    if checkpoint_path:
        cp = Path(checkpoint_path)
        # Try classifications.json first, then diagnostic.json
        for fname in ("classifications.json", "diagnostic.json"):
            fp = cp / "runs"
            # Find most recent run dir
            if fp.exists():
                run_dirs = sorted(fp.iterdir(), reverse=True)
                for rd in run_dirs:
                    candidate_file = rd / fname
                    if candidate_file.exists():
                        try:
                            data = json.loads(candidate_file.read_text())
                            if fname == "classifications.json":
                                # subsquad member handles
                                for item in data:
                                    h = item.get("handle", "") if isinstance(item, dict) else str(item)
                                    if h:
                                        candidates.append({"handle": h.lstrip("@"), "role": "subsquad"})
                            elif fname == "diagnostic.json":
                                for role, key in [("bridge_node", "bridge_nodes"), ("cultist_candidate", "cultist_candidates")]:
                                    for item in data.get(key, []):
                                        h = item.get("handle", "") if isinstance(item, dict) else str(item)
                                        if h:
                                            candidates.append({"handle": h.lstrip("@"), "role": role})
                        except Exception:
                            pass
                        break
                if candidates:
                    break

    if not candidates:
        # Try from diagnostic_runs result_json
        diag_row = conn.execute(
            """SELECT result_json, checkpoint_path FROM diagnostic_runs
               WHERE org_id=? AND status='completed' ORDER BY started_at DESC LIMIT 1""",
            (org_id,)
        ).fetchone()

        if diag_row:
            try:
                result = json.loads(diag_row["result_json"] or "{}")
                for role, key in [("bridge_node", "bridge_nodes"), ("cultist_candidate", "cultist_candidates")]:
                    for item in result.get(key, []):
                        h = item.get("handle", "") if isinstance(item, dict) else str(item)
                        if h:
                            candidates.append({"handle": h.lstrip("@"), "role": role})
            except Exception:
                pass

    if not candidates:
        fail_step(conn, step_id, "No subsquad data found for watchlist seeding.")
        raise SableError(INVALID_CONFIG, "No subsquad data found for watchlist seeding.")

    # Priority: bridge_node > cultist_candidate > subsquad
    priority = {"bridge_node": 0, "cultist_candidate": 1, "subsquad": 2}
    candidates.sort(key=lambda c: priority.get(c.get("role", "subsquad"), 2))

    # Load current watchlist
    wl_path = watchlist_path()
    if wl_path.exists():
        wl_data = yaml.safe_load(wl_path.read_text()) or {}
    else:
        wl_data = {}

    existing_handles = set()
    for scope in ("global", "orgs"):
        if scope == "global":
            for entry in wl_data.get("global", []):
                if isinstance(entry, dict):
                    existing_handles.add(entry.get("handle", "").lstrip("@").lower())
        else:
            for org_entries in wl_data.get("orgs", {}).values():
                for entry in (org_entries or []):
                    if isinstance(entry, dict):
                        existing_handles.add(entry.get("handle", "").lstrip("@").lower())

    # Filter
    to_add = []
    for c in candidates:
        h = c["handle"].lower()
        if h in team_handles or h in existing_handles:
            continue
        to_add.append(c)
        if len(to_add) >= 20:
            break

    if not to_add:
        complete_step(conn, step_id, output={"skipped": True, "reason": "all candidates already in watchlist"})
        return

    if interactive and not yes and sys.stdin.isatty():
        import click
        click.echo(f"Accounts to add to watchlist ({len(to_add)}):")
        for c in to_add:
            click.echo(f"  @{c['handle']} ({c.get('role', 'subsquad')})")
        if not click.confirm(f"Add these to watchlist under org '{org_id}'?", default=True):
            complete_step(conn, step_id, output={"declined": True})
            return
    elif interactive and not yes and not sys.stdin.isatty():
        conn.execute(
            "UPDATE job_steps SET status='awaiting_input' WHERE step_id=?", (step_id,)
        )
        conn.commit()
        raise SableError(AWAITING_OPERATOR_INPUT, "Step 5 awaiting operator input (stdin not a TTY)")

    # Add to watchlist
    orgs_section = wl_data.setdefault("orgs", {})
    org_entries = orgs_section.setdefault(org_id, [])
    for c in to_add:
        org_entries.append({
            "handle": c["handle"],
            "niche": "auto-seeded",
            "notes": "seeded from Cult Doctor subsquad data",
            "added_at": _now_iso(),
        })

    wl_path.parent.mkdir(parents=True, exist_ok=True)
    wl_path.write_text(yaml.dump(wl_data, default_flow_style=False, allow_unicode=True), encoding="utf-8")

    complete_step(conn, step_id, output={"added_count": len(to_add)})


def _step_initial_vault_sync(conn, job_id: str, step_id: int, org_id: str) -> None:
    """Step 6: Run initial vault sync."""
    from sable.vault.platform_sync import platform_vault_sync

    try:
        stats = platform_vault_sync(org_id)
        complete_step(conn, step_id, output=stats)
    except Exception as e:
        fail_step(conn, step_id, str(e))
        raise


def run_onboard(
    prospect_yaml: str,
    org_id: Optional[str] = None,
    yes: bool = False,
    non_interactive: bool = False,
) -> str:
    """
    Run 6-step onboarding. Returns job_id.
    """
    prospect_yaml_path = Path(prospect_yaml).expanduser()
    if not prospect_yaml_path.exists():
        raise SableError(INVALID_CONFIG, f"Prospect YAML not found: {prospect_yaml}")

    prospect = _load_prospect_yaml(prospect_yaml_path)

    # Determine org_id
    if not org_id:
        org_id = prospect.get("sable_org") or prospect.get("org_id") or prospect_yaml_path.stem

    # Check slug conflict
    project_slug = prospect.get("project_slug") or prospect_yaml_path.stem

    conn = get_db()

    # Check for slug conflict (different org using the same slug)
    existing_with_slug = conn.execute(
        """SELECT org_id FROM diagnostic_runs WHERE project_slug=? AND org_id != ? LIMIT 1""",
        (project_slug, org_id)
    ).fetchone()
    if existing_with_slug:
        raise SableError(SLUG_ORG_CONFLICT,
                         f"Project slug '{project_slug}' already used by org '{existing_with_slug['org_id']}'")

    interactive = not non_interactive

    # Check if org already exists for job creation
    org_exists = conn.execute("SELECT 1 FROM orgs WHERE org_id=?", (org_id,)).fetchone()
    job_org_id = org_id if org_exists else "system"

    # Create the job
    job_id = create_job(conn, job_org_id, "onboard",
                        config={"prospect_yaml": str(prospect_yaml_path), "org_id": org_id})

    # Add all 6 steps
    step_ids = {}
    step_names = [
        "create_org", "run_cult_doctor", "verify_entities",
        "seed_roster", "seed_watchlist", "initial_vault_sync"
    ]
    for i, name in enumerate(step_names, 1):
        step_ids[name] = add_step(conn, job_id, name, i)

    def _run_step(name, fn):
        sid = step_ids[name]
        # Check if already completed (for resume)
        row = conn.execute("SELECT status FROM job_steps WHERE step_id=?", (sid,)).fetchone()
        if row and row["status"] == "completed":
            return
        start_step(conn, sid)
        fn(conn, job_id, sid)

    try:
        _run_step("create_org", lambda c, j, s: _step_create_org(c, j, s, org_id, prospect))
        _run_step("run_cult_doctor", lambda c, j, s: _step_run_cult_doctor(c, j, s, org_id, prospect_yaml_path))
        _run_step("verify_entities", lambda c, j, s: _step_verify_entities(c, j, s, org_id))

        checkpoint_path = None
        diag_row = conn.execute(
            "SELECT checkpoint_path FROM diagnostic_runs WHERE org_id=? AND status='completed' ORDER BY started_at DESC LIMIT 1",
            (org_id,)
        ).fetchone()
        if diag_row:
            checkpoint_path = diag_row["checkpoint_path"]

        _run_step("seed_roster", lambda c, j, s: _step_seed_roster(c, j, s, org_id, prospect, yes=yes, interactive=interactive))
        _run_step("seed_watchlist", lambda c, j, s: _step_seed_watchlist(c, j, s, org_id, prospect, checkpoint_path=checkpoint_path, yes=yes, interactive=interactive))
        _run_step("initial_vault_sync", lambda c, j, s: _step_initial_vault_sync(c, j, s, org_id))

        conn.execute(
            "UPDATE jobs SET status='completed', completed_at=datetime('now') WHERE job_id=?",
            (job_id,)
        )
        conn.commit()

    except SableError:
        conn.execute(
            "UPDATE jobs SET status='failed', completed_at=datetime('now') WHERE job_id=?",
            (job_id,)
        )
        conn.commit()
        raise

    return job_id
