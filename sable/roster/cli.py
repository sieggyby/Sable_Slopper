"""sable roster — account management CLI."""
from __future__ import annotations

import os
import subprocess
import sys
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich import box

from sable.roster import manager, models, profiles as prof_mod

console = Console()


@click.group("roster")
def roster_group():
    """Manage accounts in the sable roster."""


# ---------------------------------------------------------------------------
# sable roster list
# ---------------------------------------------------------------------------

@roster_group.command("list")
@click.option("--org", default=None, help="Filter by org")
@click.option("--active-only", is_flag=True)
def roster_list(org, active_only):
    """List all accounts in the roster."""
    accounts = manager.list_accounts(org=org, active_only=active_only)
    if not accounts:
        console.print("[yellow]No accounts found.[/yellow]")
        return

    table = Table(box=box.SIMPLE_HEAVY, show_header=True)
    table.add_column("Handle", style="cyan bold")
    table.add_column("Display Name")
    table.add_column("Org")
    table.add_column("Archetype")
    table.add_column("Active")
    table.add_column("Profiles")

    for acc in accounts:
        has_profiles = "✓" if prof_mod.profiles_exist(acc.handle) else "—"
        table.add_row(
            acc.handle,
            acc.display_name or "—",
            acc.org or "—",
            acc.persona.archetype or "—",
            "✓" if acc.active else "✗",
            has_profiles,
        )
    console.print(table)


# ---------------------------------------------------------------------------
# sable roster add
# ---------------------------------------------------------------------------

@roster_group.command("add")
@click.argument("handle")
@click.option("--display-name", "-n", default="")
@click.option("--org", "-o", default="")
@click.option("--archetype", default="")
@click.option("--voice", default="")
@click.option("--topics", default="", help="Comma-separated topics")
@click.option("--init-profile", is_flag=True, default=True, help="Scaffold profile files")
def roster_add(handle, display_name, org, archetype, voice, topics, init_profile):
    """Add a new account to the roster."""
    topic_list = [t.strip() for t in topics.split(",") if t.strip()] if topics else []
    account = models.Account(
        handle=handle,
        display_name=display_name,
        org=org,
        persona=models.Persona(archetype=archetype, voice=voice, topics=topic_list),
    )
    try:
        manager.add_account(account)
        console.print(f"[green]✓ Added {account.handle}[/green]")
        if init_profile:
            d = prof_mod.scaffold_profile(account.handle)
            console.print(f"[dim]  Profile files created at {d}[/dim]")
    except ValueError as e:
        from sable.platform.errors import redact_error
        console.print(f"[red]Error: {redact_error(str(e))}[/red]")
        sys.exit(1)


# ---------------------------------------------------------------------------
# sable roster show
# ---------------------------------------------------------------------------

@roster_group.command("show")
@click.argument("handle")
@click.option("--profile-preview", is_flag=True, default=True, help="Show first 5 lines of each profile file")
def roster_show(handle, profile_preview):
    """Show full details for an account."""
    try:
        account = manager.require_account(handle)
    except ValueError as e:
        from sable.platform.errors import redact_error
        console.print(f"[red]{redact_error(str(e))}[/red]")
        sys.exit(1)

    console.rule(f"[bold cyan]{account.handle}[/bold cyan]")
    console.print(f"  Display name : {account.display_name or '—'}")
    console.print(f"  Org          : {account.org or '—'}")
    console.print(f"  Active       : {'yes' if account.active else 'no'}")
    console.print(f"  Archetype    : {account.persona.archetype or '—'}")
    console.print(f"  Voice        : {account.persona.voice or '—'}")
    console.print(f"  Topics       : {', '.join(account.persona.topics) or '—'}")
    console.print(f"  Avoid        : {', '.join(account.persona.avoid) or '—'}")
    console.print(f"  Meme style   : {account.content.meme_style}")
    console.print(f"  Clip style   : {account.content.clip_style}")
    console.print(f"  Brainrot     : {account.content.brainrot_energy}")
    console.print(f"  Tweet bank   : {len(account.tweet_bank)} tweets")

    if account.learned_preferences:
        console.print("\n  [bold]Learned Preferences:[/bold]")
        for k, v in account.learned_preferences.items():
            console.print(f"    {k}: {v}")

    if profile_preview and prof_mod.profiles_exist(account.handle):
        console.rule("[dim]Profile Previews[/dim]")
        previews = prof_mod.profile_preview(account.handle, lines=5)
        for fname, preview in previews.items():
            console.print(f"\n[bold]{fname}.md[/bold]")
            console.print(f"[dim]{preview}[/dim]")


