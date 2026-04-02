"""sable wojak — CLI group for wojak library and scene compositor."""
from __future__ import annotations

import time
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from sable.shared.handles import strip_handle

console = Console()


@click.group("wojak")
def wojak_group():
    """Wojak asset library and scene compositor."""


# ---------------------------------------------------------------------------
# sable wojak list
# ---------------------------------------------------------------------------

@wojak_group.command("list")
def wojak_list():
    """List all wojaks in the library."""
    from sable.wojak.library import load_library, get_wojak_image

    library = load_library()

    table = Table(title=f"Wojak Library ({len(library)} characters)")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Name")
    table.add_column("Emotion", style="yellow")
    table.add_column("Tags")
    table.add_column("Image", style="green")

    for w in library:
        img = get_wojak_image(w)
        img_status = "✓" if img else "✗ missing"
        table.add_row(
            w["id"],
            w["name"],
            w["emotion"],
            ", ".join(w.get("tags", [])[:4]),
            img_status,
        )

    console.print(table)


# ---------------------------------------------------------------------------
# sable wojak add
# ---------------------------------------------------------------------------

@wojak_group.command("add")
@click.argument("url")
@click.option("--id", "wojak_id", required=True, help="Unique ID (e.g. crying-wojak)")
@click.option("--name", required=True, help="Display name")
@click.option("--emotion", required=True, help="Primary emotion (sad, chad, smug, etc.)")
@click.option("--tags", required=True, help="Comma-separated tags")
@click.option("--description", required=True, help="When to use this wojak")
def wojak_add(url, wojak_id, name, emotion, tags, description):
    """Download a transparent PNG and register it in the wojak library."""
    from sable.wojak.library import add_wojak

    tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    with console.status(f"Downloading {url}..."):
        try:
            entry = add_wojak(url, wojak_id, name, emotion, tag_list, description)
            console.print(f"[green]✓ Added {entry['id']} ({entry['image_file']})[/green]")
            if not entry.get("transparent"):
                console.print("[yellow]⚠ Image may not be transparent — check before compositing[/yellow]")
        except Exception as e:
            from sable.platform.errors import redact_error
            console.print(f"[red]✗ Error: {redact_error(str(e))}[/red]")
            raise SystemExit(1)


# ---------------------------------------------------------------------------
# sable wojak download-missing
# ---------------------------------------------------------------------------

@wojak_group.command("download-missing")
def wojak_download_missing():
    """Attempt to download all library entries that are missing images."""
    from sable.wojak.library import download_missing

    console.print("Downloading missing wojak images...")
    results = download_missing(verbose=True)
    ok = sum(1 for v in results.values() if v)
    fail = sum(1 for v in results.values() if not v)
    console.print(f"\n[green]{ok} downloaded / available[/green], [red]{fail} failed / missing[/red]")


# ---------------------------------------------------------------------------
# sable wojak scene
# ---------------------------------------------------------------------------

@wojak_group.group("scene")
def scene_group():
    """Compose and render wojak scenes."""


wojak_group.add_command(scene_group)


@scene_group.command("generate")
@click.option("--account", "-a", required=True, help="Account handle (e.g. @Dr_JohnFletcher)")
@click.option("--topic", "-t", default=None, help="Topic or angle for the scene")
@click.option("--dry-run", is_flag=True, help="Print scene spec without rendering")
def scene_generate(account, topic, dry_run):
    """Ask Claude to design and render a wojak scene for an account."""
    from sable.roster.manager import RosterManager
    from sable.wojak.generator import generate_scene
    from sable.wojak.compositor import render_scene, scene_output_path
    import yaml

    mgr = RosterManager()
    acct = mgr.get(account)
    if not acct:
        console.print(f"[red]Account '{account}' not found in roster.[/red]")
        raise SystemExit(1)

    with console.status("Generating scene with Claude..."):
        try:
            spec = generate_scene(acct, topic=topic, dry_run=dry_run)
        except Exception as e:
            from sable.platform.errors import redact_error
            console.print(f"[red]Generation failed: {redact_error(str(e))}[/red]")
            raise SystemExit(1)

    console.print("\n[bold]Scene spec:[/bold]")
    console.print(yaml.dump(spec, default_flow_style=False, allow_unicode=True))

    if dry_run:
        console.print("[yellow]--dry-run: skipping render[/yellow]")
        return

    handle = strip_handle(account)
    timestamp = int(time.time())
    out_path = scene_output_path(handle, f"wojak_scene_{timestamp}.png")

    with console.status("Rendering scene..."):
        try:
            result = render_scene(
                layers=spec["layers"],
                caption=spec.get("caption", ""),
                output_path=out_path,
            )
            console.print(f"\n[green]✓ Scene saved → {result}[/green]")
        except Exception as e:
            from sable.platform.errors import redact_error
            console.print(f"[red]Render failed: {redact_error(str(e))}[/red]")
            raise SystemExit(1)


@scene_group.command("render")
@click.argument("spec_file", type=click.Path(exists=True))
@click.option("--account", "-a", required=True, help="Account handle (for output path)")
@click.option("--output", "-o", default=None, help="Custom output path (optional)")
def scene_render(spec_file, account, output):
    """Render a pre-written scene YAML spec file."""
    import yaml
    from sable.wojak.compositor import render_scene, scene_output_path

    with open(spec_file) as f:
        spec = yaml.safe_load(f)

    if not spec or "layers" not in spec:
        console.print("[red]Invalid spec file: must contain 'layers' key.[/red]")
        raise SystemExit(1)

    handle = strip_handle(account)
    if output:
        out_path = Path(output)
    else:
        timestamp = int(time.time())
        out_path = scene_output_path(handle, f"wojak_scene_{timestamp}.png")

    with console.status("Rendering scene..."):
        try:
            result = render_scene(
                layers=spec["layers"],
                caption=spec.get("caption", ""),
                output_path=out_path,
            )
            console.print(f"[green]✓ Scene saved → {result}[/green]")
        except Exception as e:
            from sable.platform.errors import redact_error
            console.print(f"[red]Render failed: {redact_error(str(e))}[/red]")
            raise SystemExit(1)
