"""sable vault — content catalog, search engine, and client knowledge base CLI."""
from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich import box

console = Console()
err_console = Console(stderr=True)


def _resolve_vault(org: str, vault_override: str | None = None) -> Path:
    """Resolve vault path for an org."""
    if vault_override:
        p = Path(vault_override).expanduser()
        p.mkdir(parents=True, exist_ok=True)
        return p
    from sable.shared.paths import vault_dir
    return vault_dir(org)


def _resolve_workspace(workspace_override: str | None = None) -> Path:
    if workspace_override:
        return Path(workspace_override).expanduser()
    from sable.shared.paths import workspace
    return workspace()


# ---------------------------------------------------------------------------
# Vault group
# ---------------------------------------------------------------------------

@click.group("vault")
def vault_group():
    """Content catalog, search engine, and client knowledge base."""


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------

@vault_group.command("init")
@click.option("--org", required=True, help="Client org name")
@click.option("--vault", default=None, help="Override vault path")
def vault_init(org, vault):
    """Initialize a vault for an org."""
    from sable.vault.init import init_vault

    vault_path = _resolve_vault(org, vault)
    console.print(f"[bold]Initializing vault:[/bold] {vault_path}")

    with console.status("Creating vault structure..."):
        init_vault(org, vault_path)

    console.print(f"[green]✓ Vault initialized:[/green] {vault_path}")
    console.print(f"  Run [cyan]sable vault sync --org {org}[/cyan] to index existing content.")


# ---------------------------------------------------------------------------
# sync
# ---------------------------------------------------------------------------

@vault_group.command("sync")
@click.argument("org_id", required=False, default=None)
@click.option("--org", default=None)
@click.option("--workspace", "workspace_override", default=None)
@click.option("--vault", default=None)
@click.option("--dry-run", is_flag=True)
def vault_sync(org_id, org, workspace_override, vault, dry_run):
    """Scan workspace for content meta files and index into vault.

    When ORG_ID is provided as a positional argument, regenerates the
    platform vault from sable.db (template-based, no AI calls).
    When --org is used, scans workspace meta files (legacy sync).
    """
    if org_id and not org:
        # New platform vault sync
        from sable.vault.platform_sync import platform_vault_sync
        from sable.platform.errors import SableError
        try:
            stats = platform_vault_sync(org_id)
            console.print(
                f"[green]✓ Vault synced:[/green] "
                f"{stats.get('entities_written', 0)} entities, "
                f"{stats.get('diagnostics_written', 0)} diagnostics"
            )
        except SableError as e:
            from sable.platform.errors import redact_error
            err_console.print(f"[red]{redact_error(str(e))}[/red]")
            sys.exit(1)
        return

    # Legacy meta.json sync
    if not org:
        err_console.print("[red]Provide ORG_ID as argument or --org flag[/red]")
        sys.exit(1)

    from sable.vault.sync import sync
    from sable.vault.config import load_vault_config

    vault_path = _resolve_vault(org, vault)
    workspace_path = _resolve_workspace(workspace_override)
    config = load_vault_config()

    if dry_run:
        console.print("[yellow](dry run — no files will be written)[/yellow]")

    with console.status(f"Scanning {workspace_path}..."):
        report = sync(org, vault_path, workspace_path, config, dry_run=dry_run)

    if dry_run:
        console.print(f"Would sync: {report}")
    else:
        console.print(f"[green]✓ Synced:[/green] new={report.new}, updated={report.updated}", end="")
        if report.errors:
            console.print(f", [red]errors={len(report.errors)}[/red]")
            from sable.platform.errors import redact_error
            for err in report.errors[:5]:
                console.print(f"  [red]{redact_error(str(err))}[/red]")
        else:
            console.print()


# ---------------------------------------------------------------------------
# enrich
# ---------------------------------------------------------------------------

