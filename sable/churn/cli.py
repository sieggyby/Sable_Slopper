"""CLI for sable churn commands."""
from __future__ import annotations

import json
import sys

import click


@click.group("churn")
def churn_group():
    """Churn detection and intervention tools."""


@churn_group.command("intervene")
@click.option("--org", required=True, help="Org ID")
@click.option("--input", "input_path", required=True, type=click.Path(exists=True),
              help="Path to at-risk members JSON file")
@click.option("--output", "output_path", type=click.Path(), default=None,
              help="Write playbook JSON to file")
@click.option("--force", is_flag=True, help="Allow >50 members")
@click.option("--dry-run", is_flag=True, help="Estimate cost without generating")
def intervene_command(org, input_path, output_path, force, dry_run):
    """Generate re-engagement playbooks for at-risk community members."""
    from rich.console import Console

    from sable.churn.interventions import generate_playbook, SOFT_CAP
    from sable.platform.db import get_db
    from sable.platform.errors import SableError

    console = Console()
    err_console = Console(stderr=True)

    try:
        with open(input_path, encoding="utf-8") as f:
            at_risk = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        err_console.print(f"[red]Error reading input: {e}[/red]")
        sys.exit(1)

    if not isinstance(at_risk, list):
        err_console.print("[red]Input must be a JSON array of at-risk members[/red]")
        sys.exit(1)

    if dry_run:
        console.print(f"At-risk members: {len(at_risk)}")
        console.print(f"Estimated Claude calls: {len(at_risk)}")
        est_cost = len(at_risk) * 0.005
        console.print(f"Estimated cost: ~${est_cost:.2f}")
        if len(at_risk) > SOFT_CAP:
            console.print(f"[yellow]Warning: exceeds soft cap of {SOFT_CAP}. Use --force to proceed.[/yellow]")
        return

    conn = get_db()

    try:
        results = generate_playbook(
            org, at_risk, conn, force=force, dry_run=False,
        )
    except SableError as e:
        err_console.print(f"[red]Error [{e.code}]: {e.message}[/red]")
        sys.exit(1)

    if output_path:
        out = [
            {
                "handle": r.handle,
                "interest_tags": r.interest_tags,
                "role_recommendation": r.role_recommendation,
                "spotlight_suggestion": r.spotlight_suggestion,
                "engagement_prompts": r.engagement_prompts,
                "urgency": r.urgency,
                "error": r.error,
            }
            for r in results
        ]
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2)
        console.print(f"[green]Playbook written to {output_path}[/green]")
    else:
        for r in results:
            if r.error:
                console.print(f"[red]{r.handle}: error - {r.error}[/red]")
            else:
                console.print(f"[green]{r.handle}[/green] ({r.urgency})")
                console.print(f"  Tags: {', '.join(r.interest_tags)}")
                console.print(f"  Role: {r.role_recommendation}")
                console.print(f"  Spotlight: {r.spotlight_suggestion}")
                for ep in r.engagement_prompts:
                    console.print(f"  - {ep}")

    console.print(f"\n[green]Generated {len(results)} playbooks[/green]")
