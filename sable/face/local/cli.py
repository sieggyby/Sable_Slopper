"""sable face local — operator-laptop-only face-swap pipeline.

Subcommands wrap the four-stage reference extraction (extract, filter, closed,
faceset) plus the FaceFusion swap and roop salvage helpers.

Heavy ML imports happen inside command bodies so `sable face local --help` works
without insightface/cv2 installed.
"""
from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console

from sable.shared.handles import strip_handle
from sable.shared.paths import face_local_workspace

console = Console()


def _resolve_workspace(account: str | None, slug: str | None, video: str | None) -> Path:
    """Pick a workspace dir.

    - If `slug` is given, use it directly.
    - Else derive from video filename stem (or "default" if no video).
    """
    handle = strip_handle(account) if account else "_default"
    if slug:
        s = slug
    elif video:
        s = Path(video).stem.lower().replace(" ", "_")[:48] or "default"
    else:
        s = "default"
    return face_local_workspace(handle, s)


@click.group("local")
def local_group():
    """Operator-laptop-only face swap (FaceFusion + roop). See docs/FACE_LOCAL_SETUP.md."""


@local_group.command("preflight")
@click.option("--facefusion-path", default=None, help="Override FaceFusion install path")
def preflight_cmd(facefusion_path):
    """Smoke-check the install: ffmpeg, insightface, FaceFusion, etc."""
    from rich.table import Table
    from rich import box
    from sable.face.local.preflight import run_checks, all_ok

    checks = run_checks(facefusion_path)
    table = Table(box=box.SIMPLE)
    table.add_column("Check", style="cyan")
    table.add_column("OK")
    table.add_column("Detail")
    for c in checks:
        table.add_row(c.name, "[green]✓[/green]" if c.ok else "[red]✗[/red]", c.detail)
    console.print(table)

    if all_ok(checks):
        console.print("\n[green]All preflight checks passed.[/green]")
    else:
        console.print("\n[red]Some checks failed — see docs/FACE_LOCAL_SETUP.md.[/red]")
        sys.exit(1)


@local_group.command("extract")
@click.argument("video")
@click.option("--account", "-a", default=None, help="Account handle for workspace path")
@click.option("--slug", default=None, help="Override workspace slug (defaults to video stem)")
@click.option("--every", "every_sec", default=2.0, show_default=True, help="Sample every N seconds")
@click.option("--top", default=12, show_default=True, help="Save top-N candidates")
@click.option("--detect-h", default=1080, show_default=True, help="Detection-frame height")
@click.option("--min-face-frac", default=0.08, show_default=True)
def extract_cmd(video, account, slug, every_sec, top, detect_h, min_face_frac):
    """Pull top-N face candidates from a video. Stage 1+2: sample → score → re-extract at full res.

    Output: <workspace>/headshots/top*.png
    """
    from sable.shared.download import maybe_download
    from sable.face.local.extract import extract, ExtractParams

    video_path = maybe_download(video)
    ws = _resolve_workspace(account, slug, str(video_path))
    console.print(f"[cyan]workspace:[/cyan] {ws}")

    saved = extract(
        video_path,
        ws,
        ExtractParams(every_sec=every_sec, detect_h=detect_h, top=top, min_face_frac=min_face_frac),
        progress=lambda m: console.print(m),
    )
    if not saved:
        console.print("[red]No faces found.[/red]")
        sys.exit(1)
    console.print(f"\n[green]✓ Saved {len(saved)} headshots to {ws / 'headshots'}[/green]")


