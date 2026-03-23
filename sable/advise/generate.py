"""Main entry point for Twitter strategy brief generation."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from sable.platform.db import get_db
from sable.platform.errors import SableError, HANDLE_NOT_IN_ROSTER, NO_ORG_FOR_HANDLE, ORG_NOT_FOUND, BUDGET_EXCEEDED
from sable.platform.jobs import create_job, add_step, start_step, complete_step, fail_step
from sable.platform.cost import log_cost, check_budget
from sable.advise.stage1 import assemble_input, render_summary
from sable.advise.stage2 import synthesize, build_system_prompt
from sable.advise.template_fallback import render_fallback


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_handle(handle: str) -> str:
    return handle.lstrip("@").lower()


def _get_current_iso_week() -> str:
    now = datetime.now(timezone.utc)
    y, w, _ = now.isocalendar()
    return f"{y}-W{w:02d}"


def _check_cache(conn, org_id: str, normalized_handle: str, force: bool) -> tuple[bool, str | None]:
    """Returns (cache_hit, file_path or None)."""
    if force:
        return False, None

    rows = conn.execute(
        """SELECT * FROM artifacts
           WHERE org_id=? AND artifact_type='twitter_strategy_brief' AND stale=0
           ORDER BY created_at DESC""",
        (org_id,)
    ).fetchall()

    current_week = _get_current_iso_week()
    for row in rows:
        try:
            meta = json.loads(row["metadata_json"] or "{}")
            input_refs = json.loads(meta.get("input_refs_json") or "{}")
            if input_refs.get("handle") == normalized_handle:
                # Check if it's from current ISO week
                created = row["created_at"] or ""
                try:
                    dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    y, w, _ = dt.isocalendar()
                    if f"{y}-W{w:02d}" == current_week:
                        return True, row["path"]
                except Exception:
                    pass
        except Exception:
            continue

    return False, None


def generate_advise(
    handle: str,
    force: bool = False,
    cheap: bool = False,
    dry_run: bool = False,
) -> str:
    """
    Generate Twitter strategy brief for handle.
    Returns file path of the generated brief.
    """
    normalized_handle = _normalize_handle(handle)

    # Load roster
    from sable.roster.manager import load_roster
    roster = load_roster()
    account = roster.get(normalized_handle)
    if account is None:
        raise SableError(HANDLE_NOT_IN_ROSTER, f"Handle '{normalized_handle}' not in roster")

    org_id = account.org
    if not org_id:
        raise SableError(NO_ORG_FOR_HANDLE, f"Roster handle '{normalized_handle}' has no org")

    conn = get_db()

    # Verify org
    org = conn.execute("SELECT * FROM orgs WHERE org_id=?", (org_id,)).fetchone()
    if not org:
        raise SableError(ORG_NOT_FOUND, f"Org '{org_id}' not found in sable.db")

    # Check cache
    cache_hit, cached_path = _check_cache(conn, org_id, normalized_handle, force)
    if cache_hit:
        return cached_path

    # Dry run: estimate cost and exit
    if dry_run:
        from sable import config as cfg
        cap = float(cfg.get("platform", {}).get("cost_caps", {}).get("max_ai_usd_per_strategy_brief", 0.20))
        print(f"Estimated cost: ~${cap:.2f}. No artifact generated.")
        job_id = create_job(conn, org_id, "advise", config={"handle": normalized_handle})
        conn.execute(
            "UPDATE jobs SET status='cancelled', completed_at=datetime('now') WHERE job_id=?",
            (job_id,)
        )
        conn.commit()
        return ""

    # Check budget
    from sable import config as cfg
    platform_cfg = cfg.get("platform", {})
    degrade_mode = platform_cfg.get("degrade_mode", "fallback")
    per_brief_cap = float(platform_cfg.get("cost_caps", {}).get("max_ai_usd_per_strategy_brief", 0.20))

    budget_exceeded = False
    budget_reason = ""
    try:
        check_budget(conn, org_id)
    except SableError as e:
        if e.code == BUDGET_EXCEEDED:
            if degrade_mode == "error":
                raise
            elif degrade_mode == "skip":
                raise
            else:  # fallback
                budget_exceeded = True
                budget_reason = str(e)
        else:
            raise

    # Stage 1: Assemble input
    job_id = create_job(conn, org_id, "advise", config={"handle": normalized_handle})
    s1_step = add_step(conn, job_id, "assemble_input", 1)
    start_step(conn, s1_step)

    try:
        assembled = assemble_input(normalized_handle, org_id, conn)
        complete_step(conn, s1_step)
    except Exception as e:
        fail_step(conn, s1_step, str(e))
        conn.execute(
            "UPDATE jobs SET status='failed', completed_at=datetime('now'), error_message=? WHERE job_id=?",
            (str(e), job_id)
        )
        conn.commit()
        raise

    # Stage 2: AI synthesis
    s2_step = add_step(conn, job_id, "synthesize", 2)
    start_step(conn, s2_step)

    model = "claude-haiku-4-5-20251001" if cheap else "claude-sonnet-4-20250514"
    if budget_exceeded:
        model = "template_only"

    cost_usd = 0.0
    input_tokens = 0
    output_tokens = 0

    try:
        summary_text = render_summary(assembled)

        if model == "template_only" or budget_exceeded:
            brief_body = render_fallback(assembled, budget_reason or "template_only")
        else:
            system_prompt = build_system_prompt(assembled["profile"])
            brief_body, cost_usd, input_tokens, output_tokens = synthesize(
                system_prompt, summary_text, model=model, max_tokens=1500
            )
            log_cost(conn, org_id, "advise", cost_usd, model=model,
                     input_tokens=input_tokens, output_tokens=output_tokens, job_id=job_id)

        complete_step(conn, s2_step)
    except Exception as e:
        fail_step(conn, s2_step, str(e))
        conn.execute(
            "UPDATE jobs SET status='failed', completed_at=datetime('now'), error_message=? WHERE job_id=?",
            (str(e), job_id)
        )
        conn.commit()
        raise

    # Write output file
    from sable.shared.paths import vault_dir
    import yaml

    vault_root = vault_dir(org_id)
    playbooks_dir = vault_root / "playbooks"
    playbooks_dir.mkdir(parents=True, exist_ok=True)
    out_path = playbooks_dir / f"twitter_{normalized_handle}.md"

    freshness = assembled.get("data_freshness", {})
    frontmatter = {
        "handle": normalized_handle,
        "org": org_id,
        "generated_at": _now_iso(),
        "data_freshness": {
            "pulse_last_track": freshness.get("pulse_last_track"),
            "meta_last_scan": freshness.get("meta_last_scan"),
            "tracking_last_sync": freshness.get("tracking_last_sync"),
        },
        "model_used": model,
        "cost_usd": cost_usd,
        "stale": False,
    }

    fm_yaml = yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True, sort_keys=False)
    content = f"---\n{fm_yaml}---\n\n{brief_body}\n"
    out_path.write_text(content, encoding="utf-8")

    # Insert artifact row
    meta = json.dumps({
        "input_refs_json": json.dumps({"handle": normalized_handle}),
        "cost_usd": cost_usd,
    })
    conn.execute(
        """INSERT INTO artifacts (org_id, job_id, artifact_type, path, metadata_json, stale)
           VALUES (?, ?, 'twitter_strategy_brief', ?, ?, 0)""",
        (org_id, job_id, str(out_path), meta)
    )

    # Complete job
    conn.execute(
        "UPDATE jobs SET status='completed', completed_at=datetime('now') WHERE job_id=?",
        (job_id,)
    )
    conn.commit()

    return str(out_path)
