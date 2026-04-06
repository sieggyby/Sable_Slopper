"""sable meme — template-based meme generation CLI."""
from __future__ import annotations

import sys
from pathlib import Path

from sable.shared.files import atomic_write as _atomic_write

import click
from rich.console import Console
from rich.table import Table
from rich import box

console = Console()


@click.group("meme")
def meme_group():
    """Generate memes from templates with AI-written copy."""


@meme_group.command("list-templates")
def meme_list_templates():
    """List all available meme templates."""
    from sable.meme.templates import load_registry, get_template_image
    templates = load_registry()
    table = Table(box=box.SIMPLE_HEAVY, show_header=True)
    table.add_column("ID", style="cyan bold")
    table.add_column("Name")
    table.add_column("Zones")
    table.add_column("Style")
    table.add_column("Image")
    table.add_column("Hint")
    for t in templates:
        img = get_template_image(t)
        table.add_row(
            t["id"],
            t["name"],
            ", ".join(z["id"] for z in t.get("zones", [])),
            t.get("style", "?"),
            "✓" if img else "missing",
            t.get("prompt_hint", "")[:50],
        )
    console.print(table)


@meme_group.command("generate")
@click.option("--account", "-a", required=True)
@click.option("--template", "-t", default=None, help="Template ID (auto-suggest if omitted)")
@click.option("--topic", default=None, help="Topic or angle")
@click.option("--vibe", default=None, help="Vibe override")
@click.option("--output", "-o", default=None, help="Output path (default: auto)")
@click.option("--style", default=None, type=click.Choice(["classic", "modern", "minimal"]))
@click.option("--dry-run", is_flag=True)
@click.option("--save-to-bank", "save_bank", is_flag=True, help="Save caption to tweet bank")
def meme_generate(account, template, topic, vibe, output, style, dry_run, save_bank):
    """Generate a single meme for an account."""
    from sable.roster.manager import require_account
    from sable.meme.generator import generate_meme_text, suggest_template
    from sable.meme.renderer import render_meme
    from sable.meme.bank import save_to_bank
    from sable.shared.paths import account_output_dir
    import time

    try:
        acc = require_account(account)
    except ValueError as e:
        from sable.platform.errors import redact_error
        console.print(f"[red]{redact_error(str(e))}[/red]")
        sys.exit(1)

    resolved_org = acc.org or None

    if template is None:
        with console.status("Auto-selecting best template..."):
            template = suggest_template(acc, topic=topic, org_id=resolved_org)
        console.print(f"[dim]Selected template: {template}[/dim]")

    with console.status("Generating meme text with Claude..."):
        texts = generate_meme_text(template, acc, topic=topic, vibe=vibe, dry_run=dry_run,
                                   org_id=resolved_org)

    console.print("\n[bold]Generated text:[/bold]")
    for zone_id, text in texts.items():
        console.print(f"  [cyan]{zone_id}[/cyan]: {text}")

    if dry_run:
        console.print("[yellow](dry run — skipping render)[/yellow]")
        return

    if output is None:
        out_dir = account_output_dir(acc.handle) / "memes"
        out_dir.mkdir(parents=True, exist_ok=True)
        output = str(out_dir / f"{template}_{int(time.time())}.png")

    with console.status("Rendering meme..."):
        out_path = render_meme(template, texts, output, style=style)

    # Write sidecar metadata
    import json as _json
    from datetime import datetime, timezone
    _meta = {
        "id": f"meme-{Path(out_path).stem}",
        "type": "meme",
        "source_tool": "sable-meme",
        "account": acc.handle,
        "template": template,
        "topic": topic or "",
        "texts": texts,
        "output": str(out_path),
        "assembled_at": datetime.now(timezone.utc).isoformat(),
    }
    _atomic_write(Path(str(out_path) + "_meta.json"), _json.dumps(_meta, indent=2))

    console.print(f"\n[green]✓ Saved:[/green] {out_path}")

    # Register as platform artifact if org is resolvable
    resolved_org = acc.org or None
    if resolved_org:
        try:
            from sable.platform.artifacts import register_content_artifact
            register_content_artifact(
                org_id=resolved_org,
                artifact_type="content_meme",
                path=str(out_path),
                metadata={"handle": acc.handle, "template": template, "topic": topic or ""},
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("Artifact registration failed: %s", e)

    if save_bank:
        caption = texts.get("caption") or texts.get("bottom") or list(texts.values())[-1]
        save_to_bank(acc.handle, caption)
        console.print("[dim]Caption saved to tweet bank[/dim]")


@meme_group.command("batch")
@click.option("--account", "-a", required=True)
@click.option("--count", "-n", default=5, show_default=True)
@click.option("--topics", default="", help="Comma-separated topics")
@click.option("--render", "do_render", is_flag=True, help="Render all generated memes")
@click.option("--approve", is_flag=True, help="Interactive approval before saving")
def meme_batch(account, count, topics, do_render, approve):
    """Generate a batch of memes for an account."""
    from sable.roster.manager import require_account
    from sable.meme.generator import generate_batch
    from sable.meme.renderer import render_meme
    from sable.meme.bank import save_to_bank
    from sable.shared.paths import account_output_dir
    import time

    try:
        acc = require_account(account)
    except ValueError as e:
        from sable.platform.errors import redact_error
        console.print(f"[red]{redact_error(str(e))}[/red]")
        sys.exit(1)

    resolved_org = acc.org or None
    topic_list = [t.strip() for t in topics.split(",") if t.strip()] if topics else None

    with console.status(f"Generating {count} meme ideas..."):
        batch = generate_batch(acc, num_memes=count, topics=topic_list, org_id=resolved_org)

    console.print(f"[green]✓[/green] Generated {len(batch)} ideas\n")

    out_dir = account_output_dir(acc.handle) / "memes"
    out_dir.mkdir(parents=True, exist_ok=True)

    for i, item in enumerate(batch):
        tmpl = item.get("template_id", "unknown")
        topic = item.get("topic", "")
        texts = item.get("texts", {})

        console.print(f"[bold]{i+1}. {tmpl}[/bold] — {topic}")
        for z, t in texts.items():
            console.print(f"   [cyan]{z}[/cyan]: {t}")

        if approve:
            choice = input("  Render + save? [y/n]: ").strip().lower()
            if choice != "y":
                continue

        if do_render or approve:
            out_path = out_dir / f"{tmpl}_{int(time.time())}_{i}.png"
            render_meme(tmpl, texts, out_path)
            import json as _json
            from datetime import datetime, timezone
            _meta = {
                "id": f"meme-{out_path.stem}",
                "type": "meme",
                "source_tool": "sable-meme",
                "account": acc.handle,
                "template": tmpl,
                "topic": topic,
                "texts": texts,
                "output": str(out_path),
                "assembled_at": datetime.now(timezone.utc).isoformat(),
            }
            _atomic_write(Path(str(out_path) + "_meta.json"), _json.dumps(_meta, indent=2))
            console.print(f"  [green]✓[/green] {out_path}")

            # Register as platform artifact if org is resolvable
            resolved_org = acc.org or None
            if resolved_org:
                try:
                    from sable.platform.artifacts import register_content_artifact
                    register_content_artifact(
                        org_id=resolved_org,
                        artifact_type="content_meme",
                        path=str(out_path),
                        metadata={"handle": acc.handle, "template": tmpl, "topic": topic},
                    )
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning("Artifact registration failed: %s", e)

    console.print(f"\n[bold]Done.[/bold] Memes in {out_dir}")


@meme_group.command("setup-templates")
def meme_setup_templates():
    """Print instructions for downloading template images."""
    from sable.meme.templates import load_registry, templates_dir
    reg = load_registry()
    console.print(f"[bold]Template image directory:[/bold] {templates_dir()}\n")
    console.print("Download or copy image files to that directory:\n")
    for t in reg:
        console.print(f"  {t['image_file']}  ({t['name']})")
    console.print(
        "\nMemes will render with placeholder backgrounds until images are added."
    )