@local_group.command("filter")
@click.argument("video")
@click.option("--reference", "-r", required=True, help="Reference face image (the identity you want)")
@click.option("--account", "-a", default=None)
@click.option("--slug", default=None)
@click.option("--threshold", default=0.45, show_default=True, help="Cosine sim threshold (~0.4-0.5 = same person)")
@click.option("--top", default=15, show_default=True)
@click.option("--every", "every_sec", default=2.0, show_default=True)
@click.option("--bucket", default=6.0, show_default=True, help="Time-bucket for spread (seconds)")
def filter_cmd(video, reference, account, slug, threshold, top, every_sec, bucket):
    """Identity-filter video frames against a reference image.

    Output: <workspace>/matches/top*.png  (+ candidates.pkl cache)
    """
    from sable.shared.download import maybe_download
    from sable.face.local.filter import filter_by_reference, FilterParams

    video_path = maybe_download(video)
    ws = _resolve_workspace(account, slug, str(video_path))
    console.print(f"[cyan]workspace:[/cyan] {ws}")

    saved = filter_by_reference(
        video_path, ws, Path(reference),
        FilterParams(every_sec=every_sec, threshold=threshold, top=top, bucket_size_s=bucket),
        progress=lambda m: console.print(m),
    )
    if not saved:
        console.print("[red]No matches at threshold. Try lowering --threshold.[/red]")
        sys.exit(1)
    console.print(f"\n[green]✓ Saved {len(saved)} matches to {ws / 'matches'}[/green]")


@local_group.command("closed")
@click.argument("video")
@click.option("--reference", "-r", required=True)
@click.option("--account", "-a", default=None)
@click.option("--slug", default=None)
@click.option("--id-threshold", default=0.45, show_default=True)
@click.option("--mar-max", default=0.40, show_default=True, help="Mouth-aspect-ratio ceiling")
@click.option("--top", default=10, show_default=True)
def closed_cmd(video, reference, account, slug, id_threshold, mar_max, top):
    """Add closed-mouth picks to <workspace>/matches/. Requires a prior `filter` run."""
    from sable.shared.download import maybe_download
    from sable.face.local.closed_mouth import closed_mouth, ClosedParams

    video_path = maybe_download(video)
    ws = _resolve_workspace(account, slug, str(video_path))
    console.print(f"[cyan]workspace:[/cyan] {ws}")

    try:
        saved = closed_mouth(
            video_path, ws, Path(reference),
            ClosedParams(id_threshold=id_threshold, mar_max=mar_max, top=top),
            progress=lambda m: console.print(m),
        )
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)
    console.print(f"\n[green]✓ Saved {len(saved)} closed-mouth picks[/green]")


@local_group.command("faceset")
@click.option("--account", "-a", default=None)
@click.option("--slug", default=None)
@click.option("--source", "source_subdir", default="headshots",
              type=click.Choice(["headshots", "matches"]),
              help="Which subdir to build from")
@click.option("--curate-n", default=6, show_default=True)
def faceset_cmd(account, slug, source_subdir, curate_n):
    """Build curated set + averaged embedding + composite from a workspace's picks."""
    from sable.face.local.faceset import build_faceset, FacesetParams

    ws = _resolve_workspace(account, slug, None)
    console.print(f"[cyan]workspace:[/cyan] {ws}")
    try:
        result = build_faceset(
            ws, FacesetParams(curate_n=curate_n),
            source_subdir=source_subdir, progress=lambda m: console.print(m),
        )
    except (FileNotFoundError, RuntimeError) as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)
    console.print(f"\n[green]✓ Curated {result['curated_count']} -> {ws / 'curated'}[/green]")
    if result.get("composite"):
        console.print(f"  Composite (visual sanity check): {result['composite']}")
    console.print(f"  Embedding: {result['embedding']}")


@local_group.command("swap")
@click.argument("source")
@click.argument("target")
@click.option("--output", "-o", required=True, help="Output video path")
@click.option("--swap-model", default="hyperswap_1c_256", show_default=True,
              help="hyperswap_1c_256 | hyperswap_1a_256 | ghost_2_256 | simswap_unofficial_512 | inswapper_128 | ...")
@click.option("--pixel-boost", default="512x512", show_default=True,
              help="Render swap at this resolution before merging back")
@click.option("--enhance", is_flag=True, default=False,
              help="Apply face_enhancer (codeformer w0.4 b50 by default — see FACE_SWAP_LESSONS.md bug #3)")
