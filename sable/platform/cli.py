"""Platform CLI command groups: org, entity, job, db, resume."""
from __future__ import annotations

import logging
import sys

import click

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# org
# ---------------------------------------------------------------------------

@click.group("org")
def org_group():
    """Manage orgs in sable.db."""


@org_group.command("create")
@click.argument("org_id")
@click.option("--name", required=True, help="Display name")
@click.option("--discord-server-id", default=None)
@click.option("--twitter-handle", default=None)
def org_create(org_id, name, discord_server_id, twitter_handle):
    """Create a new org."""
    from sable.platform.db import get_db
    from sable.platform.errors import SableError, ORG_EXISTS

    try:
        conn = get_db()
        existing = conn.execute("SELECT 1 FROM orgs WHERE org_id=:org_id", {"org_id": org_id}).fetchone()
        if existing:
            raise SableError(ORG_EXISTS, f"Org '{org_id}' already exists")
        with conn:
            conn.execute(
                """
                INSERT INTO orgs (org_id, display_name, discord_server_id, twitter_handle)
                VALUES (:org_id, :display_name, :discord_server_id, :twitter_handle)
                """,
                {"org_id": org_id, "display_name": name, "discord_server_id": discord_server_id, "twitter_handle": twitter_handle},
            )
        click.echo(f"Created org '{org_id}' ({name})")
    except SableError as e:
        click.echo(str(e), err=True)
        sys.exit(1)


@org_group.command("list")
def org_list():
    """List all orgs."""
    from sable.platform.db import get_db

    conn = get_db()
    rows = conn.execute("SELECT org_id, display_name, status FROM orgs ORDER BY org_id").fetchall()
    if not rows:
        click.echo("(no orgs)")
        return
    for r in rows:
        click.echo(f"  {r['org_id']:<20} {r['display_name']:<30} [{r['status']}]")


@org_group.command("status")
@click.argument("org_id")
def org_status(org_id):
    """Show org summary with cross-store freshness indicators."""
    import sqlite3
    from sable.platform.db import get_db
    from sable.platform.errors import SableError, ORG_NOT_FOUND
    from sable.platform.cost import get_weekly_spend, get_org_cost_cap

    try:
        conn = get_db()
        org = conn.execute("SELECT * FROM orgs WHERE org_id=:org_id", {"org_id": org_id}).fetchone()
        if not org:
            raise SableError(ORG_NOT_FOUND, f"Org '{org_id}' not found")

        entity_count = conn.execute(
            "SELECT COUNT(*) FROM entities WHERE org_id=:org_id AND status != 'archived'", {"org_id": org_id}
        ).fetchone()[0]

        last_diag = conn.execute(
            "SELECT started_at, status, overall_grade, fit_score FROM diagnostic_runs WHERE org_id=:org_id ORDER BY started_at DESC LIMIT 1",
            {"org_id": org_id},
        ).fetchone()

        spend = get_weekly_spend(conn, org_id)
        cap = get_org_cost_cap(conn, org_id)

        # Cross-store freshness
        last_tracking_sync = conn.execute(
            "SELECT MAX(completed_at) FROM sync_runs WHERE org_id=:org_id AND sync_type=:sync_type",
            {"org_id": org_id, "sync_type": "sable_tracking"},
        ).fetchone()[0]

        last_vault_sync = conn.execute(
            "SELECT MAX(created_at) FROM artifacts WHERE org_id=:org_id AND artifact_type=:artifact_type",
            {"org_id": org_id, "artifact_type": "vault_index"},
        ).fetchone()[0]

        # Pulse freshness (read-only, best-effort)
        pulse_last_track = None
        try:
            from sable.shared.paths import pulse_db_path
            pulse_path = pulse_db_path()
            if pulse_path.exists():
                pconn = sqlite3.connect(f"file:{pulse_path}?mode=ro", uri=True)
                pconn.row_factory = sqlite3.Row
                row = pconn.execute(
                    "SELECT MAX(taken_at) FROM snapshots"
                ).fetchone()
                pulse_last_track = row[0] if row else None
                pconn.close()
        except Exception as e:
            from sable.platform.errors import redact_error
            logger.warning("Could not read pulse freshness: %s", redact_error(str(e)))

        # Meta freshness (read-only, best-effort)
        meta_last_scan = None
        try:
            from sable.shared.paths import meta_db_path
            meta_path = meta_db_path()
            if meta_path.exists():
                mconn = sqlite3.connect(f"file:{meta_path}?mode=ro", uri=True)
                mconn.row_factory = sqlite3.Row
                row = mconn.execute(
                    "SELECT MAX(completed_at) FROM scan_runs WHERE org=?", (org_id,)
                ).fetchone()
                meta_last_scan = row[0] if row else None
                mconn.close()
        except Exception as e:
            from sable.platform.errors import redact_error
            logger.warning("Could not read meta freshness: %s", redact_error(str(e)))

        click.echo(f"Org: {org['org_id']} — {org['display_name']}")
        click.echo(f"  Status:               {org['status']}")
        click.echo(f"  Entities:             {entity_count}")
        if last_diag:
            grade_str = f" grade={last_diag['overall_grade']}" if last_diag['overall_grade'] else ""
            fit_str = f" fit={last_diag['fit_score']}" if last_diag['fit_score'] is not None else ""
            click.echo(f"  Diagnostic:           {last_diag['started_at']} [{last_diag['status']}]{grade_str}{fit_str}")
        else:
            click.echo("  Diagnostic:           (no runs yet)")
        click.echo(f"  Weekly AI spend:      ${spend:.2f} / ${cap:.2f} cap")
        click.echo(f"  pulse_last_track:     {pulse_last_track or '(none)'}")
        click.echo(f"  meta_last_scan:       {meta_last_scan or '(none)'}")
        click.echo(f"  tracking_last_sync:   {last_tracking_sync or '(none)'}")
        click.echo(f"  vault_last_sync:      {last_vault_sync or '(none)'}")

    except SableError as e:
        click.echo(str(e), err=True)
        sys.exit(1)


