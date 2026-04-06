"""Platform vault sync — generates Obsidian vault from sable.db data.

This is entirely template-based. Zero AI calls. Zero cost_events.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from sable.platform.db import get_db
from sable.platform.errors import SableError, ORG_NOT_FOUND
from sable.platform.jobs import create_job, add_step, start_step, complete_step, fail_step


_VAULT_ARTIFACT_TYPES = frozenset({
    "vault_entity_note",
    "vault_index",
    "vault_diagnostic_summary",
    "vault_diagnostic_history",
})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_to_temp(path: Path, content: str) -> Path:
    """Write content to a temp file in path's parent dir. Return the temp Path.
    Does NOT rename to final — caller is responsible for os.replace or cleanup."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp_new_", suffix=".md")
    try:
        os.write(fd, content.encode("utf-8"))
        os.close(fd)
        return Path(tmp)
    except Exception:
        os.close(fd)
        os.unlink(tmp)
        raise


def _write_partial_sync_sentinel(vault_root: Path) -> None:
    try:
        (vault_root / "_PARTIAL_SYNC").write_text("", encoding="utf-8")
    except Exception:
        pass


def _safe_vault_root(org_id: str) -> Path:
    from sable.shared.paths import vault_dir
    return vault_dir(org_id)


def _is_inside_vault_root(file_path: str, vault_root: Path) -> bool:
    try:
        resolved = Path(os.path.realpath(file_path))
        resolved_root = Path(os.path.realpath(str(vault_root)))
        resolved.relative_to(resolved_root)
        return True
    except ValueError:
        return False


def _build_entity_note(entity: dict, handles: list[dict], tags: list[dict],
                        notes: list[dict], content_items: list[dict],
                        diag_runs: list[dict], org_id: str) -> str:
    # Frontmatter
    twitter = next((h["handle"] for h in handles if h["platform"] == "twitter"), None)
    discord = next((h["handle"] for h in handles if h["platform"] == "discord"), None)
    telegram = next((h["handle"] for h in handles if h["platform"] == "telegram"), None)
    wallet = next((h["handle"] for h in handles if h["platform"] == "wallet"), None)
    tag_names = [t["tag"] for t in tags]

    fm = {
        "entity_id": entity["entity_id"],
        "org": org_id,
        "display_name": entity["display_name"] or "",
        "status": entity["status"],
        "handles": {
            "twitter": twitter,
            "discord": discord,
            "telegram": telegram,
            "wallet": wallet,
        },
        "tags": tag_names,
        "content_count": len(content_items),
        "last_updated": entity["updated_at"] or _now_iso(),
    }

    import yaml
    fm_yaml = yaml.dump(fm, default_flow_style=False, allow_unicode=True, sort_keys=False)
    lines = [f"---\n{fm_yaml}---\n"]

    # Tags section
    if tags:
        lines.append("\n## Tags\n")
        for t in tags:
            source = t["source"] or "auto"
            context = f"confidence={t['confidence']:.2f}"
            added = t["added_at"] or ""
            lines.append(f"- **{t['tag']}** — {source}, {context} ({added})\n")

    # Content section (last 90 days)
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    recent_content = [
        c for c in content_items
        if (c.get("source_time") or c.get("created_at") or "") >= cutoff
    ]
    if recent_content:
        lines.append("\n## Content\n")
        for c in recent_content:
            fmt = c["content_type"] or "unknown"
            body_preview = (c["body"] or "")[:80]
            url = c["url"] if isinstance(c, dict) else None
            display_time = c.get("source_time") or c.get("created_at") or ""
            line = f"- [{fmt}] {body_preview} ({display_time})"
            if url:
                line += f" [link]({url})"
            lines.append(line + "\n")

    # Diagnostic mentions
    mentions = []
    for run in diag_runs:
        result = {}
        try:
            result = json.loads(run["result_json"] or "{}")
        except Exception:
            pass
        # Look for entity in cultist_candidates, bridge_nodes, team_members
        for role in ("cultist_candidates", "bridge_nodes", "team_members"):
            for item in result.get(role, []):
                handle = item.get("handle", "") if isinstance(item, dict) else str(item)
                if handle and any(handle.lower() == h["handle"].lower() for h in handles):
                    run_date = run["run_date"] or (run["started_at"] or "")[:10]
                    grade = run["overall_grade"] or "?"
                    mentions.append(f"- Tagged as {role.rstrip('s')} in run {run_date} (grade: {grade})")
                    break
    for t in tags:
        score = t["confidence"]
        added = t.get("added_at") or ""
        if len(mentions) < 3:
            mentions.append(
                f"- Tagged as {t['tag']} (score: {score:.2f}) (added: {added})"
            )
    if mentions:
        lines.append("\n## Diagnostic Mentions\n")
        for m in mentions[:3]:
            lines.append(m + "\n")

    # Operator notes
    lines.append("\n## Operator Notes\n")
    if notes:
        for n in notes:
            lines.append(n["body"] + "\n")
    else:
        lines.append("No notes.\n")

    return "".join(lines)


