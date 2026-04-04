"""Main entry point for Twitter strategy brief generation."""
from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from sable.platform.db import get_db
from sable.platform.errors import SableError, HANDLE_NOT_IN_ROSTER, NO_ORG_FOR_HANDLE, ORG_NOT_FOUND, BUDGET_EXCEEDED, BRIEF_CAP_EXCEEDED, redact_error
from sable.platform.jobs import create_job, add_step, start_step, complete_step, fail_step
from sable.platform.cost import log_cost, check_budget
from sable.advise.stage1 import assemble_input, render_summary
from sable.advise.stage2 import synthesize, build_system_prompt
from sable.advise.template_fallback import render_fallback
from sable.shared.handles import normalize_handle as _normalize_handle


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
        except (json.JSONDecodeError, KeyError):
            conn.execute("UPDATE artifacts SET stale=1 WHERE artifact_id=?", (row["artifact_id"],))
            continue

    return False, None


def generate_advise(
    handle: str,
    force: bool = False,
    cheap: bool = False,
    dry_run: bool = False,
    export: bool = False,
    bridge_aware: bool = False,
    community_voice: bool = False,
    churn_data: list[dict] | None = None,
    org: str | None = None,
) -> str:
    """
    Generate Twitter strategy brief for handle.
    Returns file path of the generated brief.

    When ``org`` is provided, it overrides the roster's org association for the
    handle.  This allows SablePlatform's adapter to invoke advise for handles
    that may not yet be in the Slopper roster.
    """
    normalized_handle = _normalize_handle(handle)

    # Load roster
    from sable.roster.manager import load_roster
    roster = load_roster()
    account = roster.get(normalized_handle)

    # Resolve org_id: explicit --org flag > roster account org
    org_id = org or (account.org if account else None)
    if not org_id:
        if account is None:
            raise SableError(HANDLE_NOT_IN_ROSTER, f"Handle '{normalized_handle}' not in roster")
        raise SableError(NO_ORG_FOR_HANDLE, f"Roster handle '{normalized_handle}' has no org")

    conn = get_db()

    # Verify org
    org_row = conn.execute("SELECT * FROM orgs WHERE org_id=?", (org_id,)).fetchone()
    if not org_row:
        raise SableError(ORG_NOT_FOUND, f"Org '{org_id}' not found in sable.db")

    # Check cache
    cache_hit, cached_path = _check_cache(conn, org_id, normalized_handle, force)
    if cache_hit:
        assert cached_path is not None  # _check_cache returns non-None path on hit
        if export:
            from datetime import date as _date
            from sable.shared.files import atomic_write as _atomic_write
            _export_path = Path("output") / f"advise_{org_id}_{_date.today().isoformat()}.md"
            _atomic_write(_export_path, Path(cached_path).read_text(encoding="utf-8"))
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
        _err = redact_error(str(e))
        fail_step(conn, s1_step, _err)
        conn.execute(
            "UPDATE jobs SET status='failed', completed_at=datetime('now'), error_message=? WHERE job_id=?",
            (_err, job_id)
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

        # Inject bridge node section if requested
        if bridge_aware:
            from sable.advise.stage1 import _assemble_bridge_section, _open_db_readonly
            from sable.shared.paths import meta_db_path
            meta_conn = _open_db_readonly(meta_db_path())
            bridge_section = _assemble_bridge_section(org_id, conn, meta_conn)
            if meta_conn:
                meta_conn.close()
            if bridge_section:
                summary_text += "\n" + bridge_section

        # Inject community language section if requested
        if community_voice:
            from sable.advise.stage1 import _assemble_community_language
            cl_section = _assemble_community_language(org_id, conn)
            if cl_section:
                summary_text += "\n" + cl_section

        # Inject churn data if provided
        if churn_data and isinstance(churn_data, list):
            churn_lines = ["## At-Risk Members"]
            for m in churn_data[:20]:
                handle_str = m.get("handle", "?")
                decay = m.get("decay_score", "?")
                topics = ", ".join(m.get("topics", [])) if m.get("topics") else "none"
                churn_lines.append(f"- {handle_str}: decay={decay}, topics=[{topics}]")
            churn_lines.append("")
            summary_text += "\n" + "\n".join(churn_lines)

        # Per-brief cost cap enforcement (live runs only)
        if model not in ("template_only",) and not budget_exceeded:
            est_in = len(summary_text) // 4
            est_out = 1500
            if "haiku" in model.lower():
                est_cost = (est_in * 0.25 + est_out * 1.25) / 1_000_000
            else:
                est_cost = (est_in * 3.0 + est_out * 15.0) / 1_000_000
            if est_cost > per_brief_cap:
                raise SableError(
                    BRIEF_CAP_EXCEEDED,
                    f"Estimated brief cost ${est_cost:.4f} exceeds cap ${per_brief_cap:.4f}",
                )

        if model == "template_only" or budget_exceeded:
            brief_body = render_fallback(assembled, budget_reason or "template_only")
        else:
            system_prompt = build_system_prompt(assembled["profile"])
            brief_body, cost_usd, input_tokens, output_tokens = synthesize(
                system_prompt, summary_text, model=model, max_tokens=1500, org_id=org_id
            )

        complete_step(conn, s2_step)
    except Exception as e:
        _err = redact_error(str(e))
        fail_step(conn, s2_step, _err)
        conn.execute(
            "UPDATE jobs SET status='failed', completed_at=datetime('now'), error_message=? WHERE job_id=?",
            (_err, job_id)
        )
        conn.commit()
        raise

    # --- Deterministic data caveats block ---
    data_quality = assembled.get("data_quality", {})
    caveat_lines = []
    if not data_quality.get("pulse_ok", True):
        caveat_lines.append("- **Pulse performance data** is stale or unavailable — engagement trends may not reflect current state.")
    if not data_quality.get("meta_ok", True):
        caveat_lines.append("- **Pulse-meta trend data** is stale or unavailable — format and topic signals may be outdated.")
    if not data_quality.get("platform_ok", True):
        caveat_lines.append("- **Platform/entity data** (community members, tracking content) is incomplete or unavailable.")
    if assembled.get("failed_sources"):
        failed = ", ".join(assembled["failed_sources"])
        caveat_lines.append(f"- **Data sources that failed during assembly:** {failed}")
    if caveat_lines:
        caveat_block = "## Data Caveats\n\n" + "\n".join(caveat_lines) + "\n\n"
        brief_body = caveat_block + brief_body

    # Write output file
    from sable.shared.paths import vault_dir
    import yaml

    vault_root = vault_dir(org_id)
    playbooks_dir = vault_root / "playbooks"
    playbooks_dir.mkdir(parents=True, exist_ok=True)
    out_path = playbooks_dir / f"twitter_{normalized_handle}.md"

    freshness = assembled.get("data_freshness", {})
    data_quality = assembled.get("data_quality", {})
    stale = not data_quality.get("pulse_ok", True) or not data_quality.get("meta_ok", True)
    degraded = not data_quality.get("platform_ok", True)
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
        "stale": stale,
        "degraded": degraded,
    }

    fm_yaml = yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True, sort_keys=False)
    content = f"---\n{fm_yaml}---\n\n{brief_body}\n"

    tmp_path = out_path.with_suffix(".md.tmp")
    bak_path = out_path.with_suffix(".md.bak")
    prior_existed = out_path.exists()

    # Write new content to temp
    tmp_path.write_text(content, encoding="utf-8")

    # Backup prior file if it exists
    if prior_existed:
        shutil.copy2(out_path, bak_path)

    try:
        os.replace(tmp_path, out_path)  # atomic swap: new content now at final path
        # Insert artifact row
        meta = json.dumps({
            "input_refs_json": json.dumps({"handle": normalized_handle}),
            "cost_usd": cost_usd,
        })
        conn.execute(
            """INSERT INTO artifacts (org_id, job_id, artifact_type, path, metadata_json, stale, degraded)
               VALUES (?, ?, 'twitter_strategy_brief', ?, ?, ?, ?)""",
            (org_id, job_id, str(out_path), meta, int(stale), int(degraded))
        )
        conn.execute(
            "UPDATE jobs SET status='completed', completed_at=datetime('now') WHERE job_id=?",
            (job_id,)
        )
        conn.commit()
    except Exception:
        # Restore prior state
        if prior_existed:
            os.replace(bak_path, out_path)
        elif out_path.exists():
            out_path.unlink(missing_ok=True)
        raise
    finally:
        # Clean up temp/backup files
        if bak_path.exists():
            bak_path.unlink()
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)

    if export:
        from datetime import date as _date
        from sable.shared.files import atomic_write as _atomic_write
        _export_path = Path("output") / f"advise_{org_id}_{_date.today().isoformat()}.md"
        _atomic_write(_export_path, content)

    return str(out_path)
