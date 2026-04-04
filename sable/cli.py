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
    """Print current config (secrets masked)."""
    from sable import config as cfg
    data = cfg.load_config()
    for k, v in data.items():
        if k in _SECRET_CONFIG_KEYS:
            v = "(set)" if v else "(not set)"
        elif isinstance(v, dict):
            # Nested dicts (pulse_meta, platform): summarize instead of dumping raw
            console.print(f"  [cyan]{k}[/cyan]: ({len(v)} keys)")
            continue
        console.print(f"  [cyan]{k}[/cyan]: {v}")


from sable.config import SECRET_ENV_MAP

_SECRET_CONFIG_KEYS = set(SECRET_ENV_MAP.keys())


@config_group.command("set")
@click.argument("key")
@click.argument("value")
def config_set(key, value):
    """Set a config value."""
    import sys
    from sable import config as cfg
    if key in _SECRET_CONFIG_KEYS:
        env_name = SECRET_ENV_MAP.get(key, key.upper())
        console.print(f"[red]Error: {key} is a secret — set it via environment variable:[/red]")
        console.print(f"  export {env_name}=<value>")
        sys.exit(1)
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
from sable.wojak.cli import wojak_group
from sable.character_explainer.cli import explainer_group
from sable.vault.cli import vault_group
from sable.platform.cli import org_group, entity_group, job_group, db_group, resume_command
from sable.commands.playbook import playbook_group
from sable.commands.tracking import tracking_group
from sable.commands.advise import advise_command
from sable.commands.onboard import onboard_command
from sable.commands.write import write_command
from sable.commands.score import score_command
from sable.commands.diagnose import diagnose_command
from sable.commands.calendar import calendar_command
from sable.lexicon.cli import lexicon_group
from sable.narrative.cli import narrative_group
from sable.style.cli import style_delta_command
from sable.cadence.cli import silence_gradient_command
from sable.churn.cli import churn_group

main.add_command(roster_group)
main.add_command(clip_group)
main.add_command(meme_group)
main.add_command(face_group)
main.add_command(pulse_group)
main.add_command(wojak_group)
main.add_command(explainer_group)
main.add_command(vault_group)
main.add_command(org_group)
main.add_command(entity_group)
main.add_command(job_group)
main.add_command(db_group)
main.add_command(resume_command)
main.add_command(playbook_group)
main.add_command(tracking_group)
main.add_command(advise_command)
main.add_command(onboard_command)
main.add_command(write_command)
main.add_command(score_command)
main.add_command(diagnose_command)
main.add_command(calendar_command)
main.add_command(lexicon_group)
main.add_command(narrative_group)
main.add_command(style_delta_command)
main.add_command(silence_gradient_command)
main.add_command(churn_group)


@main.command("serve")
@click.option("--host", default="127.0.0.1", show_default=True, help="Bind address.")
@click.option("--port", default=8420, type=int, show_default=True, help="Bind port.")
@click.option("--reload", is_flag=True, default=False, help="Auto-reload on file changes (dev only).")
def serve_command(host: str, port: int, reload: bool):
    """Start the Sable API server (Phase 2)."""
    try:
        import uvicorn
    except ImportError:
        console.print("[red]uvicorn not installed. Run: pip install -e '.[serve]'[/red]")
        import sys
        sys.exit(1)
    uvicorn.run("sable.serve.app:create_app", host=host, port=port, reload=reload, factory=True)
