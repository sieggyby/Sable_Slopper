"""CLI for sable weekly — automated weekly cycle."""
from __future__ import annotations

import sys

import click
from rich.console import Console

console = Console()


@click.group("weekly")
def weekly_group():
    """Automated weekly cycle for managed accounts."""


@weekly_group.command("run")
@click.option("--org", default=None, help="Org to run the weekly cycle for.")
@click.option("--all", "all_orgs", is_flag=True, default=False,
              help="Run for all orgs with rostered accounts.")
@click.option("--dry-run", is_flag=True, default=False,
              help="Print execution plan without running anything.")
@click.option("--cost-estimate", is_flag=True, default=False,
              help="Estimate total cost without running.")
def weekly_run(
    org: str | None,
    all_orgs: bool,
    dry_run: bool,
    cost_estimate: bool,
) -> None:
    """Run the full weekly cycle for an org or all orgs."""
    if org and all_orgs:
        console.print("[red]--org and --all are mutually exclusive[/red]")
        sys.exit(1)
    if not org and not all_orgs:
        console.print("[red]Provide --org ORG or --all[/red]")
        sys.exit(1)

    from sable.weekly.runner import (
        WeeklyRunner,
        format_summary,
        discover_orgs,
        estimate_org_cost,
    )

    orgs = [org] if org else discover_orgs()

    if not orgs:
        console.print("[yellow]No orgs with active rostered accounts found.[/yellow]")
        return

    if dry_run:
        from sable.roster.manager import list_accounts as _list_accs
        console.print("[bold]Dry run — execution plan:[/bold]")
        for o in orgs:
            accounts = _list_accs(org=o, active_only=True)
            handles = ", ".join(a.handle for a in accounts)
            console.print(f"\n  Org: {o}")
            console.print(f"  Accounts: {handles or '(none)'}")
            console.print(f"  Steps: {', '.join(WeeklyRunner.STEPS)}")
        return

    if cost_estimate:
        total = 0.0
        console.print("[bold]Cost estimate:[/bold]")
        for o in orgs:
            est = estimate_org_cost(o)
            total += est
            console.print(f"  {o}: ~${est:.2f}")
        console.print(f"\n  [bold]Total: ~${total:.2f}[/bold]")
        return

    # Execute
    any_failure = False
    for o in orgs:
        runner = WeeklyRunner(o)
        console.print(f"\n[bold]Starting weekly cycle for {o}...[/bold]")

        results = runner.run()
        summary = format_summary(o, results)
        console.print(summary)

        if any(r.status == "error" for r in results):
            any_failure = True

    if any_failure:
        sys.exit(1)


# ---------------------------------------------------------------------------
# Cron subgroup
# ---------------------------------------------------------------------------

@weekly_group.group("cron")
def cron_group():
    """Manage scheduled weekly automation."""


@cron_group.command("install")
def cron_install() -> None:
    """Generate a macOS launchd plist for sable weekly --all."""
    from sable.weekly.cron import install_plist, PLIST_LABEL

    plist_path = install_plist()
    console.print(f"[green]Plist written to {plist_path}[/green]")
    console.print(f"\nTo activate:\n  launchctl load {plist_path}")
    console.print(f"\nTo deactivate:\n  launchctl unload {plist_path}")