@vault_group.command("enrich")
@click.option("--org", required=True)
@click.option("--vault", default=None)
def vault_enrich(org, vault):
    """Re-run enrichment on pending content notes."""
    from sable.vault.notes import load_all_notes, read_note, write_note
    from sable.vault.enrich import enrich_batch
    from sable.vault.topics import refresh_topics
    from sable.vault.config import load_vault_config
    from sable.vault.sync import _get_org_topics

    vault_path = _resolve_vault(org, vault)
    config = load_vault_config()

    all_notes = load_all_notes(vault_path)
    pending = [n for n in all_notes if n.get("enrichment_status") == "pending"]

    if not pending:
        console.print("[green]✓ No pending notes to enrich.[/green]")
        return

    console.print(f"Found {len(pending)} pending notes.")
    org_topics = _get_org_topics(org)

    with console.status(f"Enriching {len(pending)} notes..."):
        enriched = enrich_batch(pending, org_topics, config, org=org)

    # Write enrichment fields back to each note
    content_dir = vault_path / "content"
    ok = 0
    for ef in enriched:
        for md in content_dir.rglob("*.md"):
            if md.stem == ef.get("id", ""):
                fm, body = read_note(md)
                for key in ("topics", "questions_answered", "depth", "tone", "keywords", "enrichment_status"):
                    if key in ef:
                        fm[key] = ef[key]
                write_note(md, fm, body)
                ok += 1
                break

    console.print(f"[green]✓ Enriched {ok} notes.[/green]")

    with console.status("Refreshing topics..."):
        try:
            refresh_topics(org, vault_path)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

@vault_group.command("status")
@click.option("--org", required=True)
@click.option("--vault", default=None)
def vault_status(org, vault):
    """Show vault inventory summary."""
    from sable.vault.notes import load_all_notes
    from sable.roster.manager import list_accounts

    vault_path = _resolve_vault(org, vault)
    notes = load_all_notes(vault_path)

    # Counts by type
    counts: dict[str, int] = {}
    posted: dict[str, int] = {}
    for n in notes:
        t = n.get("type", "unknown")
        counts[t] = counts.get(t, 0) + 1
        if n.get("posted_by"):
            posted[t] = posted.get(t, 0) + 1

    table = Table(box=box.SIMPLE_HEAVY, title=f"Vault: {org}")
    table.add_column("Type", style="cyan")
    table.add_column("Total", justify="right")
    table.add_column("Posted", justify="right")
    table.add_column("Available", justify="right")
    for t in sorted(counts):
        total = counts[t]
        p = posted.get(t, 0)
        table.add_row(t, str(total), str(p), str(total - p))
    table.add_row("[bold]TOTAL[/bold]", str(sum(counts.values())),
                  str(sum(posted.values())),
                  str(sum(counts.values()) - sum(posted.values())), end_section=True)
    console.print(table)

    # Per-account breakdown
    acc_map: dict[str, dict] = {}
    for n in notes:
        h = n.get("account", "")
        if not h:
            continue
        if h not in acc_map:
            acc_map[h] = {"handle": h, "total": 0, "posted": 0}
        acc_map[h]["total"] += 1
        if n.get("posted_by"):
            acc_map[h]["posted"] += 1

    if acc_map:
        acc_table = Table(box=box.SIMPLE, title="By Account")
        acc_table.add_column("Account", style="cyan")
        acc_table.add_column("Total", justify="right")
        acc_table.add_column("Posted", justify="right")
        for h, stats in sorted(acc_map.items()):
            acc_table.add_row(h, str(stats["total"]), str(stats["posted"]))
        console.print(acc_table)


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------

@vault_group.command("search")
@click.argument("query")
@click.option("--org", required=True)
@click.option("--vault", default=None)
@click.option("--depth", default=None, type=click.Choice(["intro", "intermediate", "advanced"]))
@click.option("--type", "content_type", default=None, type=click.Choice(["clip", "meme", "faceswap", "explainer"]))
@click.option("--available-for", default=None, help="Only show content not yet posted by this account")
@click.option("--reply-to", default=None, help="Tweet text context for reply suggestions")
@click.option("--format", "format_bucket", default=None, help="Filter by format field (e.g. short_clip)")
def vault_search(query, org, vault, depth, content_type, available_for, reply_to, format_bucket):
    """Search vault content by relevance."""
    from sable.vault.search import search_vault, SearchFilters
    from sable.vault.config import load_vault_config

    vault_path = _resolve_vault(org, vault)
    config = load_vault_config()
    filters = SearchFilters(
        depth=depth,
        content_type=content_type,
        format=format_bucket,
        available_for=available_for,
        reply_context=reply_to,
    )

    with console.status("Searching vault..."):
        results = search_vault(query, vault_path, org, filters=filters, config=config)

    if not results:
        console.print("[yellow]No results found.[/yellow]")
        return

    table = Table(box=box.SIMPLE_HEAVY)
    table.add_column("#", style="dim", width=3)
    table.add_column("ID", style="cyan")
    table.add_column("Type")
    table.add_column("Account")
    table.add_column("Score", justify="right")
    table.add_column("Reason")

    for i, r in enumerate(results, 1):
        table.add_row(
            str(i),
            r.id,
            r.note.get("type", ""),
            r.note.get("account", ""),
            str(r.score),
            r.reason[:60],
        )
    console.print(table)


