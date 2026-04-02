"""CLI for sable playbook commands (delegates to Cult Doctor)."""
from __future__ import annotations

import sys
import click


@click.group("playbook")
def playbook_group():
    """Generate playbooks for client orgs."""


@playbook_group.command("discord")
@click.argument("org_id")
@click.option("--force", is_flag=True, help="Force regeneration even if cached")
@click.option("--cheap", is_flag=True, help="Use cheaper/faster model")
@click.option("--dry-run", is_flag=True, help="Estimate cost without generating")
def playbook_discord(org_id, force, cheap, dry_run):
    """Generate Discord engagement playbook for org. Delegates to Cult Doctor."""
    try:
        from sable_cult_grader.playbook.generate import generate_discord_playbook
    except ImportError:
        click.echo(
            "Required package not found: sable_cult_grader. "
            "Ensure it is installed or on PYTHONPATH.",
            err=True,
        )
        sys.exit(1)

    from sable.platform.errors import SableError
    try:
        result = generate_discord_playbook(org_id, force=force, cheap=cheap, dry_run=dry_run)
        if dry_run:
            click.echo("Dry run complete. No artifact generated.")
        elif isinstance(result, str) and result:
            click.echo(f"Playbook generated: {result}")
        else:
            click.echo("Playbook generated.")
    except SableError as e:
        click.echo(f"Error [{e.code}]: {e.message}", err=True)
        sys.exit(1)
    except Exception as e:
        from sable.platform.errors import redact_error
        click.echo(f"Error: {redact_error(str(e))}", err=True)
        sys.exit(1)
