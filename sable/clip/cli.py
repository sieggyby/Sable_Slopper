"""sable clip — video to vertical clips CLI."""
from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich import box

console = Console()


@click.group("clip")
def clip_group():
    """Process videos into vertical short-form clips."""


@clip_group.command("process")
@click.argument("video", type=click.Path(exists=True))
@click.option("--account", "-a", required=True, help="Account handle e.g. @tig_intern")
@click.option("--num-clips", "-n", default=3, show_default=True)
@click.option("--min-duration", default=15.0, show_default=True)
@click.option("--max-duration", default=60.0, show_default=True)
@click.option("--caption-style", default=None, help="Override: word|phrase|none")
@click.option("--brainrot-energy", default=None, help="Override: low|medium|high")
@click.option("--whisper-model", default="base.en", show_default=True)
@click.option("--dry-run", is_flag=True)
@click.option("--no-brainrot", is_flag=True, help="Skip brainrot overlay")
def clip_process(
    video, account, num_clips, min_duration, max_duration,
    caption_style, brainrot_energy, whisper_model, dry_run, no_brainrot
):
    """Process a video into short-form vertical clips for an account."""
    from sable.roster.manager import require_account
    from sable.clip.transcribe import transcribe
    from sable.clip.selector import select_clips
    from sable.clip.assembler import assemble_clip
    from sable.shared.paths import account_output_dir

    try:
        acc = require_account(account)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)

    energy = brainrot_energy or acc.content.brainrot_energy
    cap_style = caption_style or acc.content.caption_style

    console.print(f"[cyan]Processing[/cyan] {video} for {acc.handle}")

    # Step 1: Transcribe
    with console.status("Transcribing audio..."):
        transcript = transcribe(video, model=whisper_model)
    console.print(f"[green]✓[/green] Transcript: {len(transcript.get('segments', []))} segments")

    # Step 2: Select clips
    with console.status("Selecting best clips with Claude..."):
        clips = select_clips(
            transcript, acc,
            num_clips=num_clips,
            min_duration=min_duration,
            max_duration=max_duration,
            dry_run=dry_run,
        )
    console.print(f"[green]✓[/green] Selected {len(clips)} clips")

    if dry_run:
        table = Table(box=box.SIMPLE)
        table.add_column("Clip")
        table.add_column("Start")
        table.add_column("End")
        table.add_column("Duration")
        table.add_column("Reason")
        for i, c in enumerate(clips):
            dur = c["end"] - c["start"]
            table.add_row(
                f"#{i+1}",
                f"{c['start']:.1f}s",
                f"{c['end']:.1f}s",
                f"{dur:.1f}s",
                c.get("reason", "")[:60],
            )
        console.print(table)
        return

    # Step 3: Assemble
    out_dir = account_output_dir(acc.handle) / "clips" / Path(video).stem
    out_dir.mkdir(parents=True, exist_ok=True)

    for i, clip in enumerate(clips):
        out_file = out_dir / f"clip_{i+1:02d}.mp4"
        console.print(f"  Assembling clip {i+1}/{len(clips)}...")
        meta = assemble_clip(
            source_video=video,
            output_path=out_file,
            start=clip["start"],
            end=clip["end"],
            account_handle=acc.handle,
            brainrot_energy=energy if not no_brainrot else "none",
            caption_style=cap_style,
            captions_segments=transcript.get("segments", []),
        )
        console.print(f"  [green]✓[/green] {out_file}")
        if clip.get("caption_hint"):
            console.print(f"  [dim]Caption: {clip['caption_hint']}[/dim]")

    console.print(f"\n[bold green]Done.[/bold green] Output: {out_dir}")


# ---------------------------------------------------------------------------
# Brainrot library management
# ---------------------------------------------------------------------------

@clip_group.group("brainrot")
def brainrot_group():
    """Manage the brainrot video library."""


@brainrot_group.command("add")
@click.argument("video", type=click.Path(exists=True))
@click.option("--energy", "-e", default="medium", type=click.Choice(["low", "medium", "high"]))
@click.option("--tags", default="", help="Comma-separated tags")
@click.option("--no-copy", is_flag=True, help="Reference in-place, don't copy")
def brainrot_add(video, energy, tags, no_copy):
    """Add a video to the brainrot library."""
    from sable.clip.brainrot import add_video
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    entry = add_video(video, energy=energy, tags=tag_list, copy=not no_copy)
    console.print(f"[green]✓[/green] Added {entry['filename']} (energy={energy}, {entry['duration']:.1f}s)")


@brainrot_group.command("list")
@click.option("--energy", default=None, type=click.Choice(["low", "medium", "high"]))
def brainrot_list(energy):
    """List brainrot library."""
    from sable.clip.brainrot import list_videos
    videos = list_videos(energy=energy)
    if not videos:
        console.print("[yellow]No brainrot videos. Add with: sable clip brainrot add <file>[/yellow]")
        return
    table = Table(box=box.SIMPLE)
    table.add_column("File")
    table.add_column("Energy")
    table.add_column("Duration")
    table.add_column("Tags")
    for v in videos:
        table.add_row(
            v.get("filename", "?"),
            v.get("energy", "?"),
            f"{v.get('duration', 0):.1f}s",
            ", ".join(v.get("tags", [])) or "—",
        )
    console.print(table)