@click.option("--enhancer-model", default="codeformer", show_default=True)
@click.option("--enhancer-weight", default=0.4, show_default=True, type=float)
@click.option("--enhancer-blend", default=50, show_default=True, type=int)
@click.option("--quality", default=95, show_default=True, type=int)
@click.option("--facefusion-path", default=None, help="Override FaceFusion install path")
def swap_cmd(source, target, output, swap_model, pixel_boost, enhance,
             enhancer_model, enhancer_weight, enhancer_blend, quality, facefusion_path):
    """Run a local FaceFusion swap. Image source → image/video target.

    Examples:
      sable face local swap reference.png target.mp4 -o out.mp4
      sable face local swap reference.png target.mp4 -o out.mp4 --enhance
    """
    from sable.face.local.swap import run_swap, SwapParams

    src = Path(source)
    tgt = Path(target)
    out = Path(output)
    if not src.exists():
        console.print(f"[red]Source not found: {src}[/red]")
        sys.exit(1)
    if not tgt.exists():
        console.print(f"[red]Target not found: {tgt}[/red]")
        sys.exit(1)

    params = SwapParams(
        swap_model=swap_model,
        pixel_boost=pixel_boost,
        enhance=enhance,
        enhancer_model=enhancer_model,
        enhancer_weight=enhancer_weight,
        enhancer_blend=enhancer_blend,
        quality=quality,
    )
    log_path = out.parent / f"{out.stem}_facefusion.log"
    console.print(f"[cyan]Running FaceFusion swap[/cyan] (log: {log_path})")
    console.print(f"  source: {src}")
    console.print(f"  target: {tgt}")
    console.print(f"  output: {out}")
    console.print(f"  model:  {swap_model}, pixel-boost={pixel_boost}, enhance={enhance}")

    try:
        meta = run_swap(src, tgt, out, params,
                        facefusion_override=facefusion_path, log_path=log_path)
    except (RuntimeError, FileNotFoundError) as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)

    console.print(f"\n[green]✓ Done in {meta['elapsed_s']:.0f}s:[/green] {meta['output']}")
    console.print(
        "[yellow]Reminder:[/yellow] perceptually diff a sample frame before declaring success — "
        "see FACE_SWAP_LESSONS.md bug #4."
    )


@local_group.command("salvage")
@click.argument("temp_dir", type=click.Path(exists=True, file_okay=False))
@click.argument("target")
@click.argument("output")
@click.option("--unenhanced-list", required=True, type=click.Path(exists=True),
              help="Text file with one frame name (e.g. '0042') per line")
@click.option("--fps", default=30, show_default=True, type=int)
@click.option("--crf", default=12, show_default=True, type=int)
@click.option("--roop-path", default=None, help="Override roop install path")
def salvage_cmd(temp_dir, target, output, unenhanced_list, fps, crf, roop_path):
    """Finish a crashed roop run: enhance the remaining frames, reassemble, restore audio.

    `temp_dir` is roop's per-job PNG directory. `unenhanced-list` is a text file
    containing one frame name per line (e.g. `0042`) — generate it by comparing
    PNG mtimes against the swapper-stage timestamp range. See FACE_SWAP_LESSONS.md
    bug #6 for the diagnosis pattern.
    """
    from sable.face.local.salvage import finish_enhance, SalvageParams

    names = [ln.strip() for ln in Path(unenhanced_list).read_text().split() if ln.strip()]
    if not names:
        console.print(f"[red]No frame names in {unenhanced_list}[/red]")
        sys.exit(1)

    console.print(f"[cyan]Salvaging {len(names)} frames[/cyan] from {temp_dir}")
    try:
        meta = finish_enhance(
            Path(temp_dir), Path(target), Path(output), names,
            params=SalvageParams(fps=fps, crf=crf),
            roop_override=roop_path,
            progress=lambda m: console.print(m),
        )
    except (RuntimeError, FileNotFoundError) as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)
    console.print(f"\n[green]✓ Salvaged in {meta['elapsed_s']:.0f}s:[/green] {meta['output']}")
