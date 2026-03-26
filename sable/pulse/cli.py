"""sable pulse — performance tracking and recommendation CLI."""
from __future__ import annotations

import json
import sys

import click
from rich.console import Console
from rich.table import Table
from rich import box

console = Console()


@click.group("pulse")
def pulse_group():
    """Track performance, generate reports, and get AI recommendations."""


# Register meta subgroup
from sable.pulse.meta.cli import meta_group
pulse_group.add_command(meta_group)


@pulse_group.command("track")
@click.option("--account", "-a", required=True)
@click.option("--mock", is_flag=True, help="Use mock data (no API key required)")
def pulse_track(account, mock):
    """Fetch recent tweets and record performance snapshots."""
    from sable.pulse.tracker import snapshot_account
    from sable.pulse.db import migrate

    migrate()
    handle = account if account.startswith("@") else f"@{account}"

    try:
        with console.status(f"Fetching tweets for {handle}..."):
            tweets = snapshot_account(handle, mock=mock)
        console.print(f"[green]✓[/green] Tracked {len(tweets)} tweets for {handle}")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@pulse_group.command("report")
@click.option("--account", "-a", required=True)
@click.option("--followers", default=1000, show_default=True, help="Follower count for ER calc")
@click.option("--limit", default=50, show_default=True)
@click.option("--sort-by", default="engagement_rate",
              type=click.Choice(["engagement_rate", "virality_score", "views", "likes"]))
@click.option("--export-md", default=None, help="Export to markdown file")
def pulse_report(account, followers, limit, sort_by, export_md):
    """Show performance report for an account."""
    from sable.pulse.reporter import render_report, export_markdown

    handle = account if account.startswith("@") else f"@{account}"
    render_report(handle, followers=followers, limit=limit, sort_by=sort_by)

    if export_md:
        export_markdown(handle, export_md, followers=followers, limit=limit)
        console.print(f"[dim]Exported to {export_md}[/dim]")


@pulse_group.command("recommend")
@click.option("--account", "-a", required=True)
@click.option("--followers", default=1000, show_default=True)
@click.option("--json-output", "json_out", is_flag=True, help="Print raw JSON")
@click.option("--update-roster", is_flag=True, help="Write learned_preferences back to roster")
def pulse_recommend(account, followers, json_out, update_roster):
    """Generate AI content recommendations based on performance data."""
    from sable.roster.manager import require_account
    from sable.pulse.recommender import generate_recommendations
    from sable.pulse.feedback import update_preferences_from_performance

    try:
        acc = require_account(account)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)

    with console.status("Generating recommendations with Claude..."):
        result = generate_recommendations(acc, followers=followers)

    if json_out:
        console.print_json(json.dumps(result))
        return

    console.rule(f"[bold]Recommendations — {acc.handle}[/bold]")
    console.print(f"\n[italic]{result.get('summary', '')}[/italic]\n")

    recs = result.get("recommendations", [])
    if recs:
        console.print("[bold]Recommendations:[/bold]")
        for r in recs:
            priority_color = {"high": "red", "medium": "yellow", "low": "green"}.get(r.get("priority", ""), "white")
            console.print(
                f"  [{priority_color}]{r.get('priority', '?').upper()}[/{priority_color}] "
                f"[{r.get('type', '?')}] {r.get('action', '')}"
            )
            console.print(f"  [dim]  → {r.get('rationale', '')}[/dim]")

    ideas = result.get("content_ideas", [])
    if ideas:
        console.print("\n[bold]Content ideas:[/bold]")
        for idea in ideas:
            console.print(f"  • {idea}")

    avoids = result.get("avoid", [])
    if avoids:
        console.print("\n[bold]Stop doing:[/bold]")
        for a in avoids:
            console.print(f"  ✗ {a}")

    if update_roster:
        prefs = update_preferences_from_performance(acc.handle, followers=followers)
        console.print(f"\n[green]✓ Updated learned_preferences in roster ({len(prefs)} keys)[/green]")


@pulse_group.command("export")
@click.option("--account", "-a", required=True)
@click.option("--format", "fmt", default="csv", type=click.Choice(["csv", "json"]))
@click.option("--output", "-o", required=True)
@click.option("--followers", default=1000)
def pulse_export(account, fmt, output, followers):
    """Export performance data to CSV or JSON."""
    from sable.pulse.exporter import export_csv, export_json

    handle = account if account.startswith("@") else f"@{account}"
    if fmt == "csv":
        export_csv(handle, output, followers=followers)
    else:
        export_json(handle, output, followers=followers)


@pulse_group.command("trends")
@click.option("--account", "-a", required=True)
@click.option("--query", "-q", default=None, help="Search query (uses account topics if omitted)")
@click.option("--count", default=10, show_default=True)
@click.option("--mock", is_flag=True)
def pulse_trends(account, query, count, mock):
    """Search trending content in an account's niche."""
    from sable.roster.manager import require_account
    from sable.pulse.trends import search_niche

    try:
        acc = require_account(account)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)

    search_query = query or " OR ".join(acc.persona.topics[:3]) or "crypto"

    with console.status(f"Searching: {search_query}"):
        tweets = search_niche(search_query, count=count, mock=mock)

    table = Table(box=box.SIMPLE, title=f"Trending: {search_query}")
    table.add_column("Author")
    table.add_column("Text")
    table.add_column("Likes", justify="right")
    table.add_column("RTs", justify="right")

    for t in tweets[:count]:
        user = t.get("user", {})
        table.add_row(
            f"@{user.get('screen_name', '?')}",
            t.get("full_text", "")[:60],
            f"{t.get('favorite_count', 0):,}",
            f"{t.get('retweet_count', 0):,}",
        )
    console.print(table)


@pulse_group.command("account")
@click.option("--account", "-a", required=True, help="Twitter handle")
@click.option("--days", default=30, show_default=True, help="Lookback window in days")
@click.option("--org", default=None, help="Org for niche comparison (defaults to roster org)")
def pulse_account(account, days, org):
    """Show per-format lift report for a managed account."""
    from sable.roster.manager import require_account
    from sable.shared.paths import pulse_db_path, meta_db_path
    from sable.pulse.account_report import compute_account_format_lift, render_account_report

    try:
        acc = require_account(account)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)

    effective_org = org or acc.org

    with console.status(f"Computing format lift for {acc.handle}..."):
        report = compute_account_format_lift(
            handle=acc.handle,
            org=effective_org,
            days=days,
            pulse_db_path=pulse_db_path(),
            meta_db_path=meta_db_path() if effective_org else None,
        )

    click.echo(render_account_report(report))


@pulse_group.command("link")
@click.option("--post-id", required=True)
@click.option("--type", "content_type", required=True, type=click.Choice(["clip", "meme", "faceswap", "text"]))
@click.option("--path", "content_path", required=True)
def pulse_link(post_id, content_type, content_path):
    """Manually link a tweet to a sable content item."""
    from sable.pulse.linker import manual_link
    manual_link(post_id, content_type, content_path)
    console.print(f"[green]✓ Linked {post_id} → {content_type}: {content_path}[/green]")
