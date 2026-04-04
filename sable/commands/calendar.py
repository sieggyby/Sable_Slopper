"""CLI for `sable calendar` command."""
from __future__ import annotations

import sys
from datetime import datetime, timezone

import click
from rich.console import Console

from sable.shared.handles import strip_handle

console = Console()


@click.command("calendar")
@click.argument("handle")
@click.option("--days", default=7, show_default=True, help="Planning horizon in days.")
@click.option(
    "--formats-target", default=4, show_default=True,
    help="Unique format types to target.",
)
@click.option("--org", default=None, help="Org slug (defaults to roster account org).")
@click.option(
    "--save", "save_plan", is_flag=True, default=False,
    help="Save calendar to ~/.sable/playbooks/.",
)
@click.option(
    "--churn-input", "churn_input_path", type=click.Path(exists=True), default=None,
    help="Path to at-risk members JSON for re-engagement slot injection.",
)
@click.option(
    "--prioritize-churn", is_flag=True, default=False,
    help="Remove 30%% cap on churn-annotated slots.",
)
def calendar_command(
    handle: str, days: int, formats_target: int, org: str | None, save_plan: bool,
    churn_input_path: str | None, prioritize_churn: bool,
) -> None:
    """Generate a posting calendar for an account."""
    from sable.calendar.planner import build_calendar, render_calendar
    from sable.roster.manager import require_account
    from sable.shared.paths import pulse_db_path, meta_db_path, vault_dir, sable_home

    try:
        account = require_account(handle)
    except ValueError as e:
        from sable.platform.errors import redact_error
        console.print(f"[red]{redact_error(str(e))}[/red]")
        sys.exit(1)

    resolved_org = org or account.org
    if not resolved_org:
        console.print(
            "[yellow]No org resolved — vault and meta sections will be skipped.[/yellow]"
        )

    churn_playbook = None
    if churn_input_path:
        import json as _json
        try:
            with open(churn_input_path, encoding="utf-8") as _f:
                churn_playbook = _json.load(_f)
            if not isinstance(churn_playbook, list):
                console.print("[red]Churn input must be a JSON array[/red]")
                sys.exit(1)
        except (ValueError, OSError) as e:
            console.print(f"[red]Error reading churn input: {e}[/red]")
            sys.exit(1)

    from sable.platform.errors import SableError, redact_error as _redact

    try:
        plan = build_calendar(
            handle=account.handle,
            org=resolved_org or "",
            days=days,
            formats_target=formats_target,
            pulse_db_path=pulse_db_path(),
            meta_db_path=meta_db_path() if resolved_org else None,
            vault_root=vault_dir(resolved_org) if resolved_org else None,
            churn_playbook=churn_playbook,
            prioritize_churn=prioritize_churn,
        )
    except SableError as e:
        console.print(f"[red]Error [{e.code}]: {_redact(e.message)}[/red]")
        sys.exit(1)

    output = render_calendar(plan)
    console.print(output)

    if save_plan:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        playbooks_dir = sable_home() / "playbooks"
        playbooks_dir.mkdir(parents=True, exist_ok=True)
        filename = f"calendar_{strip_handle(account.handle)}_{today}.md"
        save_path = playbooks_dir / filename
        save_path.write_text(output, encoding="utf-8")
        console.print(f"[green]Saved → {save_path}[/green]")
