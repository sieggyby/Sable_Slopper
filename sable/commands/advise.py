"""CLI for sable advise command."""
from __future__ import annotations

import sys
import click


@click.command("advise")
@click.argument("handle")
@click.option("--cheap", is_flag=True, help="Use cheaper/faster model")
@click.option("--force", is_flag=True, help="Force regeneration even if cached")
@click.option("--dry-run", is_flag=True, help="Estimate cost without generating")
def advise_command(handle, cheap, force, dry_run):
    """Generate Twitter strategy brief for a managed account."""
    from sable.platform.errors import SableError
    from sable.advise.generate import generate_advise
    from rich.console import Console

    console = Console()

    try:
        path = generate_advise(handle, force=force, cheap=cheap, dry_run=dry_run)
        if not dry_run and path:
            console.print(f"[green]✓ Strategy brief:[/green] {path}")
    except SableError as e:
        console.print(f"[red]Error [{e.code}]: {e.message}[/red]", err=True)
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]", err=True)
        sys.exit(1)
