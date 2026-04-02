"""CLI for sable onboard command."""
from __future__ import annotations

import sys
import click
from rich.console import Console

console = Console()
err_console = Console(stderr=True)

_PREP_TEMPLATES = {
    "tone": "# Tone\n\n<!-- Describe this account's voice. Examples:\n- Confident and direct. Never hedges.\n- Uses crypto-native slang but stays readable.\n- Technical when explaining mechanisms; plain English for takes.\n-->",
    "interests": "# Interests\n\n<!-- List the topics this account posts about. Examples:\n- DeFi yields and risk management\n- L2 scaling narratives\n- On-chain data interpretation\n-->",
    "context": "# Account Context\n\n<!-- Background on who this account represents. Examples:\n- Founder at XYZ protocol. Background in TradFi before going on-chain.\n- Anonymous. Known for contrarian macro takes.\n-->",
    "notes": "# Operator Notes\n\n<!-- Running notes for Sable operators. Examples:\n- Avoid mentioning competitors by name.\n- Client prefers threads over standalone text for complex topics.\n-->",
}


def _run_prep(handle: str | None, org_slug: str | None) -> None:
    if not handle or not org_slug:
        click.echo("Error: --handle and --org-slug are required with --prep", err=True)
        sys.exit(1)

    from sable.shared.paths import profile_dir
    from sable.pulse.db import migrate as pulse_migrate
    from sable.platform.db import get_db

    d = profile_dir(handle)   # normalizes @ prefix
    already_exists = d.exists()

    if already_exists:
        err_console.print(f"[yellow]Profile already exists, skipping: {d}[/yellow]")
    else:
        d.mkdir(parents=True, exist_ok=True)
        for name, content in _PREP_TEMPLATES.items():
            fpath = d / f"{name}.md"
            if not fpath.exists():
                fpath.write_text(content + "\n", encoding="utf-8")
        console.print(f"[green]✓ Profile created:[/green] {d}")

    # Ensure pulse.db schema exists
    pulse_migrate()

    # Register org in sable.db (idempotent)
    conn = get_db()
    conn.execute(
        "INSERT OR IGNORE INTO orgs (org_id, display_name) VALUES (?, ?)",
        (org_slug, org_slug),
    )
    conn.commit()
    conn.close()
    console.print(f"[green]✓ Org registered:[/green] {org_slug}")


@click.command("onboard")
@click.argument("prospect_yaml", required=False, default=None)
@click.option("--org", "org_id", default=None, help="Override org_id (from YAML or filename)")
@click.option("--yes", is_flag=True, help="Accept all defaults without prompting")
@click.option("--non-interactive", is_flag=True, help="Fail if disambiguation needed")
@click.option("--prep", "prep_mode", is_flag=True, default=False,
              help="Create profile stubs for a new account")
@click.option("--handle", "prep_handle", default=None,
              help="Account handle for --prep mode (e.g. @psy_handle)")
@click.option("--org-slug", "prep_org", default=None,
              help="Org slug for --prep mode (e.g. psy)")
def onboard_command(prospect_yaml, org_id, yes, non_interactive, prep_mode, prep_handle, prep_org):
    """Onboard a new client org through 6-step pipeline."""
    if prep_mode:
        _run_prep(prep_handle, prep_org)
    else:
        if prospect_yaml is None:
            click.echo("Error: PROSPECT_YAML required when not using --prep", err=True)
            sys.exit(1)

        from sable.platform.errors import SableError
        from sable.onboard.orchestrator import run_onboard

        try:
            job_id = run_onboard(prospect_yaml, org_id=org_id, yes=yes, non_interactive=non_interactive)
            console.print(f"[green]✓ Onboarding complete.[/green] Job: {job_id}")
            console.print(f"  Run [cyan]sable job show {job_id}[/cyan] to see all steps.")
        except SableError as e:
            err_console.print(f"[red]Error [{e.code}]: {e.message}[/red]")
            sys.exit(1)
        except Exception as e:
            from sable.platform.errors import redact_error
            err_console.print(f"[red]Error: {redact_error(str(e))}[/red]")
            sys.exit(1)
