"""sable — top-level CLI entry point."""
from __future__ import annotations

import click
from rich.console import Console

console = Console()


@click.group()
@click.version_option(package_name="sable")
def main():
    """Sable content production toolkit for crypto Twitter."""


# ---------------------------------------------------------------------------
# Config subcommand
# ---------------------------------------------------------------------------

@main.group("config")
def config_group():
    """Manage sable configuration."""


@config_group.command("show")
def config_show():
    """Print current config (keys masked)."""
    from sable import config as cfg
    data = cfg.load_config()
    for k, v in data.items():
        if "key" in k.lower() or "token" in k.lower():
            v = v[:6] + "…" if v else "(not set)"
        console.print(f"  [cyan]{k}[/cyan]: {v}")


@config_group.command("set")
@click.argument("key")
@click.argument("value")
def config_set(key, value):
    """Set a config value."""
    from sable import config as cfg
    cfg.set_key(key, value)
    console.print(f"[green]✓ Set {key}[/green]")


# ---------------------------------------------------------------------------
# Register subcommands
# ---------------------------------------------------------------------------

from sable.roster.cli import roster_group
from sable.clip.cli import clip_group
from sable.meme.cli import meme_group
from sable.face.cli import face_group
from sable.pulse.cli import pulse_group

main.add_command(roster_group)
main.add_command(clip_group)
main.add_command(meme_group)
main.add_command(face_group)
main.add_command(pulse_group)