# ---------------------------------------------------------------------------
# suggest
# ---------------------------------------------------------------------------

@vault_group.command("suggest")
@click.option("--org", required=True)
@click.option("--vault", default=None)
@click.option("--tweet-text", default=None)
@click.option("--tweet-url", default=None)
@click.option("--account", default=None, help="Filter suggestions for this account")
def vault_suggest(org, vault, tweet_text, tweet_url, account):
    """Suggest vault content to reply to a tweet."""
    from sable.vault.suggest import suggest_replies, fetch_tweet_text
    from sable.vault.config import load_vault_config

    if not tweet_text and not tweet_url:
        console.print("[red]Provide --tweet-text or --tweet-url[/red]")
        sys.exit(1)

    vault_path = _resolve_vault(org, vault)
    config = load_vault_config()

    if tweet_url and not tweet_text:
        with console.status("Fetching tweet..."):
            try:
                tweet_text = fetch_tweet_text(tweet_url)
            except Exception as e:
                from sable.platform.errors import redact_error
                console.print(f"[red]Failed to fetch tweet: {redact_error(str(e))}[/red]")
                sys.exit(1)

    console.print(f"[dim]Tweet:[/dim] {tweet_text[:120]}")

    with console.status("Finding reply suggestions..."):
        suggestions = suggest_replies(tweet_text, org, account, vault_path, config)

    if not suggestions:
        console.print("[yellow]No suggestions found.[/yellow]")
        return

    for i, s in enumerate(suggestions, 1):
        console.print(f"\n[bold cyan]{i}. {s.content_id}[/bold cyan] — {s.content_type} | {s.account} | score={s.relevance_score}")
        console.print(f"   [dim]{s.relevance_reason}[/dim]")
        if s.reply_draft:
            console.print(f"   [green]Draft:[/green] {s.reply_draft}")
        if s.content_path:
            console.print(f"   [dim]Media:[/dim] {s.content_path}")

    # Interactive selection
    if sys.stdin.isatty():
        choice = click.prompt("\nSelect suggestion (number) or press Enter to skip", default="")
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(suggestions):
                s = suggestions[idx]
                console.print(f"\n[bold]Selected:[/bold] {s.content_id}")
                console.print(f"[bold]Draft:[/bold] {s.reply_draft}")
                console.print(f"[bold]Media:[/bold] {s.content_path}")


# ---------------------------------------------------------------------------
# log
# ---------------------------------------------------------------------------

