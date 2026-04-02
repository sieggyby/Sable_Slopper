"""CLI for character explainer: generate + list-characters."""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table

console = Console()


@click.group("character-explainer")
def explainer_group():
    """Generate brainrot explainer videos with famous character voices."""


@explainer_group.command("generate")
@click.option("--topic", required=True, help="Topic to explain (e.g. 'What is a DAO')")
@click.option("--character", required=True, help="Character ID (e.g. peter_griffin)")
@click.option("--bg-video", default=None, help="Path to brainrot background video")
@click.option("--output", "-o", default=None, help="Output video path")
@click.option("--background-md", default=None, type=click.Path(exists=True),
              help="Optional markdown context file for the topic")
@click.option("--tts-backend", default=None, type=click.Choice(["local", "elevenlabs"]),
              help="TTS backend (overrides character default)")
@click.option("--target-duration", default=30, type=int, show_default=True,
              help="Target video duration in seconds")
@click.option("--no-talking-head", is_flag=True, default=False,
              help="Skip talking head overlay even if character has mouth images configured")
@click.option("--orientation", default="landscape",
              type=click.Choice(["landscape", "portrait"]), show_default=True,
              help="Output orientation: landscape (1280×720) or portrait (720×1280)")
@click.option("--platform", default="twitter",
              type=click.Choice(["twitter", "youtube", "discord", "telegram"]), show_default=True,
              help="Optimize encoding for target platform")
def generate_cmd(
    topic: str,
    character: str,
    bg_video: Optional[str],
    output: Optional[str],
    background_md: Optional[str],
    tts_backend: Optional[str],
    target_duration: int,
    no_talking_head: bool,
    orientation: str,
    platform: str,
) -> None:
    """Generate a character explainer video."""
    from sable.character_explainer.config import ExplainerConfig
    from sable.character_explainer.pipeline import generate_explainer
    from sable.shared.paths import account_output_dir, explainer_resources_dir

    topic_slug = re.sub(r"[^\w]+", "_", topic.lower()).strip("_")[:40]
    topic_resource_dir = explainer_resources_dir() / topic_slug

    background: Optional[str] = None

    if background_md:
        src = Path(background_md)
        topic_resource_dir.mkdir(parents=True, exist_ok=True)
        dest = topic_resource_dir / src.name
        if src.resolve() != dest.resolve():
            shutil.copy2(src, dest)
        console.print(f"  Resource     : [green]saved[/green] → {dest}")
        background = dest.read_text()
    else:
        existing = sorted(topic_resource_dir.glob("*.md")) if topic_resource_dir.exists() else []
        if existing:
            background = existing[0].read_text()
            console.print(f"  Resource     : [cyan]loaded[/cyan] ← {existing[0]}")
        else:
            console.print(
                f"[red]Error:[/red] No resource file found for topic '{topic}'.\n"
                f"  Run with --background-md <file> to register one.\n"
                f"  Resources are stored in: {topic_resource_dir}"
            )
            raise SystemExit(1)

    # Resolve output path
    if output is None:
        out_dir = account_output_dir("@explainer") / topic_slug
        out_dir.mkdir(parents=True, exist_ok=True)
        output = str(out_dir / f"{character}.mp4")

    config = ExplainerConfig(
        target_duration_seconds=target_duration,
        tts_backend=tts_backend or "local",
        background_video_path=bg_video or "",
        talking_head_enabled=not no_talking_head,
        orientation=orientation,
        platform=platform,
    )

    console.print(f"[cyan]Generating explainer:[/cyan] {topic}")
    console.print(f"  Character    : {character}")
    console.print(f"  TTS          : {config.tts_backend}")
    console.print(f"  Orientation  : {orientation} ({config.output_width}×{config.output_height})")
    console.print(f"  Platform     : {platform} (crf={config.crf}, preset={config.video_preset}, audio={config.audio_bitrate})")
    console.print(f"  Talking head : {'disabled' if no_talking_head else 'enabled'}")
    console.print(f"  Output       : {output}")

    try:
        result = generate_explainer(
            topic=topic,
            character_id=character,
            output_path=output,
            background=background,
            config=config,
        )
        console.print(f"[green]✓ Done:[/green] {result}")
    except Exception as e:
        from sable.platform.errors import redact_error
        console.print(f"[red]Error:[/red] {redact_error(str(e))}")
        raise SystemExit(1)


@explainer_group.command("setup-voice")
@click.option("--character", required=True, help="Character ID (e.g. peter_griffin)")
@click.option("--source", required=True, help="YouTube URL or local video/audio path")
@click.option("--start", default=None, type=float, help="Clip start in seconds (optional)")
@click.option("--end", default=None, type=float, help="Clip end in seconds (optional)")
@click.option("--mouth-open", default=None, type=click.Path(exists=True),
              help="Mouth-open PNG to install for this character")