def _build_index(org: dict, entities: list[dict], diag_runs: list[dict],
                 total_artifacts: int, stale_artifacts: int) -> str:
    import yaml
    org_id = org["org_id"]
    display_name = org["display_name"]
    fm = {
        "org": org_id,
        "display_name": display_name,
        "generated_at": _now_iso(),
    }
    fm_yaml = yaml.dump(fm, default_flow_style=False, allow_unicode=True, sort_keys=False)
    lines = [f"---\n{fm_yaml}---\n", f"\n# {display_name}\n"]

    lines.append(f"\n## Entities ({len(entities)})\n")
    for e in entities:
        name = e["display_name"] or e["entity_id"]
        status = e["status"]
        lines.append(f"- [{name}](entities/{e['entity_id']}.md) — {status}\n")

    lines.append("\n## Latest Diagnostic\n")
    if diag_runs:
        r = diag_runs[0]
        run_date = r["run_date"] or (r["started_at"] or "")[:10]
        grade = r["overall_grade"] or "?"
        fit = r["fit_score"] or "?"
        action = r["recommended_action"] or "?"
        lines.append(f"Run {run_date}: Grade {grade}, Fit {fit}, Action: {action}\n")
    else:
        lines.append("No diagnostics yet.\n")

    lines.append(f"\n## Artifacts\n{total_artifacts} total, {stale_artifacts} stale\n")
    return "".join(lines)


def _build_diagnostic_summary(org: dict, diag_runs: list[dict]) -> str:
    import yaml
    if not diag_runs:
        return "---\norg: " + org["org_id"] + "\n---\n\nNo diagnostics yet.\n"
    r = diag_runs[0]
    run_date = r["run_date"] or (r["started_at"] or "")[:10]
    fm = {
        "org": org["org_id"],
        "generated_at": _now_iso(),
        "latest_run_date": run_date,
        "overall_grade": r["overall_grade"],
        "fit_score": r["fit_score"],
        "recommended_action": r["recommended_action"],
    }
    fm_yaml = yaml.dump(fm, default_flow_style=False, allow_unicode=True, sort_keys=False)
    lines = [f"---\n{fm_yaml}---\n", f"\n# Diagnostic Summary\n\n**Latest run:** {run_date}\n"]
    lines.append(f"**Grade:** {r['overall_grade'] or '?'}  \n")
    lines.append(f"**Fit score:** {r['fit_score'] or '?'}  \n")
    lines.append(f"**Recommended action:** {r['recommended_action'] or '?'}  \n")
    if r["sable_verdict"]:
        lines.append(f"\n**Verdict:** {r['sable_verdict']}\n")
    return "".join(lines)


