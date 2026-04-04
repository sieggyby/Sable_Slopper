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
@click.argument("video")
@click.option("--account", "-a", required=True, help="Account handle e.g. @tig_intern")
@click.option("--num-clips", "-n", default=None, type=int,
              help="Max clips to produce (default: all worthy clips)")
@click.option("--min-duration", default=15.0, show_default=True)
@click.option("--max-duration", default=45.0, show_default=True)
@click.option("--caption-style", default=None, help="Override: word|phrase|none")
@click.option("--caption-color", default=None, help="Caption color: white|yellow|black|cyan|green|red|#RRGGBB (default: auto)")
@click.option("--brainrot-energy", default=None, help="Override: low|medium|high")
@click.option("--whisper-model", default="base.en", show_default=True)
@click.option("--dry-run", is_flag=True)
@click.option("--no-brainrot", is_flag=True, help="Skip brainrot overlay")
@click.option("--image-overlay", default=None, type=click.Path(), help="PNG to overlay in bottom-left corner (e.g. a character or logo)")
@click.option("--target-duration", default=None, type=float, help="Target clip duration in seconds (ends at speech boundary)")
@click.option("--clip-sizes", default=None, help="Comma-separated target durations e.g. 15,30")
@click.option("--platform", default="twitter",
              type=click.Choice(["twitter", "discord", "telegram"]),
              show_default=True,
              help="Output encoding profile (affects resolution and file size)")
@click.option("--no-highlight", is_flag=True,
              help="Disable active-word highlight (karaoke effect) on captions")
@click.option("--audio-only", is_flag=True,
              help="Use source audio only — brainrot fills the full frame (for podcasts, screen-shares)")
@click.option("--face-track", is_flag=True,
              help="Center crop on detected faces (falls back to motion tracking, then center)")