# ---------------------------------------------------------------------------
# sable roster remove
# ---------------------------------------------------------------------------

@roster_group.command("remove")
@click.argument("handle")
@click.confirmation_option(prompt="Are you sure you want to remove this account?")
def roster_remove(handle):
    """Remove an account from the roster."""
    removed = manager.remove_account(handle)
    if removed:
        console.print(f"[green]✓ Removed {handle}[/green]")
    else:
        console.print(f"[red]Account {handle} not found.[/red]")
        sys.exit(1)


# ---------------------------------------------------------------------------
# sable roster update
# ---------------------------------------------------------------------------

@roster_group.command("update")
@click.argument("handle")
@click.option("--display-name", default=None)
@click.option("--org", default=None)
@click.option("--archetype", default=None)
@click.option("--voice", default=None)
@click.option("--active/--inactive", default=None)
def roster_update(handle, display_name, org, archetype, voice, active):
    """Update account fields."""
    try:
        account = manager.require_account(handle)
    except ValueError as e:
        from sable.platform.errors import redact_error
        console.print(f"[red]{redact_error(str(e))}[/red]")
        sys.exit(1)

    if display_name is not None:
        account.display_name = display_name
    if org is not None:
        account.org = org
    if archetype is not None:
        account.persona.archetype = archetype
    if voice is not None:
        account.persona.voice = voice
    if active is not None:
        account.active = active

    from sable.roster.manager import save_roster, load_roster
    roster = load_roster()
    roster.upsert(account)
    save_roster(roster)
    console.print(f"[green]✓ Updated {account.handle}[/green]")


# ---------------------------------------------------------------------------
# sable roster profile
# ---------------------------------------------------------------------------

@roster_group.group("profile")
def profile_group():
    """Manage markdown profile files for an account."""


@profile_group.command("init")
@click.argument("handle")
@click.option("--force", is_flag=True, help="Overwrite existing files")
def profile_init(handle, force):
    """Scaffold blank profile files for an account."""
    handle = handle if handle.startswith("@") else f"@{handle}"
    if force:
        # Remove existing files first
        from sable.shared.paths import profile_dir
        d = profile_dir(handle)
        if d.exists():
            for f in prof_mod.PROFILE_FILES:
                fpath = d / f"{f}.md"
                if fpath.exists():
                    fpath.unlink()
    d = prof_mod.scaffold_profile(handle)
    console.print(f"[green]✓ Profile files created at {d}[/green]")
    for f in prof_mod.PROFILE_FILES:
        console.print(f"  {d / f}.md")


@profile_group.command("show")
@click.argument("handle")
@click.option("--file", "-f", default=None, type=click.Choice(prof_mod.PROFILE_FILES + ["all"]))
def profile_show(handle, file):
    """Print a profile file (or all files)."""
    handle = handle if handle.startswith("@") else f"@{handle}"
    files_to_show = prof_mod.PROFILE_FILES if file in (None, "all") else [file]
    for fname in files_to_show:
        content = prof_mod.read_profile_file(handle, fname)
        if content is None:
            console.print(f"[yellow]{fname}.md not found. Run: sable roster profile init {handle}[/yellow]")
        else:
            console.rule(f"[bold]{fname}.md[/bold]")
            console.print(content)


@profile_group.command("edit")
@click.argument("handle")
@click.option("--file", "-f", default="tone", type=click.Choice(prof_mod.PROFILE_FILES))
def profile_edit(handle, file):
    """Open a profile file in $EDITOR."""
    handle = handle if handle.startswith("@") else f"@{handle}"
    from sable.shared.paths import profile_dir as _pd
    d = _pd(handle)
    d.mkdir(parents=True, exist_ok=True)
    fpath = d / f"{file}.md"

    # Scaffold if missing
    if not fpath.exists():
        prof_mod.scaffold_profile(handle)

    editor = os.environ.get("EDITOR", "nano")
    subprocess.call([editor, str(fpath)])


@profile_group.command("list")
@click.argument("handle")
def profile_list(handle):
    """List profile files and their sizes."""
    handle = handle if handle.startswith("@") else f"@{handle}"
    from sable.shared.paths import profile_dir as _pd
    d = _pd(handle)
    if not d.exists():
        console.print(f"[yellow]No profile directory for {handle}. Run: sable roster profile init {handle}[/yellow]")
        return
    for fname in prof_mod.PROFILE_FILES:
        fpath = d / f"{fname}.md"
        if fpath.exists():
            size = fpath.stat().st_size
            console.print(f"  [cyan]{fname}.md[/cyan]  ({size} bytes)")
        else:
            console.print(f"  [dim]{fname}.md[/dim]  [red]missing[/red]")
