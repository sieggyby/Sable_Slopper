"""CLI for sable onboard command."""
from __future__ import annotations

import sys
import click
from rich.console import Console

console = Console()


@click.command("onboard")
@click.argument("prospect_yaml")
@click.option("--org", "org_id", default=None, help="Override org_id (default: from YAML or filename)")
@click.option("--yes", is_flag=True, help="Accept all defaults without prompting")
@click.option("--non-interactive", is_flag=True, help="Fail if disambiguation needed")
def onboard_command(prospect_yaml, org_id, yes, non_interactive):
    """Onboard a new client org through 6-step pipeline."""
    from sable.platform.errors import SableError
    from sable.onboard.orchestrator import run_onboard

    try:
        job_id = run_onboard(prospect_yaml, org_id=org_id, yes=yes, non_interactive=non_interactive)
        console.print(f"[green]✓ Onboarding complete.[/green] Job: {job_id}")
        console.print(f"  Run [cyan]sable job show {job_id}[/cyan] to see all steps.")
    except SableError as e:
        console.print(f"[red]Error [{e.code}]: {e.message}[/red]", err=True)
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]", err=True)
        sys.exit(1)
