"""CLI for sable tracking commands (delegates to SableTracking)."""
from __future__ import annotations

import asyncio
import json
import sys
import click


@click.group("tracking")
def tracking_group():
    """Manage SableTracking sync operations."""


@tracking_group.command("sync")
@click.argument("org_id")
def tracking_sync(org_id):
    """Sync SableTracking data into sable.db. Delegates to SableTracking."""
    try:
        from app.platform_sync import sync_to_platform
    except ImportError:
        click.echo(
            "Required package not found: app.platform_sync. "
            "Ensure SableTracking is installed or on PYTHONPATH.",
            err=True,
        )
        sys.exit(1)

    from sable.platform.db import get_db
    from sable.platform.errors import SableError, ORG_NOT_FOUND
    from sable.platform.jobs import create_job, add_step, start_step, complete_step, fail_step

    conn = get_db()

    # Verify org exists
    org = conn.execute("SELECT 1 FROM orgs WHERE org_id=?", (org_id,)).fetchone()
    if not org:
        click.echo(f"Error [ORG_NOT_FOUND]: Org '{org_id}' not found in sable.db", err=True)
        sys.exit(1)

    job_id = create_job(conn, org_id, "tracking_sync")
    step_id = add_step(conn, job_id, "sync", 1)
    start_step(conn, step_id)

    try:
        counts = asyncio.run(sync_to_platform(org_id))
        complete_step(conn, step_id, output=counts)
        conn.execute(
            "UPDATE jobs SET status='completed', completed_at=datetime('now'), result_json=? WHERE job_id=?",
            (json.dumps(counts), job_id)
        )
        conn.commit()
        click.echo(
            f"Synced: "
            f"{counts.get('entities_created', 0)} entities created, "
            f"{counts.get('content_items_created', 0)} items, "
            f"{counts.get('handles_added', 0)} handles added"
        )
    except SableError as e:
        from sable.platform.errors import redact_error
        _err = redact_error(str(e))
        fail_step(conn, step_id, _err)
        conn.execute(
            "UPDATE jobs SET status='failed', completed_at=datetime('now'), error_message=? WHERE job_id=?",
            (_err, job_id)
        )
        conn.commit()
        click.echo(f"Error [{e.code}]: {redact_error(e.message)}", err=True)
        sys.exit(1)
    except Exception as e:
        from sable.platform.errors import redact_error
        _err = redact_error(str(e))
        fail_step(conn, step_id, _err)
        conn.execute(
            "UPDATE jobs SET status='failed', completed_at=datetime('now'), error_message=? WHERE job_id=?",
            (_err, job_id)
        )
        conn.commit()
        click.echo(f"Error: {redact_error(str(e))}", err=True)
        sys.exit(1)