@org_group.command("set-config")
@click.argument("org_id")
@click.argument("key")
@click.argument("value")
def org_set_config(org_id, key, value):
    """Set a JSON config key on an org."""
    import json
    from sable.platform.db import get_db
    from sable.platform.errors import SableError, ORG_NOT_FOUND

    try:
        conn = get_db()
        row = conn.execute("SELECT config_json FROM orgs WHERE org_id=:org_id", {"org_id": org_id}).fetchone()
        if not row:
            raise SableError(ORG_NOT_FOUND, f"Org '{org_id}' not found")
        cfg = json.loads(row["config_json"] or "{}")
        cfg[key] = value
        with conn:
            conn.execute(
                # TODO: datetime('now') is SQLite-specific — replace for Postgres
                "UPDATE orgs SET config_json=:config_json, updated_at=datetime('now') WHERE org_id=:org_id",
                {"config_json": json.dumps(cfg), "org_id": org_id},
            )
        click.echo(f"Set {key}={value!r} on org '{org_id}'")
    except SableError as e:
        click.echo(str(e), err=True)
        sys.exit(1)


# ---------------------------------------------------------------------------
# entity
# ---------------------------------------------------------------------------

@click.group("entity")
def entity_group():
    """Manage entities in sable.db."""


@entity_group.command("search")
@click.argument("org_id")
@click.argument("query")
def entity_search(org_id, query):
    """Search entities by display name or handle."""
    from sable.platform.db import get_db

    conn = get_db()
    like = f"%{query}%"
    rows = conn.execute(
        """
        SELECT DISTINCT e.entity_id, e.display_name, e.status, e.org_id
        FROM entities e
        LEFT JOIN entity_handles h ON e.entity_id = h.entity_id
        WHERE e.org_id = :org_id
          AND (e.display_name LIKE :like OR h.handle LIKE :like)
          AND e.status != 'archived'
        LIMIT 50
        """,
        {"org_id": org_id, "like": like},
    ).fetchall()

    if not rows:
        click.echo("(no results)")
        return
    for r in rows:
        name = r["display_name"] or "(unnamed)"
        click.echo(f"  {r['entity_id'][:12]}  {name:<30} [{r['status']}]")


@entity_group.command("show")
@click.argument("entity_id")
def entity_show(entity_id):
    """Show entity detail including handles and active tags."""
    from sable.platform.db import get_db
    from sable.platform.errors import SableError
    from sable.platform.tags import get_active_tags

    try:
        conn = get_db()
        row = conn.execute("SELECT * FROM entities WHERE entity_id=:entity_id", {"entity_id": entity_id}).fetchone()
        if not row:
            raise SableError("ENTITY_NOT_FOUND", f"Entity '{entity_id}' not found")

        handles = conn.execute(
            "SELECT platform, handle, is_primary FROM entity_handles WHERE entity_id=:entity_id ORDER BY platform, handle",
            {"entity_id": entity_id},
        ).fetchall()
        tags = get_active_tags(conn, entity_id)

        click.echo(f"Entity: {entity_id}")
        click.echo(f"  Org:          {row['org_id']}")
        click.echo(f"  Display name: {row['display_name'] or '(none)'}")
        click.echo(f"  Status:       {row['status']}")
        click.echo(f"  Source:       {row['source']}")
        click.echo(f"  Updated:      {row['updated_at']}")
        click.echo(f"  Handles ({len(handles)}):")
        for h in handles:
            primary = " [primary]" if h["is_primary"] else ""
            click.echo(f"    {h['platform']}:{h['handle']}{primary}")
        click.echo(f"  Active tags ({len(tags)}):")
        for t in tags:
            click.echo(f"    {t['tag']} (conf={t['confidence']:.2f})")

    except SableError as e:
        click.echo(str(e), err=True)
        sys.exit(1)


