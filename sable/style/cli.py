"""CLI for sable style-delta — posting style gap analysis."""
from __future__ import annotations

import sys

import click
from rich.console import Console

console = Console()


@click.command("style-delta")
@click.option("--handle", required=True, help="Managed account handle")
@click.option("--org", required=True, help="Org for watchlist comparison")
@click.option("--output", "output_path", default=None, type=click.Path(),
              help="Write markdown report to file")
def style_delta_command(handle, org, output_path):
    """Quantitative posting style gap analysis vs watchlist top performers."""
    import sqlite3
    from pathlib import Path
    from sable.shared.paths import pulse_db_path, meta_db_path
    from sable.style.fingerprint import fingerprint_managed, fingerprint_watchlist, MIN_POSTS
    from sable.style.delta import compute_delta
    from sable.style.report import render_delta_report

    # Open pulse.db
    pdb = pulse_db_path()
    if not pdb.exists():
        console.print("[red]pulse.db not found. Run sable pulse first.[/red]")
        sys.exit(1)
    pulse_conn = sqlite3.connect(str(pdb))
    pulse_conn.row_factory = sqlite3.Row

    # Open meta.db
    mdb = meta_db_path()
    meta_conn = None
    if mdb.exists():
        meta_conn = sqlite3.connect(str(mdb))
        meta_conn.row_factory = sqlite3.Row

    try:
        managed_fp = fingerprint_managed(handle, pulse_conn, meta_conn)
        if not managed_fp:
            console.print(
                f"[yellow]Insufficient data for {handle} — "
                f"need ≥{MIN_POSTS} posts in pulse.db.[/yellow]"
            )
            sys.exit(0)

        if meta_conn is None:
            console.print("[red]meta.db not found. Run sable pulse meta scan first.[/red]")
            sys.exit(1)

        watchlist_fp = fingerprint_watchlist(org, meta_conn)
        if not watchlist_fp:
            console.print(
                f"[yellow]Insufficient watchlist data for {org} — "
                f"need ≥{MIN_POSTS} tweets with lift data.[/yellow]"
            )
            sys.exit(0)

        delta = compute_delta(managed_fp, watchlist_fp)
        if delta is None:
            console.print("[yellow]Cannot compute delta — insufficient data.[/yellow]")
            sys.exit(0)

        md = render_delta_report(handle, org, delta, managed_fp, watchlist_fp, console)

        if output_path:
            Path(output_path).write_text(md, encoding="utf-8")
            console.print(f"[dim]Report written: {output_path}[/dim]")

    finally:
        pulse_conn.close()
        if meta_conn:
            meta_conn.close()
