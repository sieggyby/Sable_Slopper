"""CLI for sable lexicon — community vocabulary management."""
from __future__ import annotations

import sys

import click
from rich.console import Console

console = Console()


@click.group("lexicon")
def lexicon_group():
    """Community vocabulary extraction and management."""


@lexicon_group.command("scan")
@click.option("--org", required=True, help="Org to scan")
@click.option("--days", default=14, show_default=True, help="Look-back window in days")
@click.option("--top", "top_n", default=20, show_default=True, help="Max terms to extract")
@click.option("--no-interpret", "no_interpret", is_flag=True, default=False,
              help="Skip Claude classification (extraction only)")
@click.option("--dry-run", "dry_run", is_flag=True, default=False,
              help="Show corpus stats without scanning or writing")
def lexicon_scan(org, days, top_n, no_interpret, dry_run):
    """Scan watchlist tweets for community-specific vocabulary."""
    from sable.pulse.meta import db as meta_db
    from sable.lexicon.scanner import scan_lexicon, MIN_AUTHORS, MIN_TWEETS

    meta_db.migrate()
    conn = meta_db.get_conn()

    if dry_run:
        from datetime import datetime, timedelta, timezone
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        rows = conn.execute(
            """SELECT COUNT(*) as cnt, COUNT(DISTINCT author_handle) as authors
               FROM scanned_tweets WHERE org = ? AND posted_at >= ?""",
            (org, cutoff),
        ).fetchone()
        tweet_count = rows["cnt"]
        author_count = rows["authors"]
        meets_thresh = tweet_count >= MIN_TWEETS and author_count >= MIN_AUTHORS
        claude_calls = 0 if no_interpret else (1 if meets_thresh else 0)
        console.print(f"[bold]Dry run — corpus stats for {org}[/bold]")
        console.print(f"  Tweets: {tweet_count} (min {MIN_TWEETS})")
        console.print(f"  Authors: {author_count} (min {MIN_AUTHORS})")
        console.print(f"  Thresholds met: {'yes' if meets_thresh else 'no'}")
        console.print(f"  Estimated Claude calls: {claude_calls}")
        return

    terms = scan_lexicon(org=org, days=days, top_n=top_n, conn=conn)
    if not terms:
        console.print(
            f"[yellow]Insufficient data for org '{org}' — need ≥{MIN_AUTHORS} authors "
            f"and ≥{MIN_TWEETS} tweets in the last {days} days.[/yellow]"
        )
        return

    # Optionally interpret via Claude
    if not no_interpret:
        from sable.lexicon.writer import interpret_terms
        from sable.platform.errors import SableError
        try:
            terms = interpret_terms(terms, org)
        except SableError as e:
            console.print(f"[red]Error [{e.code}]: {e.message}[/red]", err=True)
            sys.exit(1)

    # Save to DB
    from sable.lexicon.store import upsert_term
    for t in terms:
        upsert_term(conn, org, t["term"],
                     category=t.get("category"),
                     gloss=t.get("gloss"),
                     lsr=t.get("lsr"))

    # Write vault report
    from sable.shared.paths import vault_dir
    from sable.lexicon.writer import render_report
    vpath = vault_dir(org)
    if vpath.exists():
        report_path = render_report(terms, org, vpath)
        console.print(f"[dim]Report: {report_path}[/dim]")

    console.print(f"[green]✓[/green] {len(terms)} terms extracted for {org}")
    for t in terms[:10]:
        cat = t.get("category", "")
        gloss = t.get("gloss", "")
        cat_str = f" [{cat}]" if cat else ""
        gloss_str = f" — {gloss}" if gloss else ""
        console.print(f"  {t['term']}{cat_str}{gloss_str}  (LSR: {t['lsr']:.3f})")


@lexicon_group.command("list")
@click.option("--org", required=True, help="Org to list")
def lexicon_list(org):
    """List stored lexicon terms for an org."""
    from sable.pulse.meta import db as meta_db
    from sable.lexicon.store import list_terms

    meta_db.migrate()
    conn = meta_db.get_conn()
    terms = list_terms(org, conn)

    if not terms:
        console.print(f"[dim]No lexicon terms for '{org}'. Run: sable lexicon scan --org {org}[/dim]")
        return

    from rich.table import Table
    table = Table(title=f"Lexicon — {org}")
    table.add_column("Term")
    table.add_column("Category")
    table.add_column("Gloss")
    table.add_column("LSR", justify="right")
    for t in terms:
        table.add_row(t["term"], t.get("category") or "", t.get("gloss") or "",
                       f"{t['lsr']:.3f}" if t.get("lsr") else "")
    console.print(table)


@lexicon_group.command("add")
@click.option("--org", required=True, help="Org to add to")
@click.option("--term", required=True, help="Term to add")
@click.option("--gloss", default="", help="Definition/explanation")
def lexicon_add(org, term, gloss):
    """Manually add a term to the lexicon."""
    from sable.pulse.meta import db as meta_db
    from sable.lexicon.store import add_manual_term

    meta_db.migrate()
    conn = meta_db.get_conn()
    add_manual_term(conn, org, term, gloss)
    console.print(f"[green]✓[/green] Added '{term}' to {org} lexicon")


@lexicon_group.command("remove")
@click.argument("term")
@click.option("--org", required=True, help="Org to remove from")
def lexicon_remove(term, org):
    """Remove a term from the lexicon."""
    from sable.pulse.meta import db as meta_db
    from sable.lexicon.store import remove_term

    meta_db.migrate()
    conn = meta_db.get_conn()
    removed = remove_term(conn, org, term)
    if removed:
        console.print(f"[green]✓[/green] Removed '{term}'")
    else:
        console.print(f"[yellow]'{term}' not found in {org} lexicon[/yellow]")
