"""CLI for `sable diagnose` command."""
from __future__ import annotations

import sys

import click
from rich.console import Console

console = Console()


@click.command("diagnose")
@click.argument("handle")
@click.option("--org", default=None, help="Org slug (defaults to roster account org).")
@click.option("--days", default=30, show_default=True, help="Look-back window in days.")
@click.option(
    "--save", "save_artifact", is_flag=True, default=False,
    help="Save diagnosis to sable.db as an artifact.",
)
def diagnose_command(handle: str, org: str | None, days: int, save_artifact: bool) -> None:
    """Full account audit: format health, topic gaps, vault waste, cadence, engagement."""
    from sable.diagnose.runner import run_diagnosis, render_diagnosis, save_diagnosis_artifact
    from sable.roster.manager import require_account
    from sable.shared.paths import pulse_db_path, meta_db_path, vault_dir, sable_db_path

    try:
        account = require_account(handle)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)

    resolved_org = org or account.org
    if not resolved_org:
        console.print(
            "[yellow]No org resolved — vault and meta sections will be skipped.[/yellow]"
        )

    report = run_diagnosis(
        handle=account.handle,
        org=resolved_org or "",
        days=days,
        pulse_db_path=pulse_db_path(),
        meta_db_path=meta_db_path() if resolved_org else None,
        vault_root=vault_dir(resolved_org) if resolved_org else None,
        sable_db_path=sable_db_path(),
    )

    if save_artifact and resolved_org:
        artifact_id = save_diagnosis_artifact(report, resolved_org)
        if artifact_id:
            report.artifact_id = artifact_id

    console.print(render_diagnosis(report))
