"""Style delta report rendering."""
from __future__ import annotations

from rich.console import Console
from rich.table import Table


def render_delta_report(
    handle: str,
    org: str,
    delta: dict[str, float],
    managed_fp: dict[str, float],
    watchlist_fp: dict[str, float],
    console: Console | None = None,
) -> str:
    """Render a style delta report as a Rich table and return markdown summary."""
    if console is None:
        console = Console()

    table = Table(title=f"Style Delta — {handle} vs {org} watchlist")
    table.add_column("Metric")
    table.add_column("Managed", justify="right")
    table.add_column("Watchlist", justify="right")
    table.add_column("Gap", justify="right")

    for key in sorted(delta):
        m = managed_fp.get(key, 0.0)
        w = watchlist_fp.get(key, 0.0)
        gap = delta[key]
        gap_str = f"{gap:+.1%}" if abs(gap) > 0.001 else "—"
        table.add_row(
            key,
            f"{m:.1%}" if isinstance(m, float) else str(m),
            f"{w:.1%}" if isinstance(w, float) else str(w),
            gap_str,
        )

    console.print(table)

    # Markdown summary
    lines = [f"# Style Delta — {handle} vs {org} watchlist", ""]
    lines.append("| Metric | Managed | Watchlist | Gap |")
    lines.append("|--------|---------|-----------|-----|")
    for key in sorted(delta):
        m = managed_fp.get(key, 0.0)
        w = watchlist_fp.get(key, 0.0)
        gap = delta[key]
        lines.append(f"| {key} | {m:.1%} | {w:.1%} | {gap:+.1%} |")

    return "\n".join(lines)