@entity_group.command("archive")
@click.argument("entity_id")
def entity_archive(entity_id):
    """Archive an entity."""
    from sable.platform.db import get_db
    from sable.platform.errors import SableError
    from sable.platform.entities import archive_entity

    try:
        conn = get_db()
        archive_entity(conn, entity_id)
        click.echo(f"Archived entity '{entity_id}'")
    except SableError as e:
        click.echo(str(e), err=True)
        sys.exit(1)


# ---------------------------------------------------------------------------
# job
# ---------------------------------------------------------------------------

@click.group("job")
def job_group():
    """Inspect jobs in sable.db."""


@job_group.command("list")
@click.argument("org_id")
@click.option("--status", default=None, help="Filter by status")
def job_list(org_id, status):
    """List jobs for an org."""
    from sable.platform.db import get_db

    conn = get_db()
    if status:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE org_id=:org_id AND status=:status ORDER BY created_at DESC",
            {"org_id": org_id, "status": status},
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE org_id=:org_id ORDER BY created_at DESC LIMIT 50",
            {"org_id": org_id},
        ).fetchall()

    if not rows:
        click.echo("(no jobs)")
        return
    for r in rows:
        click.echo(f"  {r['job_id'][:12]}  {r['job_type']:<25} [{r['status']}]  {r['created_at']}")


@job_group.command("show")
@click.argument("job_id")
def job_show(job_id):
    """Show job detail including all steps."""
    from sable.platform.db import get_db
    from sable.platform.jobs import get_job, get_resumable_steps

    conn = get_db()
    job = get_job(conn, job_id)
    if not job:
        click.echo(f"Job '{job_id}' not found", err=True)
        sys.exit(1)

    steps = get_resumable_steps(conn, job_id)

    click.echo(f"Job: {job['job_id']}")
    click.echo(f"  Org:     {job['org_id']}")
    click.echo(f"  Type:    {job['job_type']}")
    click.echo(f"  Status:  {job['status']}")
    click.echo(f"  Created: {job['created_at']}")
    click.echo(f"  Steps ({len(steps)}):")
    for s in steps:
        err = f"  err: {s['error']}" if s["error"] else ""
        click.echo(
            f"    [{s['step_order']:02d}] {s['step_name']:<30} [{s['status']}] retries={s['retries']}{err}"
        )


# ---------------------------------------------------------------------------
# db
# ---------------------------------------------------------------------------

@click.group("db")
def db_group():
    """Manage sable.db schema."""


@db_group.command("migrate")
def db_migrate():
    """Apply pending migrations to sable.db, pulse.db, and meta.db."""
    from sable.platform.db import get_db

    conn = get_db()
    row = conn.execute("SELECT version FROM schema_version").fetchone()
    click.echo(f"sable.db  → schema version {row['version']}")

    # pulse.db
    from sable.pulse.db import migrate as pulse_migrate, SCHEMA_VERSION as pulse_v
    pulse_migrate()
    click.echo(f"pulse.db  → schema version {pulse_v}")

    # meta.db
    from sable.pulse.meta.db import migrate as meta_migrate, SCHEMA_VERSION as meta_v
    meta_migrate()
    click.echo(f"meta.db   → schema version {meta_v}")


@db_group.command("status")
def db_status():
    """Show sable.db file path and schema version."""
    from sable.shared.paths import sable_db_path
    from sable.platform.db import get_db

    path = sable_db_path()
    conn = get_db()
    row = conn.execute("SELECT version FROM schema_version").fetchone()
    click.echo(f"Path:    {path}")
    click.echo(f"Version: {row['version']}")


# ---------------------------------------------------------------------------
# resume
# ---------------------------------------------------------------------------

@click.command("resume")
@click.argument("job_id")
@click.option("--max-retries", default=2, show_default=True)
def resume_command(job_id, max_retries):
    """Resume a job, printing one line per step describing the action taken."""
    from sable.platform.db import get_db
    from sable.platform.errors import SableError
    from sable.platform.jobs import resume_job

    try:
        conn = get_db()
        actions = resume_job(conn, job_id, max_retries=max_retries)
        if not actions:
            click.echo(f"Job '{job_id}' has no steps.")
            return
        for item in actions:
            click.echo(f"  [{item['action'].upper():5}] {item['step_name']}")
    except SableError as e:
        click.echo(str(e), err=True)
        sys.exit(1)
