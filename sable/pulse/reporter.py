"""Rich terminal tables and markdown export for pulse reports."""
from __future__ import annotations

from typing import Optional

from rich.console import Console
from rich.table import Table
from rich import box

from sable.pulse.db import get_posts_for_account, get_latest_snapshot
from sable.pulse.scorer import score_post, rank_posts

console = Console()


def _get_scored_posts(handle: str, followers: int = 1000, limit: int = 50) -> list[dict]:
    posts = get_posts_for_account(handle, limit=limit)
    scored = []
    for post in posts:
        snap = get_latest_snapshot(post["id"])
        if not snap:
            continue
        scores = score_post(snap, followers=followers)
        scores["post_id"] = post["id"]
        scores["text"] = post.get("text", "")[:80]
        scores["posted_at"] = post.get("posted_at", "")[:10]
        scores["content_type"] = post.get("sable_content_type", "unknown")
        scored.append(scores)
    return scored


def render_report(
    handle: str,
    followers: int = 1000,
    limit: int = 50,
    sort_by: str = "engagement_rate",
) -> None:
    """Print a rich terminal performance table for an account."""
    handle = handle if handle.startswith("@") else f"@{handle}"
    scored = _get_scored_posts(handle, followers=followers, limit=limit)

    if not scored:
        console.print(f"[yellow]No performance data for {handle}. Run: sable pulse track --account {handle}[/yellow]")
        return

    ranked = rank_posts(scored, metric=sort_by)

    table = Table(
        title=f"Performance Report — {handle}",
        box=box.SIMPLE_HEAVY,
        show_header=True,
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("Date", width=10)
    table.add_column("Type", width=8)
    table.add_column("Text", width=50)
    table.add_column("Views", justify="right")
    table.add_column("ER%", justify="right")
    table.add_column("Viral‰", justify="right")
    table.add_column("Likes", justify="right")
    table.add_column("RTs", justify="right")
    table.add_column("%ile", justify="right")

    for post in ranked[:limit]:
        er = post.get("engagement_rate", 0)
        er_color = "green" if er > 2.0 else "yellow" if er > 0.5 else "red"
        table.add_row(
            str(post.get("rank", "?")),
            post.get("posted_at", "?")[:10],
            post.get("content_type", "?")[:8],
            post.get("text", "")[:50],
            f"{post.get('views', 0):,}",
            f"[{er_color}]{er:.2f}%[/{er_color}]",
            f"{post.get('virality_score', 0):.2f}",
            f"{post.get('likes', 0):,}",
            f"{post.get('retweets', 0):,}",
            f"{post.get('percentile', 0):.0f}",
        )

    console.print(table)
    console.print(f"\n[dim]{len(ranked)} posts analyzed.[/dim]")


def export_markdown(
    handle: str,
    output_path: str,
    followers: int = 1000,
    limit: int = 50,
) -> None:
    """Export report to markdown file."""
    handle = handle if handle.startswith("@") else f"@{handle}"
    scored = _get_scored_posts(handle, followers=followers, limit=limit)
    ranked = rank_posts(scored)

    lines = [
        f"# Pulse Report — {handle}",
        "",
        "| # | Date | Type | Text | Views | ER% | Viral‰ | Likes | RTs |",
        "|---|------|------|------|-------|-----|--------|-------|-----|",
    ]
    for post in ranked[:limit]:
        text = post.get("text", "").replace("|", "\\|")[:60]
        lines.append(
            f"| {post.get('rank')} "
            f"| {post.get('posted_at', '')[:10]} "
            f"| {post.get('content_type', '?')} "
            f"| {text} "
            f"| {post.get('views', 0):,} "
            f"| {post.get('engagement_rate', 0):.2f}% "
            f"| {post.get('virality_score', 0):.2f} "
            f"| {post.get('likes', 0):,} "
            f"| {post.get('retweets', 0):,} |"
        )

    with open(output_path, "w") as f:
        f.write("\n".join(lines) + "\n")
