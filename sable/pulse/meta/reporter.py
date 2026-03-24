"""Terminal three-pane output and vault markdown report."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from rich.text import Text

from sable.pulse.meta.trends import TrendResult
from sable.pulse.meta.topics import TopicSignal
from sable.pulse.meta.recommender import PostNowRecommendation

console = Console()

_STATUS_COLOR = {
    "surging": "bold green",
    "rising": "green",
    "stable": "yellow",
    "declining": "red",
    "dead": "bold red",
}
_CONFIDENCE_COLOR = {"A": "green", "B": "yellow", "C": "dim"}
_MOMENTUM_SYMBOL = {
    "accelerating": "↑↑",
    "plateauing": "→",
    "decelerating": "↓",
}


def render_report(
    org: str,
    trends: dict[str, TrendResult],
    topic_signals: list[TopicSignal],
    recommendations: dict,
    analysis: dict,
    baseline_days: int,
    min_baseline_days: int = 5,
    scan_info: dict | None = None,
) -> None:
    """Render the full three-pane terminal report."""
    scan_info = scan_info or {}

    console.print()
    console.rule(f"[bold]Sable Pulse Meta — {org.upper()}[/bold]")

    # Bootstrapping header
    if baseline_days < min_baseline_days:
        remaining = min_baseline_days - baseline_days
        console.print(
            f"\n[yellow]⚠  Building baseline — {remaining} more scan(s) needed before trend labels appear.[/yellow]"
        )
        console.print(
            f"   ({baseline_days} days of data so far, need {min_baseline_days})\n"
        )

    # Scan metadata
    if scan_info:
        console.print(
            f"[dim]Scan: {scan_info.get('tweets_collected', 0)} tweets collected, "
            f"{scan_info.get('tweets_new', 0)} new | "
            f"Watchlist: {scan_info.get('watchlist_size', 0)} accounts[/dim]"
        )

    console.print()

    # --- Format Trends overview ---
    _render_format_trends(trends, baseline_days, min_baseline_days)

    # --- Topic signals ---
    if topic_signals:
        _render_topics(topic_signals, analysis)

    # --- Three panes ---
    post_now = recommendations.get("post_now", [])
    stop_doing = recommendations.get("stop_doing", [])
    gaps = recommendations.get("gaps_to_fill", [])

    _render_post_now(post_now)
    _render_stop_doing(stop_doing)
    _render_gaps(gaps)

    # --- Active limitations ---
    _render_limitations(trends, baseline_days, min_baseline_days)

    # --- Claude meta summary ---
    meta = analysis.get("meta_summary")
    if meta:
        console.print()
        console.print(Panel(meta, title="[bold]Strategist Brief[/bold]", border_style="cyan"))


def _render_format_trends(
    trends: dict[str, TrendResult],
    baseline_days: int,
    min_baseline_days: int,
) -> None:
    table = Table(
        title="Format Performance",
        box=box.SIMPLE,
        show_header=True,
    )
    table.add_column("Format", style="bold", min_width=16)
    table.add_column("Lift", justify="right", min_width=7)
    table.add_column("vs 30d", justify="right", min_width=7)
    table.add_column("Trend", min_width=10)
    table.add_column("Conf", justify="center", min_width=5)
    table.add_column("Authors", justify="right", min_width=7)
    table.add_column("Samples", justify="right", min_width=7)
    table.add_column("Notes")

    for bucket, trend in sorted(trends.items(), key=lambda kv: kv[1].current_lift, reverse=True):
        lift_str = f"{trend.current_lift:.2f}x"
        vs30_str = f"{trend.lift_vs_30d:.2f}x" if trend.lift_vs_30d else "—"

        if trend.trend_status and baseline_days >= min_baseline_days:
            status_color = _STATUS_COLOR.get(trend.trend_status, "white")
            momentum_sym = _MOMENTUM_SYMBOL.get(trend.momentum or "", "")
            trend_cell = f"[{status_color}]{trend.trend_status}[/{status_color}] {momentum_sym}"
        elif baseline_days < min_baseline_days:
            trend_cell = "[dim]building…[/dim]"
        else:
            trend_cell = f"[dim]gates: {', '.join(trend.gate_failures[:1])}[/dim]"

        conf_color = _CONFIDENCE_COLOR.get(trend.confidence, "white")
        conf_cell = f"[{conf_color}]{trend.confidence}[/{conf_color}]"

        # Concentration warning
        notes = []
        if trend.quality.concentration > 0.50:
            notes.append(f"conc {trend.quality.concentration:.0%}")
        if trend.quality.mixed_quality_warning:
            notes.append("⚠ history")
        if trend.quality.all_fallback:
            notes.append("fallback-only")

        table.add_row(
            bucket,
            lift_str,
            vs30_str,
            trend_cell,
            # INVARIANT: confidence grade + unique author count on same line
            conf_cell,
            str(trend.quality.unique_authors),
            str(trend.quality.sample_count),
            ", ".join(notes) if notes else "",
        )

    console.print(table)


def _render_topics(topics: list[TopicSignal], analysis: dict) -> None:
    cat = analysis.get("topic_categorization", {})
    hot = set(cat.get("hot", []))
    rising = set(cat.get("rising", []))
    emerging = set(cat.get("emerging", []))
    topic_conf = analysis.get("topic_confidence", "")

    table = Table(
        title=f"Topic Signals{' [confidence: ' + topic_conf + ']' if topic_conf else ''}",
        box=box.SIMPLE,
    )
    table.add_column("Term", min_width=20)
    table.add_column("Mentions", justify="right")
    table.add_column("Authors", justify="right")
    table.add_column("Avg Lift", justify="right")
    table.add_column("Category")

    for sig in topics[:15]:
        if sig.term in hot:
            cat_cell = "[bold green]hot[/bold green]"
        elif sig.term in rising:
            cat_cell = "[green]rising[/green]"
        elif sig.term in emerging:
            cat_cell = "[yellow]emerging[/yellow]"
        else:
            cat_cell = ""

        table.add_row(
            sig.term,
            str(sig.mention_count),
            str(sig.unique_authors),
            f"{sig.avg_lift:.2f}x",
            cat_cell,
        )

    console.print(table)


def _render_post_now(recs: list[PostNowRecommendation]) -> None:
    console.print()
    console.print("[bold green]━━━ PANE 1: POST NOW ━━━[/bold green]")

    if not recs:
        console.print("[dim]  No high-confidence post opportunities identified.[/dim]")
        return

    for i, rec in enumerate(recs[:10], 1):
        conf_color = _CONFIDENCE_COLOR.get(rec.confidence, "white")
        console.print(
            f"  [bold]{i}.[/bold] [{conf_color}]{rec.confidence}[/{conf_color}] "
            f"[bold]{rec.title}[/bold]"
        )
        console.print(f"     Account: {rec.account} | Format: {rec.archetype} | "
                      f"Urgency: {rec.urgency} | Effort: {rec.effort}")
        console.print(f"     [dim]{rec.reason}[/dim]")
        if rec.file_path:
            console.print(f"     [dim]File: {rec.file_path}[/dim]")
        console.print()


def _render_stop_doing(stops: list[dict]) -> None:
    console.print("[bold red]━━━ PANE 2: STOP DOING ━━━[/bold red]")

    if not stops:
        console.print("[dim]  No clearly declining formats identified.[/dim]")
        return

    for s in stops:
        conf_color = _CONFIDENCE_COLOR.get(s["confidence"], "white")
        console.print(
            f"  ✗ [{conf_color}]{s['confidence']}[/{conf_color}] "
            f"[bold]{s['format']}[/bold] — {s['evidence']}"
        )
        if s.get("confidence_reasons"):
            console.print(f"    [dim]{' | '.join(s['confidence_reasons'][:2])}[/dim]")
    console.print()


def _render_gaps(gaps: list[dict]) -> None:
    console.print("[bold yellow]━━━ PANE 3: GAPS TO FILL ━━━[/bold yellow]")

    if not gaps:
        console.print("[dim]  No content gaps detected (vault covers active formats).[/dim]")
        return

    for g in gaps:
        urgency_color = "red" if g["urgency"] == "high" else "yellow"
        # INVARIANT: always specify what content type needs to be produced
        console.print(
            f"  → [{urgency_color}]{g['urgency'].upper()}[/{urgency_color}] "
            f"[bold]{g['format']}[/bold] is {g['trend_status']} "
            f"({g['lift']:.2f}x, conf {g['confidence']}) — "
            f"need: [italic]{g['content_type']}[/italic] | effort: {g['effort']}"
        )
    console.print()


def _render_limitations(
    trends: dict[str, TrendResult],
    baseline_days: int,
    min_baseline_days: int,
) -> None:
    """Render active limitations. INVARIANT: always visible in terminal when affecting results."""
    limitations: list[str] = []

    if baseline_days < min_baseline_days:
        limitations.append(
            f"Baseline: only {baseline_days} days of data — "
            f"trend labels suppressed until {min_baseline_days} days."
        )

    for bucket, trend in trends.items():
        if trend.quality.concentration > 0.50:
            limitations.append(
                f"{bucket}: concentrated signal (top 2 authors = "
                f"{trend.quality.concentration:.0%} of lift from {trend.quality.unique_authors} authors)."
            )
        if trend.quality.all_fallback and trend.quality.sample_count >= 4:
            limitations.append(
                f"{bucket}: all contributing authors have limited history — "
                "confidence capped at B."
            )
        if trend.quality.mixed_quality_warning:
            limitations.append(f"{bucket}: {trend.quality.mixed_quality_warning}")

    if limitations:
        console.print()
        console.print("[bold dim]Active Limitations:[/bold dim]")
        for lim in limitations:
            console.print(f"  [dim]⚠  {lim}[/dim]")


# ---------------------------------------------------------------------------
# Vault markdown output
# ---------------------------------------------------------------------------

def write_vault_report(
    org: str,
    vault_path: Path,
    trends: dict[str, TrendResult],
    topic_signals: list[TopicSignal],
    recommendations: dict,
    analysis: dict,
    scan_date: str | None = None,
    degraded: bool = False,
) -> Path:
    """Write markdown report to vault."""
    date_str = scan_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    report_dir = vault_path / "pulse"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"{date_str}.md"

    degraded_str = "true" if degraded else "false"
    lines: list[str] = [
        "---",
        f"date: {date_str}",
        f"org: {org}",
        "type: pulse_meta_report",
        f"degraded: {degraded_str}",
        "---",
        "",
    ]

    if degraded:
        lines += ["> ⚠ Fallback analysis — Claude unavailable", "", ""]

    lines += [
        f"# Sable Pulse Meta — {org.upper()} — {date_str}",
        "",
    ]

    # Meta summary
    meta = analysis.get("meta_summary", "")
    if meta:
        lines += ["## Strategist Brief", "", meta, ""]

    # Format trends
    lines += ["## Format Performance", ""]
    lines += ["| Format | Lift | vs 30d | Trend | Conf | Authors | Samples |", "|---|---|---|---|---|---|---|"]
    for bucket, trend in sorted(trends.items(), key=lambda kv: kv[1].current_lift, reverse=True):
        vs30 = f"{trend.lift_vs_30d:.2f}x" if trend.lift_vs_30d else "—"
        status = trend.trend_status or "gates not met"
        lines.append(
            f"| {bucket} | {trend.current_lift:.2f}x | {vs30} | {status} | "
            f"{trend.confidence} | {trend.quality.unique_authors} | {trend.quality.sample_count} |"
        )
    lines.append("")

    # Topic signals
    if topic_signals:
        lines += ["## Topic Signals", ""]
        for sig in topic_signals[:20]:
            lines.append(f"- **{sig.term}** — {sig.mention_count} mentions, {sig.unique_authors} authors, {sig.avg_lift:.2f}x avg lift")
        lines.append("")

    # Post now
    post_now = recommendations.get("post_now", [])
    if post_now:
        lines += ["## Post Now", ""]
        for i, rec in enumerate(post_now[:10], 1):
            lines.append(f"{i}. **{rec.title}** — {rec.account} | {rec.archetype} | {rec.reason}")
        lines.append("")

    # Stop doing
    stop_doing = recommendations.get("stop_doing", [])
    if stop_doing:
        lines += ["## Stop Doing", ""]
        for s in stop_doing:
            lines.append(f"- **{s['format']}** ({s['confidence']}) — {s['evidence']}")
        lines.append("")

    # Gaps
    gaps = recommendations.get("gaps_to_fill", [])
    if gaps:
        lines += ["## Gaps to Fill", ""]
        for g in gaps:
            lines.append(
                f"- **{g['format']}** ({g['urgency']} urgency) — need {g['content_type']} | effort: {g['effort']}"
            )
        lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path