@vault_group.command("log")
@click.argument("content_id", required=False)
@click.option("--account", default=None)
@click.option("--tweet-id", default=None)
@click.option("--org", default=None)
@click.option("--vault", default=None)
@click.option("--sync-from-pulse", "do_pulse_sync", is_flag=True, help="Sync posts from pulse DB")
@click.option("--bulk", "bulk_csv", default=None, help="Path to CSV (columns: content_id,account,tweet_id)")
def vault_log(content_id, account, tweet_id, org, vault, do_pulse_sync, bulk_csv):
    """Log a posted piece of content, or sync from pulse DB."""
    if bulk_csv:
        if not org:
            console.print("[red]--org required with --bulk[/red]")
            sys.exit(1)
        import csv
        from sable.vault.log import log_post
        vault_path = _resolve_vault(org, vault)
        ok_count = 0
        fail_count = 0
        with open(bulk_csv, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                cid = row.get("content_id", "").strip()
                acc = row.get("account", "").strip()
                tid = row.get("tweet_id", "").strip()
                if not all([cid, acc, tid]):
                    console.print(f"[yellow]Skipping incomplete row: {row}[/yellow]")
                    fail_count += 1
                    continue
                if log_post(cid, acc, tid, vault_path, org):
                    ok_count += 1
                else:
                    console.print(f"[red]Not found: {cid}[/red]")
                    fail_count += 1
        console.print(f"[green]✓ Logged {ok_count} posts.[/green]" + (f" [red]{fail_count} failed.[/red]" if fail_count else ""))
        return

    if do_pulse_sync:
        if not org:
            console.print("[red]--org required with --sync-from-pulse[/red]")
            sys.exit(1)
        from sable.vault.log import sync_from_pulse, log_post
        vault_path = _resolve_vault(org, vault)
        with console.status("Checking pulse DB..."):
            unlogged = sync_from_pulse(org, vault_path)
        if not unlogged:
            console.print("[green]✓ All pulse posts already logged.[/green]")
            return
        console.print(f"Found {len(unlogged)} unlogged posts:")
        for i, entry in enumerate(unlogged, 1):
            console.print(f"  {i}. {entry['account']} — {entry.get('content_type', '?')} — {entry['tweet_id']}")
        if click.confirm("Log these entries?", default=True):
            for entry in unlogged:
                # Try to find matching note by content path
                log_post(
                    entry.get("content_path", entry["tweet_id"]),
                    entry["account"],
                    entry["tweet_id"],
                    vault_path,
                    org,
                )
            console.print(f"[green]✓ Logged {len(unlogged)} posts.[/green]")
        return

    # Manual log
    if not all([content_id, account, tweet_id, org]):
        console.print("[red]Required: CONTENT_ID --account HANDLE --tweet-id ID --org ORG[/red]")
        sys.exit(1)

    from sable.vault.log import log_post
    vault_path = _resolve_vault(org, vault)

    ok = log_post(content_id, account, tweet_id, vault_path, org)
    if ok:
        console.print(f"[green]✓ Logged:[/green] {content_id} posted as {tweet_id} by {account}")
    else:
        console.print(f"[red]Content note not found: {content_id}[/red]")
        sys.exit(1)


# ---------------------------------------------------------------------------
# assign
# ---------------------------------------------------------------------------

@vault_group.command("assign")
@click.argument("content_id")
@click.option("--account", required=True)
@click.option("--caption", default=None)
@click.option("--org", required=True)
@click.option("--vault", default=None)
def vault_assign(content_id, account, caption, org, vault):
    """Assign content to an account's queue."""
    from sable.vault.assign import assign_content

    vault_path = _resolve_vault(org, vault)
    ok = assign_content(content_id, account, caption, vault_path)
    if ok:
        console.print(f"[green]✓ Assigned[/green] {content_id} → {account}")
        if caption:
            console.print("  Caption added to tweet bank.")
    else:
        console.print(f"[red]Content note not found: {content_id}[/red]")
        sys.exit(1)


# ---------------------------------------------------------------------------
# gaps
# ---------------------------------------------------------------------------

@vault_group.command("gaps")
@click.option("--org", required=True)
@click.option("--vault", default=None)
def vault_gaps(org, vault):
    """Show content coverage gaps per topic and depth level."""
    from sable.vault.gaps import analyze_gaps

    vault_path = _resolve_vault(org, vault)
    gaps = analyze_gaps(org, vault_path)

    if not gaps:
        console.print(f"[yellow]No topics found. Run `sable vault init --org {org}` first.[/yellow]")
        return

    table = Table(box=box.SIMPLE_HEAVY, title=f"Coverage Gaps — {org}")
    table.add_column("Topic", style="cyan")
    table.add_column("Total", justify="right")
    table.add_column("Intro", justify="right")
    table.add_column("Intermediate", justify="right")
    table.add_column("Advanced", justify="right")
    table.add_column("FAQ Gaps", justify="right")

    for g in sorted(gaps, key=lambda x: x["total_content"]):
        depths = g["depths"]
        intro = len(depths.get("intro", []))
        inter = len(depths.get("intermediate", []))
        adv = len(depths.get("advanced", []))
        faq = len(g.get("faq_gaps", []))
        table.add_row(
            g["display_name"],
            str(g["total_content"]),
            str(intro) if intro else "[red][ ][/red]",
            str(inter) if inter else "[red][ ][/red]",
            str(adv) if adv else "[yellow][ ][/yellow]",
            str(faq) if faq else "—",
        )

    console.print(table)


# ---------------------------------------------------------------------------
# niche-gaps
# ---------------------------------------------------------------------------

@vault_group.command("niche-gaps")
@click.option("--org", required=True)
@click.option("--vault", default=None)
@click.option("--top", default=10, show_default=True)
@click.option("--min-authors", default=2, show_default=True)
@click.option("--json", "as_json", is_flag=True)
def vault_niche_gaps(org, vault, top, min_authors, as_json):
    """Show niche-trending topics with no vault coverage (requires meta scan data)."""
    from sable.vault.gaps import compute_signal_gaps, render_signal_gaps
    import json as json_mod

    vault_path = _resolve_vault(org, vault) if vault else None
    gaps = compute_signal_gaps(org, vault_path=vault_path, top_n=top, min_unique_authors=min_authors)
    if as_json:
        import dataclasses
        click.echo(json_mod.dumps([dataclasses.asdict(g) for g in gaps], indent=2))
    else:
        click.echo(render_signal_gaps(gaps, org))


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------

@vault_group.command("export")
@click.option("--org", required=True)
@click.option("--vault", default=None)
@click.option("--output", "-o", default=None, help="Output zip path")
@click.option("--include-media", is_flag=True, help="Bundle media files into zip")
def vault_export(org, vault, output, include_media):
    """Export vault as a client-ready zip."""
    from sable.vault.export import export_vault
    import time

    vault_path = _resolve_vault(org, vault)

    if output is None:
        output = str(Path.home() / "Desktop" / f"{org}-vault-{int(time.time())}.zip")

    output_path = Path(output)

    with console.status(f"Exporting {org} vault..."):
        zip_path = export_vault(org, vault_path, output_path, include_media=include_media)

    size_mb = zip_path.stat().st_size / 1024 / 1024
    console.print(f"[green]✓ Exported:[/green] {zip_path} ({size_mb:.1f} MB)")


# ---------------------------------------------------------------------------
# topic subgroup
# ---------------------------------------------------------------------------

@vault_group.group("topic")
def topic_group():
    """Manage topic hub pages."""


@topic_group.command("add")
@click.argument("slug")
@click.option("--display-name", required=True)
@click.option("--org", required=True)
@click.option("--vault", default=None)
def topic_add(slug, display_name, org, vault):
    """Add a new topic hub page."""
    from sable.vault.topics import add_topic
    vault_path = _resolve_vault(org, vault)
    path = add_topic(slug, display_name, org, vault_path)
    console.print(f"[green]✓ Topic created:[/green] {path}")


@topic_group.command("list")
@click.option("--org", required=True)
@click.option("--vault", default=None)
def topic_list(org, vault):
    """List all topic hubs."""
    from sable.vault.topics import list_topics
    vault_path = _resolve_vault(org, vault)
    topics = list_topics(vault_path)
    if not topics:
        console.print("[yellow]No topics found.[/yellow]")
        return
    table = Table(box=box.SIMPLE)
    table.add_column("Slug", style="cyan")
    table.add_column("Display Name")
    table.add_column("Content", justify="right")
    for t in sorted(topics, key=lambda x: x.get("slug", "")):
        table.add_row(
            t.get("slug", ""),
            t.get("display_name", ""),
            str(t.get("content_count", 0)),
        )
    console.print(table)


@topic_group.command("refresh")
@click.option("--org", required=True)
@click.option("--vault", default=None)
def topic_refresh(org, vault):
    """Refresh topic→content links from content notes."""
    from sable.vault.topics import refresh_topics
    vault_path = _resolve_vault(org, vault)
    with console.status("Refreshing topics..."):
        refresh_topics(org, vault_path)
    console.print("[green]✓ Topics refreshed.[/green]")
