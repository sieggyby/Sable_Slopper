"""CLI for sable silence-gradient — pre-decay cadence signals."""
from __future__ import annotations

import json
import sys

import click
from rich.console import Console
from rich.table import Table

console = Console()


@click.command("silence-gradient")
@click.option("--org", required=True, help="Org to analyze")
@click.option("--top", "top_n", default=20, show_default=True, help="Show top N authors")
@click.option("--window", "window_days", default=30, show_default=True,
              help="Window in days (must be even, >= 6)")
@click.option("--include-insufficient", "include_insufficient", is_flag=True, default=False,
              help="Include authors with some insufficient signals")
@click.option("--output", "output_path", default=None, type=click.Path(),
              help="Write JSON report to file")
def silence_gradient_command(org, top_n, window_days, include_insufficient, output_path):
    """Compute pre-decay cadence signals from watchlist data."""
    from pathlib import Path
    from sable.pulse.meta import db as meta_db
    from sable.cadence.combine import compute_silence_gradient, MIN_WINDOW_DAYS
    from sable.cadence.store import upsert_cadence

    meta_db.migrate()
    conn = meta_db.get_conn()

    try:
        results = compute_silence_gradient(org, window_days=window_days, conn=conn)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)

    if not results:
        console.print(f"[yellow]No authors with sufficient data for '{org}'.[/yellow]")
        sys.exit(0)

    # Filter insufficient if not requested
    if not include_insufficient:
        display = [r for r in results if r["insufficient_data"] is None]
    else:
        display = results

    # Store results
    upsert_cadence(results, conn)

    # Truncate display
    display = display[:top_n]

    if output_path:
        Path(output_path).write_text(
            json.dumps(results, indent=2), encoding="utf-8"
        )
        console.print(f"[dim]Report written: {output_path}[/dim]")

    # Rich table
    table = Table(title=f"Silence Gradient — {org} ({window_days}d)")
    table.add_column("Rank", justify="right")
    table.add_column("Author")
    table.add_column("Gradient", justify="right")
    table.add_column("Vol↓", justify="right")
    table.add_column("Eng↓", justify="right")
    table.add_column("Fmt↓", justify="right")
    table.add_column("Posts R/P", justify="right")
    table.add_column("Gaps")

    for i, r in enumerate(display, 1):
        gaps = r.get("insufficient_data") or "—"
        table.add_row(
            str(i),
            r["author_handle"],
            f"{r['silence_gradient']:.3f}",
            f"{r['vol_drop']:.2f}",
            f"{r['eng_drop']:.2f}",
            f"{r['fmt_reg']:.2f}",
            f"{r['posts_recent_half']}/{r['posts_prior_half']}",
            gaps,
        )

    console.print(table)