@click.option("--mouth-closed", default=None, type=click.Path(exists=True),
              help="Mouth-closed PNG to install for this character")
def setup_voice_cmd(
    character: str,
    source: str,
    start: Optional[float],
    end: Optional[float],
    mouth_open: Optional[str],
    mouth_closed: Optional[str],
) -> None:
    """Download a voice sample and optionally install mouth images for a character."""
    import shutil
    import tempfile

    import yaml

    from sable.character_explainer.characters import CHARACTERS_DIR
    from sable.shared.download import maybe_download
    from sable.shared.ffmpeg import extract_audio, extract_clip
    from sable.shared.paths import sable_home

    # Validate character exists
    profile_path = CHARACTERS_DIR / character / "profile.yaml"
    if not profile_path.exists():
        console.print(f"[red]Character '{character}' not found.[/red]")
        raise SystemExit(1)

    voice_samples_dir = sable_home() / "voice_samples"
    voice_samples_dir.mkdir(parents=True, exist_ok=True)
    wav_path = voice_samples_dir / f"{character}.wav"

    # Download or resolve source
    console.print(f"[cyan]Resolving source:[/cyan] {source}")
    try:
        video_path = maybe_download(source)
    except Exception as e:
        from sable.platform.errors import redact_error
        console.print(f"[red]Download failed:[/red] {redact_error(str(e))}")
        raise SystemExit(1)
    console.print(f"  Source     : {video_path}")

    # Extract audio (with optional clip trimming)
    with tempfile.TemporaryDirectory(prefix="sable_sv_") as tmp:
        tmp_path = Path(tmp)
        if start is not None or end is not None:
            clip_start = start or 0.0
            if end is None:
                from sable.shared.ffmpeg import get_duration
                clip_end = get_duration(video_path)
            else:
                clip_end = end
            console.print(f"  Trimming   : {clip_start}s → {clip_end}s")
            clipped = tmp_path / "clipped.mp4"
            extract_clip(video_path, clipped, clip_start, clip_end)
            audio_source = clipped
        else:
            audio_source = video_path

        extract_audio(audio_source, wav_path)

    file_size_kb = wav_path.stat().st_size // 1024
    console.print(f"[green]✓ Voice sample:[/green] {wav_path} ({file_size_kb} KB)")

    # Install mouth images if provided
    if mouth_open or mouth_closed:
        char_images_dir = sable_home() / "character_images" / character
        char_images_dir.mkdir(parents=True, exist_ok=True)

        image_paths: dict[str, str] = {}

        if mouth_open:
            dest = char_images_dir / "mouth_open.png"
            shutil.copy2(mouth_open, dest)
            image_paths["image_open_mouth"] = f"~/.sable/character_images/{character}/mouth_open.png"
            console.print(f"[green]✓ Mouth open:[/green] {dest}")

        if mouth_closed:
            dest = char_images_dir / "mouth_closed.png"
            shutil.copy2(mouth_closed, dest)
            image_paths["image_closed_mouth"] = f"~/.sable/character_images/{character}/mouth_closed.png"
            console.print(f"[green]✓ Mouth closed:[/green] {dest}")

        # Update profile.yaml: append new fields if not already present
        content = profile_path.read_text()
        existing = yaml.safe_load(content)
        additions = []
        for key, val in image_paths.items():
            if key not in existing:
                additions.append(f"{key}: {val}")
        if additions:
            content = content.rstrip("\n") + "\n" + "\n".join(additions) + "\n"
            profile_path.write_text(content)
            console.print(f"[green]✓ Updated profile:[/green] {profile_path}")
        else:
            console.print("[yellow]Profile already has image paths — skipping update.[/yellow]")


@explainer_group.command("list-characters")
def list_characters_cmd() -> None:
    """List all available characters."""
    from sable.character_explainer.characters import list_characters, load_character

    ids = list_characters()
    if not ids:
        console.print("[yellow]No characters found.[/yellow]")
        return

    table = Table(title="Available Characters")
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("TTS Backend")
    table.add_column("ElevenLabs Voice ID")

    for cid in ids:
        try:
            profile = load_character(cid)
            table.add_row(
                profile.id,
                profile.display_name,
                profile.tts_backend,
                profile.elevenlabs_voice_id or "—",
            )
        except Exception as e:
            from sable.platform.errors import redact_error
            table.add_row(cid, f"[red]Error: {redact_error(str(e))}[/red]", "", "")

    console.print(table)