def _build_diagnostic_history_entry(org: dict, r: dict) -> str:
    import yaml
    run_date = r["run_date"] or (r["started_at"] or "")[:10]
    run_id = r["run_id"]
    fm = {
        "org": org["org_id"],
        "run_id": run_id,
        "run_date": run_date,
        "overall_grade": r["overall_grade"],
        "fit_score": r["fit_score"],
        "recommended_action": r["recommended_action"],
        "status": r["status"],
    }
    fm_yaml = yaml.dump(fm, default_flow_style=False, allow_unicode=True, sort_keys=False)
    lines = [f"---\n{fm_yaml}---\n", f"\n# Diagnostic Run {run_id} ({run_date})\n\n"]
    lines.append(f"**Grade:** {r['overall_grade'] or '?'}  \n")
    lines.append(f"**Fit score:** {r['fit_score'] or '?'}  \n")
    lines.append(f"**Recommended action:** {r['recommended_action'] or '?'}  \n")
    if r["sable_verdict"]:
        lines.append(f"\n**Verdict:** {r['sable_verdict']}\n")
    return "".join(lines)


import logging as _logging
_logger = _logging.getLogger(__name__)


def _cleanup_temps(temp_writes: list[tuple[Path, Path]]) -> None:
    """Best-effort removal of temp files from a staged write set."""
    for tmp, _ in temp_writes:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass


def platform_vault_sync(org_id: str) -> dict:
    """
    Regenerate the Obsidian vault for org_id from sable.db.
    Template-based — no AI calls.
    Returns a summary dict: {entities_written, index_written, diagnostics_written, ...}
    """
    conn = get_db()

    # Detect and clear _PARTIAL_SYNC sentinel from any previous interrupted sync
    vault_root_early = _safe_vault_root(org_id)
    sentinel = vault_root_early / "_PARTIAL_SYNC"
    if sentinel.exists():
        _logger.warning(
            "Partial sync sentinel detected for org '%s' — previous sync was interrupted. "
            "Clearing sentinel and retrying.", org_id
        )
        sentinel.unlink(missing_ok=True)

    # Verify org
    org = conn.execute("SELECT * FROM orgs WHERE org_id=?", (org_id,)).fetchone()
    if not org:
        raise SableError(ORG_NOT_FOUND, f"Org '{org_id}' not found in sable.db")
    org = dict(org)

    vault_root = _safe_vault_root(org_id)

    # Create job
    job_id = create_job(conn, org_id, "vault_sync")
    step_id = add_step(conn, job_id, "generate_vault", 1)
    start_step(conn, step_id)

    try:
        stats = _do_sync(conn, org, vault_root, job_id)
        complete_step(conn, step_id, output=stats)
        conn.execute(
            "UPDATE jobs SET status='completed', completed_at=datetime('now'), result_json=? WHERE job_id=?",
            (json.dumps(stats), job_id)
        )
        conn.commit()
        return stats
    except Exception as e:
        from sable.platform.errors import redact_error
        _err = redact_error(str(e))
        fail_step(conn, step_id, _err)
        conn.execute(
            "UPDATE jobs SET status='failed', completed_at=datetime('now'), error_message=? WHERE job_id=?",
            (_err, job_id)
        )
        conn.commit()
        raise


