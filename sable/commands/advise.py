"""CLI for sable advise command."""
from __future__ import annotations

import sys
import click


@click.command("advise")
@click.argument("handle")
@click.option("--cheap", is_flag=True, help="Use cheaper/faster model")
@click.option("--force", is_flag=True, help="Force regeneration even if cached")
@click.option("--dry-run", is_flag=True, help="Estimate cost without generating")
@click.option("--export", is_flag=True, help="Export brief to ./output/advise_<org>_<date>.md")
def advise_command(handle, cheap, force, dry_run, export):
    """Generate Twitter strategy brief for a managed account."""
    from sable.platform.errors import SableError
    from sable.advise.generate import generate_advise
    from rich.console import Console

    console = Console()
    err_console = Console(stderr=True)

    try:
        path = generate_advise(handle, force=force, cheap=cheap, dry_run=dry_run, export=export)
        if not dry_run and path:
            console.print(f"[green]✓ Strategy brief:[/green] {path}")
    except SableError as e:
        err_console.print(f"[red]Error [{e.code}]: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        from sable.platform.errors import redact_error
        err_console.print(f"[red]Error: {redact_error(str(e))}[/red]")
        sys.exit(1)