@click.option("--org", default=None, help="Org slug for cost logging (defaults to account's org).")
def clip_process(
    video, account, num_clips, min_duration, max_duration,
    caption_style, caption_color, brainrot_energy, whisper_model, dry_run, no_brainrot,
    image_overlay, target_duration, clip_sizes, platform, no_highlight, audio_only,
    face_track, org,
):
    """Process a video into short-form vertical clips for an account."""
    from sable.shared.download import maybe_download
    from sable.roster.manager import require_account

    try:
        video = str(maybe_download(video))
    except (FileNotFoundError, RuntimeError) as e:
        from sable.platform.errors import redact_error
        console.print(f"[red]{redact_error(str(e))}[/red]")
        sys.exit(1)
    from sable.clip.transcribe import transcribe
    from sable.clip.selector import select_clips
    from sable.clip.assembler import assemble_clip
    from sable.shared.paths import account_output_dir

    try:
        acc = require_account(account)
    except ValueError as e:
        from sable.platform.errors import redact_error
        console.print(f"[red]{redact_error(str(e))}[/red]")
        sys.exit(1)

    resolved_org = org or acc.org or None

    energy = brainrot_energy or acc.content.brainrot_energy
    cap_style = caption_style or acc.content.caption_style

    # Parse --clip-sizes if provided (takes precedence over --target-duration for min/max)
    target_durations = None
    if clip_sizes:
        target_durations = [float(x.strip()) for x in clip_sizes.split(",") if x.strip()]
        if min_duration == 15.0:  # default — not explicitly set
            min_duration = min(target_durations) - 10
        if max_duration == 45.0:  # default — not explicitly set
            max_duration = max(target_durations) + 10
    elif target_duration is not None:
        # Relaxed tolerance: ±10s for ≤30s targets, ±20% for longer
        if target_duration <= 30:
            tol = 10.0
        else:
            tol = target_duration * 0.20
        if min_duration == 15.0:  # default — not explicitly set
            min_duration = target_duration - tol
        if max_duration == 45.0:  # default — not explicitly set
            max_duration = target_duration + tol

    console.print(f"[cyan]Processing[/cyan] {video} for {acc.handle}  [cyan]Platform:[/cyan] {platform}")

    # Step 1: Transcribe
    with console.status("Transcribing audio..."):
        transcript = transcribe(video, model=whisper_model)
    seg_count = len(transcript.get("segments", []))
    word_count = len(transcript.get("words", []))
    console.print(f"[green]✓[/green] Transcript: {seg_count} segments, {word_count} words")

    # Step 2: Select clips
    with console.status("Selecting best clips with Claude..."):
        clips = select_clips(
            transcript, acc,
            max_clips=num_clips,
            min_duration=min_duration,
            max_duration=max_duration,
            dry_run=dry_run,
            org_id=resolved_org,
        )
    if dry_run and clips and clips[0].get("window_count") is not None:
        console.print(f"[green]✓[/green] Selected {len(clips)} clips ({clips[0]['window_count']} windows detected)")
    else:
        console.print(f"[green]✓[/green] Selected {len(clips)} clips")

    if dry_run:
        table = Table(box=box.SIMPLE)
        table.add_column("Clip")
        table.add_column("Score")
        table.add_column("Start")
        table.add_column("End")
        table.add_column("Duration")
        table.add_column("Reason")
        for i, c in enumerate(clips):
            dur = c["end"] - c["start"]
            table.add_row(
                f"#{i+1}",
                str(c.get("score", "?")),
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
        score = clip.get("score", "?")
        console.print(f"  Assembling clip {i+1}/{len(clips)} (score {score}/10)...")
        meta = assemble_clip(
            source_video=video,
            output_path=out_file,
            start=clip["start"],
            end=clip["end"],
            account_handle=acc.handle,
            brainrot_energy=energy if not no_brainrot else "none",
            caption_style=cap_style,
            captions_segments=transcript.get("words") or transcript.get("segments", []),
            image_overlay_path=image_overlay,
            caption_color=caption_color,
            caption_hint=clip.get("caption_hint"),
            platform=platform,
            highlight_active=not no_highlight,
            audio_only=audio_only,
            face_track=face_track,
            org_id=resolved_org,
        )
        console.print(f"  [green]✓[/green] {out_file}")
        if meta.get("thumbnail"):
            console.print(f"  🖼  {meta['thumbnail']}")
        if clip.get("caption_hint"):
            console.print(f"  [dim]Caption: {clip['caption_hint']}[/dim]")

        # Register as platform artifact if org is resolvable
        if resolved_org:
            try:
                from sable.platform.artifacts import register_content_artifact
                register_content_artifact(
                    org_id=resolved_org,
                    artifact_type="content_clip",
                    path=str(out_file),
                    metadata={
                        "handle": acc.handle,
                        "score": clip.get("score"),
                        "caption_hint": clip.get("caption_hint", ""),
                    },
                )
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning("Artifact registration failed: %s", e)

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


@brainrot_group.command("remove")
@click.argument("filename")
@click.option("--delete", is_flag=True, help="Also delete the file from the brainrot library directory")
def brainrot_remove(filename, delete):
    """Remove a video from the brainrot library."""
    from sable.clip.brainrot import load_index, save_index
    from sable.shared.paths import brainrot_dir

    index = load_index()
    # Match by filename or basename of path
    basename = Path(filename).name
    removed = [e for e in index if e.get("filename") == basename or Path(e.get("path", "")).name == basename]
    index = [e for e in index if e.get("filename") != basename and Path(e.get("path", "")).name != basename]

    if not removed:
        console.print(f"[yellow]No entry found for '{basename}' in the index.[/yellow]")
        return

    save_index(index)
    console.print(f"[green]✓[/green] Removed '{basename}' from index.")

    if delete:
        for entry in removed:
            file_path = Path(entry.get("path", ""))
            if not file_path.is_absolute():
                file_path = brainrot_dir() / basename
            if file_path.exists():
                file_path.unlink()
                console.print(f"[green]✓[/green] Deleted file: {file_path}")
            else:
                console.print(f"[yellow]File not found on disk (already gone?): {file_path}[/yellow]")


@brainrot_group.command("trace")
@click.argument("filename")
@click.option("--search-dir", default=None, type=click.Path(), help="Root dir to search for .meta.json files (default: ~/.sable/output)")
def brainrot_trace(filename, search_dir):
    """Find all output clips that used a given brainrot source file."""
    import json as _json
    from sable.shared.paths import sable_home

    basename = Path(filename).name
    root = Path(search_dir) if search_dir else sable_home() / "output"

    if not root.exists():
        console.print(f"[yellow]Search dir not found: {root}[/yellow]")
        return

    matches = []
    for meta_file in root.rglob("*.meta.json"):
        try:
            data = _json.loads(meta_file.read_text())
            src = data.get("brainrot_source", "")
            if Path(src).name == basename or basename in src:
                clip = meta_file.with_suffix("").with_suffix(".mp4")
                matches.append({
                    "clip": str(clip),
                    "exists": clip.exists(),
                    "assembled_at": data.get("assembled_at", "?"),
                    "source_video": Path(data.get("source", "?")).name,
                })
        except Exception:
            continue

    if not matches:
        console.print(f"[yellow]No clips found that used '{basename}'. "
                      f"(Only clips assembled after logging was added will appear here.)[/yellow]")
        return

    table = Table(box=box.SIMPLE)
    table.add_column("Clip")
    table.add_column("Source Video")
    table.add_column("Assembled At")
    table.add_column("Exists")
    for m in matches:
        table.add_row(
            m["clip"],
            m["source_video"],
            m["assembled_at"],
            "[green]yes[/green]" if m["exists"] else "[red]no[/red]",
        )
    console.print(table)
    console.print(f"\n[dim]{len(matches)} clip(s) found using '{basename}'[/dim]")