def _do_sync(conn, org: dict, vault_root: Path, job_id: str) -> dict:
    org_id = org["org_id"]

    # --- Step 1: Record old vault artifacts — defer deletion until after generation succeeds ---
    old_artifacts = conn.execute(
        f"SELECT * FROM artifacts WHERE org_id=? AND artifact_type IN ({','.join(['?']*len(_VAULT_ARTIFACT_TYPES))})",
        [org_id, *list(_VAULT_ARTIFACT_TYPES)]
    ).fetchall()

    old_artifact_ids = []
    old_artifact_paths: set[str] = set()
    for art in old_artifacts:
        fp = art["path"]
        if fp and _is_inside_vault_root(fp, vault_root):
            old_artifact_ids.append(art["artifact_id"])
            old_artifact_paths.add(fp)

    # --- Step 2: Query all data for org (AR5-12: paginated with LIMIT 500 OFFSET n) ---
    entities: list[dict] = []
    _page_size = 500
    _offset = 0
    while True:
        page = [dict(r) for r in conn.execute(
            "SELECT * FROM entities WHERE org_id=? AND status != 'archived' ORDER BY display_name LIMIT ? OFFSET ?",
            (org_id, _page_size, _offset)
        ).fetchall()]
        entities.extend(page)
        if len(page) < _page_size:
            break
        _offset += _page_size

    # Load handles, tags, notes, content_items per entity
    entity_handles_map = {}
    entity_tags_map = {}
    entity_notes_map = {}
    entity_content_map = {}

    for e in entities:
        eid = e["entity_id"]
        entity_handles_map[eid] = [dict(r) for r in conn.execute(
            "SELECT * FROM entity_handles WHERE entity_id=? ORDER BY platform",
            (eid,)
        ).fetchall()]

        entity_tags_map[eid] = [dict(r) for r in conn.execute(
            """SELECT * FROM entity_tags
               WHERE entity_id=? AND is_current=1 AND (expires_at IS NULL OR expires_at > datetime('now'))
               ORDER BY added_at""",
            (eid,)
        ).fetchall()]

        entity_notes_map[eid] = [dict(r) for r in conn.execute(
            "SELECT * FROM entity_notes WHERE entity_id=? ORDER BY created_at",
            (eid,)
        ).fetchall()]

        # content_items: get url from metadata_json
        content_rows = conn.execute(
            "SELECT *, COALESCE(posted_at, created_at) AS source_time "
            "FROM content_items WHERE entity_id=? "
            "ORDER BY COALESCE(posted_at, created_at) DESC LIMIT 50",
            (eid,)
        ).fetchall()
        items = []
        for row in content_rows:
            d = dict(row)
            try:
                meta = json.loads(d.get("metadata_json") or "{}")
                d["url"] = meta.get("url")
            except Exception:
                d["url"] = None
            items.append(d)
        entity_content_map[eid] = items

    # Diagnostic runs
    diag_runs = [dict(r) for r in conn.execute(
        """SELECT * FROM diagnostic_runs
           WHERE org_id=? AND status='completed'
           ORDER BY started_at DESC""",
        (org_id,)
    ).fetchall()]

    # Artifact counts for index
    total_artifacts = conn.execute(
        "SELECT COUNT(*) FROM artifacts WHERE org_id=?", (org_id,)
    ).fetchone()[0]
    stale_artifacts = conn.execute(
        "SELECT COUNT(*) FROM artifacts WHERE org_id=? AND stale=1", (org_id,)
    ).fetchone()[0]

    new_artifact_rows = []
    temp_writes: list[tuple[Path, Path]] = []

    # --- Steps 3-5: Phase A — write all generated content to temp files ---
    try:
        # --- Step 3: Generate entity notes ---
        entities_dir = vault_root / "entities"
        entities_dir.mkdir(parents=True, exist_ok=True)

        for e in entities:
            eid = e["entity_id"]
            content = _build_entity_note(
                e, entity_handles_map[eid], entity_tags_map[eid],
                entity_notes_map[eid], entity_content_map[eid],
                diag_runs, org_id
            )
            note_path = entities_dir / f"{eid}.md"
            tmp = _write_to_temp(note_path, content)
            temp_writes.append((tmp, note_path))
            new_artifact_rows.append((org_id, job_id, "vault_entity_note", str(note_path),
                                       json.dumps({"entity_id": eid}), 0))

        # --- Step 4: Generate index ---
        index_path = vault_root / "_index.md"
        index_content = _build_index(org, entities, diag_runs, total_artifacts, stale_artifacts)
        tmp = _write_to_temp(index_path, index_content)
        temp_writes.append((tmp, index_path))
        new_artifact_rows.append((org_id, job_id, "vault_index", str(index_path), "{}", 0))

        # --- Step 5: Generate diagnostic files ---
        diag_dir = vault_root / "diagnostics"
        diag_dir.mkdir(parents=True, exist_ok=True)
        history_dir = diag_dir / "history"
        history_dir.mkdir(parents=True, exist_ok=True)

        # latest.md
        latest_path = diag_dir / "latest.md"
        latest_content = _build_diagnostic_summary(org, diag_runs)
        tmp = _write_to_temp(latest_path, latest_content)
        temp_writes.append((tmp, latest_path))
        new_artifact_rows.append((org_id, job_id, "vault_diagnostic_summary", str(latest_path), "{}", 0))

        # history/{run_id}.md for each run
        for r in diag_runs:
            run_id = r["run_id"]
            hist_path = history_dir / f"{run_id}.md"
            hist_content = _build_diagnostic_history_entry(org, r)
            tmp = _write_to_temp(hist_path, hist_content)
            temp_writes.append((tmp, hist_path))
            new_artifact_rows.append((org_id, job_id, "vault_diagnostic_history", str(hist_path),
                                       json.dumps({"run_id": run_id}), 0))

    except Exception:
        _cleanup_temps(temp_writes)
        raise

    # --- Step 6: Stage pulse meta report into the same temp-write set (CRIT-1 fix) ---
    pulse_dir = vault_root / "pulse"
    pulse_dir.mkdir(parents=True, exist_ok=True)
    meta_report_dest = pulse_dir / "meta_report.md"
    _remove_pulse_dest = False

    try:
        pulse_meta_artifact = conn.execute(
            """SELECT * FROM artifacts WHERE org_id=? AND artifact_type='pulse_meta_report'
               ORDER BY created_at DESC LIMIT 1""",
            (org_id,)
        ).fetchone()

        if pulse_meta_artifact and pulse_meta_artifact["path"]:
            src = Path(pulse_meta_artifact["path"])
            try:
                pulse_content = src.read_text(encoding="utf-8")
            except (OSError, FileNotFoundError):
                _remove_pulse_dest = True
            else:
                pulse_tmp = _write_to_temp(meta_report_dest, pulse_content)
                temp_writes.append((pulse_tmp, meta_report_dest))
        else:
            _remove_pulse_dest = True
    except Exception:
        _cleanup_temps(temp_writes)
        raise

    try:
        # --- Phase B: batch rename ALL temp files (including pulse report) to final paths ---
        for tmp, final in temp_writes:
            os.replace(str(tmp), str(final))

        if _remove_pulse_dest:
            meta_report_dest.unlink(missing_ok=True)

        # --- Step 7: All generation + renames succeeded — delete old artifacts ---
        new_paths = {row[3] for row in new_artifact_rows}
        for fp in old_artifact_paths:
            if fp not in new_paths:
                try:
                    Path(fp).unlink(missing_ok=True)
                except Exception:
                    pass

        if old_artifact_ids:
            placeholders = ",".join("?" * len(old_artifact_ids))
            conn.execute(
                f"DELETE FROM artifacts WHERE artifact_id IN ({placeholders})",
                old_artifact_ids
            )

        # --- Step 8: Insert new artifact rows and commit ---
        conn.executemany(
            """INSERT INTO artifacts (org_id, job_id, artifact_type, path, metadata_json, stale)
               VALUES (?, ?, ?, ?, ?, ?)""",
            new_artifact_rows
        )
        conn.commit()
    except Exception:
        _cleanup_temps(temp_writes)
        _write_partial_sync_sentinel(vault_root)
        raise

    return {
        "entities_written": len(entities),
        "diagnostics_written": len(diag_runs),
        "index_written": 1,
    }
