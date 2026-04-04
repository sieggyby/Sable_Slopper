"""CLI for sable narrative — keyword spread scoring for narrative arcs."""
from __future__ import annotations

import json
import sys

import click
from rich.console import Console
from rich.table import Table

console = Console()


@click.group("narrative")
def narrative_group():
    """Narrative velocity — keyword spread scoring for narrative arcs."""


@narrative_group.command("score")
@click.option("--org", required=True, help="Org to score")
@click.option("--beats", "beats_path", default=None, type=click.Path(),
              help="Path to narrative_beats.yaml (defaults to ~/.sable/{org}/)")
@click.option("--days", default=14, show_default=True, help="Look-back window in days")
@click.option("--output", "output_path", default=None, type=click.Path(),
              help="Write JSON report to file")
def narrative_score(org, beats_path, days, output_path):
    """Score keyword uptake for narrative beats."""
    from pathlib import Path
    from sable.lexicon.scanner import MIN_AUTHORS, MIN_TWEETS
    from sable.narrative.tracker import load_beats, score_uptake
    from sable.pulse.meta import db as meta_db

    meta_db.migrate()
    conn = meta_db.get_conn()

    bp = Path(beats_path) if beats_path else None
    try:
        beats = load_beats(org, beats_path=bp)
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        console.print(f"[dim]Create a beats file with: sable narrative beats edit --org {org}[/dim]")
        sys.exit(1)
    except ValueError as e:
        console.print(f"[red]Invalid beats file: {e}[/red]")
        sys.exit(1)

    results = []
    for beat in beats:
        result = score_uptake(beat, org, days=days, conn=conn)
        if result is None:
            console.print(
                f"[yellow]Insufficient data for '{org}' — need ≥{MIN_AUTHORS} authors "
                f"and ≥{MIN_TWEETS} tweets in the last {days} days.[/yellow]"
            )
            sys.exit(0)
        results.append(result)

    if output_path:
        report = [
            {
                "beat": r.beat_name,
                "uptake_score": round(r.uptake_score, 4),
                "uptake_velocity": round(r.uptake_velocity, 4),
                "unique_authors": r.unique_authors,
                "total_authors": r.total_authors,
                "matching_tweets": r.matching_tweets,
                "keywords_matched": r.keywords_matched,
            }
            for r in results
        ]
        Path(output_path).write_text(json.dumps(report, indent=2), encoding="utf-8")
        console.print(f"[dim]Report written: {output_path}[/dim]")

    # Display table
    table = Table(title=f"Narrative Velocity — {org} ({days}d)")
    table.add_column("Beat")
    table.add_column("Uptake", justify="right")
    table.add_column("Velocity", justify="right")
    table.add_column("Authors", justify="right")
    table.add_column("Tweets", justify="right")
    table.add_column("Keywords Hit")

    for r in sorted(results, key=lambda x: x.uptake_score, reverse=True):
        table.add_row(
            r.beat_name,
            f"{r.uptake_score:.1%}",
            f"{r.uptake_velocity:.2f}/d" if r.uptake_velocity else "—",
            f"{r.unique_authors}/{r.total_authors}",
            str(r.matching_tweets),
            ", ".join(r.keywords_matched) if r.keywords_matched else "—",
        )

    console.print(table)


@narrative_group.command("beats")
@click.argument("action", type=click.Choice(["edit"]))
@click.option("--org", required=True, help="Org to edit beats for")
def narrative_beats(action, org):
    """Manage narrative beats file (edit opens $EDITOR)."""
    import os
    from pathlib import Path
    from sable.shared.paths import sable_home

    beats_path = sable_home() / org / "narrative_beats.yaml"
    if not beats_path.exists():
        beats_path.parent.mkdir(parents=True, exist_ok=True)
        beats_path.write_text(
            f"# Narrative beats for {org}\n"
            "beats:\n"
            "  - name: example_narrative\n"
            "    keywords:\n"
            "      - example\n"
            "      - keyword\n"
            "    started_at: \"2026-01-01\"\n",
            encoding="utf-8",
        )
        console.print(f"[dim]Created template: {beats_path}[/dim]")

    editor = os.environ.get("EDITOR", "vi")
    click.edit(filename=str(beats_path), editor=editor)
