"""CLI for sable advise command."""
from __future__ import annotations

import sys
import click


@click.command("advise")
@click.argument("handle")
@click.option("--org", default=None, help="Org ID (defaults to roster account org)")
@click.option("--cheap", is_flag=True, help="Use cheaper/faster model")
@click.option("--force", is_flag=True, help="Force regeneration even if cached")
@click.option("--dry-run", is_flag=True, help="Estimate cost without generating")
@click.option("--export", is_flag=True, help="Export brief to ./output/advise_<org>_<date>.md")
@click.option("--bridge-aware", is_flag=True, default=False,
              help="Inject bridge node activity into the brief")
@click.option("--community-voice", is_flag=True, default=False,
              help="Inject CultGrader community language data into the brief")
@click.option("--churn-input", "churn_input_path", type=click.Path(exists=True), default=None,
              help="Path to at-risk members JSON to fold into the brief")
def advise_command(handle, org, cheap, force, dry_run, export, bridge_aware, community_voice, churn_input_path):
    """Generate Twitter strategy brief for a managed account."""
    from sable.platform.errors import SableError
    from sable.advise.generate import generate_advise
    from rich.console import Console

    console = Console()
    err_console = Console(stderr=True)

    churn_data = None
    if churn_input_path:
        import json as _json
        try:
            with open(churn_input_path, encoding="utf-8") as _f:
                churn_data = _json.load(_f)
        except (ValueError, OSError) as e:
            err_console.print(f"[red]Error reading churn input: {e}[/red]")
            sys.exit(1)

    try:
        path = generate_advise(
            handle, force=force, cheap=cheap, dry_run=dry_run, export=export,
            bridge_aware=bridge_aware, community_voice=community_voice,
            churn_data=churn_data, org=org,
        )
        if not dry_run and path:
            console.print(f"[green]✓ Strategy brief:[/green] {path}")
    except SableError as e:
        err_console.print(f"[red]Error [{e.code}]: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        from sable.platform.errors import redact_error
        err_console.print(f"[red]Error: {redact_error(str(e))}[/red]")
        sys.exit(1)
