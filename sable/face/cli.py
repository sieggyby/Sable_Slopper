"""sable face — Replicate-powered face swap CLI."""
from __future__ import annotations

import sys
from pathlib import Path
import time

import click
from rich.console import Console
from rich.table import Table
from rich import box

console = Console()


@click.group("face")
def face_group():
    """Swap faces in images, video, and GIFs using Replicate."""


@face_group.command("swap")
@click.argument("target", type=click.Path(exists=True))
@click.option("--account", "-a", required=True, help="Account handle (to look up reference face)")
@click.option("--reference", "-r", default=None, help="Reference face name (overrides account default)")
@click.option("--output", "-o", default=None)
@click.option("--quality", default="medium", type=click.Choice(["low", "medium", "high"]))
@click.option("--max-cost", default=None, type=float, help="Abort if estimated cost exceeds this (USD)")
@click.option("--dry-run", is_flag=True)
@click.option("--skip-consent-check", is_flag=True, hidden=True)
def face_swap(target, account, reference, output, quality, max_cost, dry_run, skip_consent_check):
    """Swap face in target image or video."""
    from sable.roster.manager import require_account
    from sable.face.library import get_reference
    from sable.face.safety import require_consent
    from sable.face.cost import estimate_image_cost, estimate_video_cost, check_budget, format_cost_estimate
    from sable.face.swapper import swap_image
    from sable.face.video import swap_video
    from sable.shared.paths import account_output_dir
    from sable.shared.ffmpeg import get_duration

    try:
        acc = require_account(account)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)

    ref_name = reference or acc.handle.lstrip("@")
    try:
        ref = get_reference(ref_name)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)

    if not skip_consent_check:
        try:
            require_consent(ref_name)
        except RuntimeError as e:
            console.print(f"[red]{e}[/red]")
            sys.exit(1)

    target_path = Path(target)
    is_video = target_path.suffix.lower() in (".mp4", ".mov", ".avi", ".mkv", ".webm")

    # Cost estimate
    if is_video:
        duration = get_duration(target_path)
        strategy = "frame-by-frame" if quality in ("medium", "high") else "native"
        estimate = estimate_video_cost(duration, strategy=strategy)
    else:
        cost = estimate_image_cost()
        estimate = {"strategy": "image", "cost_usd": cost, "model": "facefusion"}

    console.print("[bold]Cost estimate:[/bold]")
    console.print(format_cost_estimate(estimate))

    try:
        check_budget(estimate["cost_usd"], max_cost)
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)

    if dry_run:
        console.print("[yellow](dry run — skipping swap)[/yellow]")
        return

    if output is None:
        out_dir = account_output_dir(acc.handle) / "faceswap"
        out_dir.mkdir(parents=True, exist_ok=True)
        suffix = target_path.suffix
        output = str(out_dir / f"swap_{int(time.time())}{suffix}")

    ref_image = ref["path"]

    with console.status("Running face swap..."):
        if is_video:
            meta = swap_video(
                target_path, ref_image, output,
                reference_name=ref_name, quality=quality,
            )
        else:
            out_path, model = swap_image(target_path, ref_image, output)
            meta = {"output": out_path, "model": model}

    console.print(f"\n[green]✓ Done:[/green] {meta['output']}")
    if "swapped_frames" in meta:
        console.print(f"  Frames: {meta['swapped_frames']}/{meta['total_frames']}")

    # Write sidecar metadata
    import json as _json
    from datetime import datetime, timezone
    _out = str(meta["output"])
    _face_meta = {
        "id": f"faceswap-{Path(_out).stem}",
        "type": "faceswap",
        "source_tool": "sable-face",
        "account": acc.handle,
        "target": str(target_path),
        "output": _out,
        "strategy": meta.get("strategy", "image"),
        "assembled_at": datetime.now(timezone.utc).isoformat(),
    }
    Path(_out + "_meta.json").write_text(_json.dumps(_face_meta, indent=2))


# ---------------------------------------------------------------------------
# Library management
# ---------------------------------------------------------------------------

@face_group.group("library")
def library_group():
    """Manage reference face library."""


@library_group.command("add")
@click.argument("image", type=click.Path(exists=True))
@click.option("--name", "-n", required=True)
@click.option("--consent", is_flag=True, help="Mark as consented")
@click.option("--notes", default="")
@click.option("--no-copy", is_flag=True)
def library_add(image, name, consent, notes, no_copy):
    """Add a reference face image."""
    from sable.face.library import add_reference
    add_reference(image, name=name, consent=consent, notes=notes, copy=not no_copy)
    status = "[green]consented[/green]" if consent else "[yellow]no consent flag[/yellow]"
    console.print(f"[green]✓ Added[/green] {name} ({status})")


@library_group.command("list")
@click.option("--consent-only", is_flag=True)
def library_list(consent_only):
    """List reference faces."""
    from sable.face.library import list_references
    refs = list_references(consent_only=consent_only)
    if not refs:
        console.print("[yellow]No reference faces. Add with: sable face library add <image> --name <name>[/yellow]")
        return
    table = Table(box=box.SIMPLE)
    table.add_column("Name", style="cyan")
    table.add_column("File")
    table.add_column("Consent")
    table.add_column("Notes")
    for r in refs:
        table.add_row(
            r["name"], r.get("filename", "?"),
            "✓" if r.get("consent") else "✗",
            r.get("notes", "")[:40] or "—",
        )
    console.print(table)


@library_group.command("remove")
@click.argument("name")
@click.confirmation_option(prompt="Remove this reference face?")
def library_remove(name):
    from sable.face.library import remove_reference
    if remove_reference(name):
        console.print(f"[green]✓ Removed {name}[/green]")
    else:
        console.print(f"[red]Not found: {name}[/red]")


@face_group.command("audit-log")
@click.option("--limit", default=20, show_default=True)
def audit_log(limit):
    """Show recent face swap audit log."""
    from sable.face.safety import read_audit_log
    entries = read_audit_log(limit=limit)
    if not entries:
        console.print("[yellow]No audit log entries.[/yellow]")
        return
    for e in entries:
        console.print(f"  {e.get('timestamp', '?')[:19]}  {e.get('reference')}  {e.get('model')}  ${e.get('cost_usd', 0):.4f}")
