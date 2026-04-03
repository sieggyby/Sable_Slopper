"""CLI for sable pulse meta — content shape intelligence."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import click
from rich.console import Console

console = Console()


@click.group("meta", invoke_without_command=True)
@click.option("--org", default=None, help="Org to analyze (runs full analysis if no subcommand)")
@click.option("--deep", is_flag=True, default=False)
@click.option("--cheap", is_flag=True, default=False, help="Skip Claude analysis")
@click.option("--trends-only", "trends_only", is_flag=True, default=False,
              help="Skip vault recommendations")
@click.option("--dry-run", "dry_run", is_flag=True, default=False)
@click.pass_context
def meta_group(ctx, org, deep, cheap, trends_only, dry_run):
    """Content shape intelligence: what to post, stop doing, and create next."""
    if ctx.invoked_subcommand is None:
        if org:
            _run_analysis(org=org, deep=deep, cheap=cheap, trends_only=trends_only, dry_run=dry_run)
        else:
            click.echo(ctx.get_help())


# ---------------------------------------------------------------------------
# Watchlist commands
# ---------------------------------------------------------------------------

@meta_group.group("watchlist")
def watchlist_group():
    """Manage the account watchlist."""


@watchlist_group.command("list")
@click.option("--org", default=None, help="Include org-specific accounts too")
def watchlist_list(org):
    """List all watchlist accounts."""
    from sable.pulse.meta.watchlist import list_watchlist
    entries = list_watchlist(org)
    if not entries:
        scope = f"org '{org}'" if org else "global"
        console.print(
            f"[dim]No accounts in watchlist ({scope}). "
            f"Add with: sable pulse meta watchlist add @handle[/dim]"
        )
        return
    console.print(f"[bold]{len(entries)} accounts:[/bold]")
    for e in entries:
        niche = f" [{e.get('niche', '')}]" if e.get("niche") else ""
        console.print(f"  {e['handle']}{niche}")


@watchlist_group.command("add")
@click.argument("handle")
@click.option("--org", default=None, help="Add to org-specific list (omit for global)")
@click.option("--niche", default="", help="Niche/category label")
@click.option("--notes", default="", help="Notes about this account")
def watchlist_add(handle, org, niche, notes):
    """Add a handle to the watchlist."""
    from sable.pulse.meta.watchlist import add_handle
    added = add_handle(handle, org, niche, notes)
    if added:
        scope = f"org '{org}'" if org else "global"
        console.print(f"[green]✓[/green] Added {handle} to {scope} watchlist")
    else:
        console.print(f"[yellow]{handle} already in watchlist[/yellow]")


@watchlist_group.command("remove")
@click.argument("handle")
@click.option("--org", default=None, help="Remove from org-specific list (omit for global)")
def watchlist_remove(handle, org):
    """Remove a handle from the watchlist."""
    from sable.pulse.meta.watchlist import remove_handle
    removed = remove_handle(handle, org)
    if removed:
        console.print(f"[green]✓[/green] Removed {handle}")
    else:
        console.print(f"[yellow]{handle} not found in watchlist[/yellow]")


@watchlist_group.command("validate")
def watchlist_validate():
    """Validate watchlist structure."""
    from sable.pulse.meta.watchlist import validate
    issues = validate()
    if issues:
        console.print("[red]Validation issues:[/red]")
        for issue in issues:
            console.print(f"  ✗ {issue}")
        sys.exit(1)
    else:
        console.print("[green]✓ Watchlist is valid[/green]")


@watchlist_group.command("stats")
def watchlist_stats():
    """Show watchlist summary statistics."""
    from sable.pulse.meta.watchlist import stats
    s = stats()
    console.print(f"Total accounts: {s['total']}")
    console.print(f"  Global: {s['global_count']}")
    for org_name, count in s.get("org_counts", {}).items():
        console.print(f"  {org_name}: {count}")
    if s.get("niches"):
        console.print("Niches:")
        for niche, count in sorted(s["niches"].items(), key=lambda x: x[1], reverse=True):
            console.print(f"  {niche}: {count}")


@watchlist_group.command("amplifiers")
@click.option("--org", required=True, help="Org to analyze")
@click.option("--window-days", "window_days", default=30, show_default=True,
              help="Look-back window in days")
@click.option("--top", "top_n", default=10, show_default=True,
              help="Number of top amplifiers to show")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON")
def watchlist_amplifiers(org, window_days, top_n, as_json):
    """Rank watchlist accounts by amplification power."""
    import json as json_mod
    from sable.pulse.meta.amplifiers import compute_amplifiers
    from sable.pulse.meta import db as meta_db

    meta_db.migrate()
    results = compute_amplifiers(org=org, window_days=window_days, conn=meta_db.get_conn())

    if not results:
        console.print(f"[dim]No tweet data for org '{org}' in the last {window_days} days.[/dim]")
        return

    results = results[:top_n]

    if as_json:
        from dataclasses import asdict
        console.print(json_mod.dumps([asdict(r) for r in results], indent=2))
        return

    from rich.table import Table
    table = Table(title=f"Top {len(results)} Amplifiers — {org} (last {window_days}d)")
    table.add_column("Rank", justify="right", style="bold")
    table.add_column("Handle")
    table.add_column("Amp Score", justify="right")
    table.add_column("RT_v", justify="right")
    table.add_column("RPR", justify="right")
    table.add_column("QTR", justify="right")
    for r in results:
        table.add_row(
            str(r.rank),
            r.author,
            f"{r.amp_score:.3f}",
            f"{r.rt_v:.2f}",
            f"{r.rpr:.3f}",
            f"{r.qtr:.3f}",
        )
    console.print(table)


@watchlist_group.command("health")
@click.option("--org", default=None)
def watchlist_health(org):
    """Run health diagnostics on watchlist + existing scan data."""
    from sable.pulse.meta.watchlist import health
    from sable.pulse.meta import db as meta_db
    meta_db.migrate()
    result = health(org, db=meta_db)

    warnings = result.get("warnings", [])
    metrics = result.get("metrics", {})

    console.print("[bold]Watchlist Health Report[/bold]")
    console.print(f"Total accounts: {metrics.get('total_accounts', 0)}")

    if warnings:
        console.print("\n[yellow]Warnings:[/yellow]")
        for w in warnings:
            console.print(f"  ⚠  {w}")
    else:
        console.print("\n[green]✓ No issues detected[/green]")

    if "format_diversity" in metrics:
        console.print("\nFormat diversity (% of watchlist participating):")
        for bucket, pct in sorted(metrics["format_diversity"].items()):
            color = "red" if pct < 0.20 else "green"
            console.print(f"  {bucket}: [{color}]{pct:.0%}[/{color}]")

    if "top5_author_concentration" in metrics:
        pct = metrics["top5_author_concentration"]
        color = "red" if pct > 0.60 else "green"
        console.print(f"\nTop 5 author concentration: [{color}]{pct:.0%}[/{color}]")


# ---------------------------------------------------------------------------
# Scan command
# ---------------------------------------------------------------------------

@meta_group.command("scan")
@click.option("--org", required=True, help="Org to scan for")
@click.option("--deep", is_flag=True, help="Include topic keyword searches beyond watchlist (outsider results are transient and not stored in meta.db)")
@click.option("--full", is_flag=True, help="Ignore incremental cursors — full 48h rescan")
@click.option("--cheap", is_flag=True, help="Scan + classify only, skip Claude analysis")
@click.option("--dry-run", "dry_run", is_flag=True, help="Show cost estimate without API calls")
@click.option("--skip-if-fresh", "skip_if_fresh", type=int, default=None,
              help="Skip scan if last successful scan completed within N hours.")
def meta_scan(org, deep, full, cheap, dry_run, skip_if_fresh=None):
    """Scan watchlist accounts and collect/classify tweets."""
    from sable.pulse.meta import db as meta_db
    from sable.pulse.meta.watchlist import list_watchlist
    from sable.pulse.meta.scanner import Scanner
    from sable import config as sable_cfg

    meta_db.migrate()

    watchlist = list_watchlist(org)
    if not watchlist:
        console.print(
            f"[yellow]No accounts in watchlist for org '{org}'. "
            f"Add with: sable pulse meta watchlist add @handle --org {org}[/yellow]"
        )
        return

    meta_cfg = sable_cfg.load_config().get("pulse_meta", {})
    max_cost = meta_cfg.get("max_cost_per_run", 1.00)
    mode = "deep" if deep else ("full" if full else "incremental")

    scanner = Scanner(
        org=org,
        watchlist=watchlist,
        db=meta_db,
        cfg_meta=meta_cfg,
        deep=deep,
        full=full,
        dry_run=dry_run,
        max_cost=max_cost,
    )

    if dry_run:
        estimate = scanner.estimate_cost()
        console.print("[bold]Dry run — estimated cost:[/bold]")
        console.print(f"  Accounts: {estimate['accounts']}")
        console.print(f"  Requests: {estimate['estimated_requests']}")
        console.print(f"  Cost: ~${estimate['estimated_cost_usd']:.3f}")
        if estimate["estimated_cost_usd"] > max_cost:
            console.print(
                f"[red]⚠ Estimated ${estimate['estimated_cost_usd']:.3f} "
                f"exceeds limit ${max_cost:.2f}. "
                f"Use --cheap or increase max_cost_per_run in config.[/red]"
            )
        return

    if skip_if_fresh is not None:
        from sable.pulse.meta.db import get_latest_successful_scan_at
        from datetime import datetime, timezone, timedelta
        last = get_latest_successful_scan_at(org)
        if last is not None:
            last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            age_hours = (datetime.now(timezone.utc) - last_dt).total_seconds() / 3600
            if age_hours < skip_if_fresh:
                console.print(
                    f"[dim]Scan skipped: last scan {age_hours:.1f}h ago "
                    f"(within {skip_if_fresh}h window)[/dim]"
                )
                return

    scan_id = meta_db.create_scan_run(org, mode=mode, watchlist_size=len(watchlist))

    result = None
    with console.status(f"Scanning {len(watchlist)} accounts ({mode})..."):
        try:
            result = scanner.run(scan_id)
        except Exception as e:
            partial = meta_db.get_tweets_for_scan(scan_id, org)
            meta_db.fail_scan_run(
                scan_id, str(e),
                tweets_collected=len(partial),
                tweets_new=scanner._tweets_new,
                estimated_cost=scanner._estimated_cost,
            )
            from sable.platform.errors import redact_error
            console.print(f"[red]Scan failed: {redact_error(str(e))}[/red]")
            sys.exit(1)

    if result.get("aborted"):
        console.print(
            f"[red]⚠ Scan aborted: cost limit exceeded. "
            f"Partial results recorded ({result['tweets_collected']} tweets, "
            f"${result['estimated_cost']:.3f}).[/red]"
        )
        meta_db.complete_scan_run(
            scan_id=scan_id,
            tweets_collected=result["tweets_collected"],
            tweets_new=result["tweets_new"],
            estimated_cost=result["estimated_cost"],
        )
        sys.exit(1)

    meta_db.complete_scan_run(
        scan_id=scan_id,
        tweets_collected=result["tweets_collected"],
        tweets_new=result["tweets_new"],
        estimated_cost=result.get("estimated_cost", 0.0),
    )

    console.print(
        f"[green]✓[/green] Scan complete: "
        f"{result['tweets_new']} new tweets "
        f"({result['tweets_collected']} collected from {len(watchlist)} accounts)"
    )
    console.print(f"[dim]Estimated cost: ${result.get('estimated_cost', 0.0):.3f}[/dim]")

    # AR5-8: warn about failed author fetches
    if result.get("failed_authors"):
        console.print(f"[yellow]⚠ Failed to fetch {len(result['failed_authors'])} author(s):[/yellow]")
        for failed_handle in result["failed_authors"]:
            console.print(f"  [yellow]  - {failed_handle}[/yellow]")

    # First-scan tip
    runs = meta_db.get_scan_runs(org, limit=5)
    if len(runs) <= 2:
        console.print(
            "\n[dim]First scan(s) use per-follower fallback for normalization. "
            "Run 2-3 more times to build author history for better accuracy.[/dim]"
        )


@meta_group.command("status")
def meta_status():
    """Show scan history summary for all orgs."""
    from sable.pulse.meta import db as meta_db
    meta_db.migrate()
    rows = meta_db.get_scan_summary_all_orgs()
    if not rows:
        console.print("[dim]No scans recorded yet.[/dim]")
        return
    console.print(f"{'Org':<20} {'Last Scan':<22} {'Count':>6}")
    console.print("-" * 50)
    for r in rows:
        last = r["last_scan_at"] or "never"
        console.print(f"{r['org']:<20} {last:<22} {r['scan_count']:>6}")


# ---------------------------------------------------------------------------
# Core analysis pipeline (shared by group invocation and explicit run)
# ---------------------------------------------------------------------------

def _run_analysis(org: str, deep: bool, cheap: bool, trends_only: bool, dry_run: bool) -> None:
    """Run the full content shape analysis pipeline."""
    from sable.pulse.meta import db as meta_db
    from sable.pulse.meta.watchlist import list_watchlist
    from sable.pulse.meta.baselines import compute_baselines_from_db, _rows_to_normalized
    from sable.pulse.meta.trends import analyze_all_formats
    from sable.pulse.meta.topics import aggregate_topic_signals, load_vault_synonyms
    from sable.pulse.meta.analyzer import run_analysis, fallback_analysis
    from sable.pulse.meta.recommender import build_recommendations
    from sable.pulse.meta.reporter import render_report, write_vault_report
    from sable.pulse.meta.fingerprint import FORMAT_BUCKETS
    from sable.shared.paths import vault_dir
    from sable import config as sable_cfg

    meta_db.migrate()

    cfg_all = sable_cfg.load_config()
    meta_cfg = cfg_all.get("pulse_meta", {})
    min_baseline_days = meta_cfg.get("min_baseline_days", 5)
    top_n = meta_cfg.get("top_n_for_analysis", 20)
    method = meta_cfg.get("aggregation_method", "weighted_mean")
    model = meta_cfg.get("claude_model", "claude-sonnet-4-6")
    long_days = meta_cfg.get("baseline_long_days", 30)
    short_days = meta_cfg.get("baseline_short_days", 7)
    lookback = meta_cfg.get("lookback_hours", 48)

    # Vault path check
    vault_path = vault_dir(org)
    vault_available = vault_path.exists()
    if not vault_available and not trends_only:
        console.print(
            f"[yellow]Vault not initialized for org '{org}'. "
            f"Run `sable vault init --org {org}` for recommendations, "
            f"or use --trends-only.[/yellow]"
        )
        trends_only = True

    # Watchlist check
    watchlist = list_watchlist(org)
    if not watchlist:
        console.print(
            f"[yellow]No accounts in watchlist for org '{org}'. "
            f"Need 20+ for meaningful signal.[/yellow]"
        )
        return
    if len(watchlist) < 20:
        console.print(
            f"[yellow]Only {len(watchlist)} accounts in watchlist — "
            f"20+ recommended for meaningful signal.[/yellow]"
        )

    # Load recent tweets from DB
    recent_rows = meta_db.get_recent_tweets(org, hours=lookback)
    if not recent_rows:
        console.print(
            f"[yellow]No tweets in DB yet. "
            f"Run `sable pulse meta scan --org {org}` first.[/yellow]"
        )
        return

    # Group normalized tweets by format bucket
    tweets_by_bucket: dict[str, list] = {b: [] for b in FORMAT_BUCKETS}
    all_normalized = _rows_to_normalized(recent_rows)
    for t in all_normalized:
        if t.format_bucket in tweets_by_bucket:
            tweets_by_bucket[t.format_bucket].append(t)

    # Compute/retrieve baselines
    baselines = compute_baselines_from_db(org, meta_db, long_days, short_days, method)

    # Baseline age
    oldest = meta_db.get_oldest_tweet_date(org)
    baseline_days = 0
    if oldest:
        try:
            oldest_dt = datetime.fromisoformat(oldest.replace("Z", "+00:00"))
            baseline_days = max((datetime.now(timezone.utc) - oldest_dt).days, 0)
        except Exception:
            pass

    # Trend analysis
    trends = analyze_all_formats(
        org=org,
        tweets_by_bucket=tweets_by_bucket,
        baselines=baselines,
        baseline_days_available=baseline_days,
        cfg=meta_cfg,
        method=method,
    )

    # Topic signals
    vault_synonyms: dict = {}
    if vault_available:
        try:
            vault_synonyms = load_vault_synonyms(vault_path)
        except Exception:
            pass

    prev_topics = meta_db.get_prev_scan_topics(org, limit=1)
    topic_signals = aggregate_topic_signals(
        tweets=recent_rows,
        synonyms=vault_synonyms,
        prev_scan_mentions=prev_topics,
    )

    # Top tweets for Claude
    top_tweets = sorted(
        recent_rows,
        key=lambda r: r.get("total_lift") or 0,
        reverse=True,
    )[:top_n]

    # Claude analysis
    analysis: dict = {}
    _claude_degraded = False
    if not cheap:
        # AR5-20: cost guard before calling Claude analysis
        from sable.shared.pricing import compute_cost as _compute_cost
        import logging as _logging
        _meta_logger = _logging.getLogger(__name__)
        _max_analysis_cost = meta_cfg.get("max_analysis_cost", 0.50)
        # Build summary_text to estimate token count
        _top_tweets_for_est = sorted(
            recent_rows, key=lambda r: r.get("total_lift") or 0, reverse=True
        )[:top_n]
        from sable.pulse.meta.reporter import render_report as _rr
        import io as _io
        # Estimate from top_tweets text content
        _est_text = " ".join(str(t.get("text", "")) for t in _top_tweets_for_est)
        _est_input_tokens = len(_est_text) // 4
        _est_cost = _compute_cost(_est_input_tokens, 1500, model)
        if _est_cost > _max_analysis_cost:
            _meta_logger.warning(
                "Estimated analysis cost $%.4f exceeds max_analysis_cost $%.2f — forcing cheap mode",
                _est_cost, _max_analysis_cost
            )
            cheap = True
    if cheap:
        analysis = fallback_analysis(trends)
        _claude_degraded = True
    else:
        with console.status("Running Claude analysis..."):
            try:
                parsed, raw = run_analysis(
                    top_tweets=top_tweets,
                    trends=trends,
                    topic_signals=topic_signals,
                    org=org,
                    model=model,
                )
                analysis = parsed if parsed else fallback_analysis(trends)
                if not parsed:
                    _claude_degraded = True
                    console.print(
                        "[yellow]Claude analysis failed — showing quantitative trends.[/yellow]"
                    )
            except Exception as e:
                from sable.platform.errors import redact_error
                console.print(f"[yellow]Claude unavailable: {redact_error(str(e))} — showing quantitative trends.[/yellow]")
                analysis = fallback_analysis(trends)
                _claude_degraded = True

    # Recommendations
    recommendations: dict = {"post_now": [], "stop_doing": [], "gaps_to_fill": []}
    if not trends_only:
        accounts = []
        try:
            from sable.roster.manager import list_accounts
            accounts = list_accounts(org=org)
        except Exception:
            pass

        recommendations = build_recommendations(
            trends=trends,
            accounts=accounts,
            vault_path=vault_path if vault_available else None,
            analysis=analysis,
            cfg=meta_cfg,
            org=org,
        )

    # Store topic signals
    scan_runs = meta_db.get_scan_runs(org, limit=1)
    if scan_runs and topic_signals:
        latest_scan_id = scan_runs[0]["id"]
        sig_dicts = [
            {
                "term": s.term,
                "mention_count": s.mention_count,
                "unique_authors": s.unique_authors,
                "avg_lift": s.avg_lift,
                "prev_scan_mentions": s.prev_scan_mentions,
                "acceleration": s.acceleration,
            }
            for s in topic_signals
        ]
        try:
            meta_db.insert_topic_signals(org, latest_scan_id, sig_dicts)
        except Exception:
            pass

    # Render
    scan_info = scan_runs[0] if scan_runs else {}
    render_report(
        org=org,
        trends=trends,
        topic_signals=topic_signals,
        recommendations=recommendations,
        analysis=analysis,
        baseline_days=baseline_days,
        min_baseline_days=min_baseline_days,
        scan_info=scan_info,
    )

    # Write vault report
    if vault_available:
        report_path = write_vault_report(
            org=org,
            vault_path=vault_path,
            trends=trends,
            topic_signals=topic_signals,
            recommendations=recommendations,
            analysis=analysis,
            degraded=_claude_degraded,
        )
        console.print(f"\n[dim]Report written: {report_path}[/dim]")

    # Anatomy enrichment — silently skip on any error
    try:
        from sable.pulse.meta.anatomy import run_anatomy_enrichment
        n_saved = run_anatomy_enrichment(org)
        if n_saved:
            console.print(f"[dim]Anatomy: {n_saved} new viral post(s) analyzed[/dim]")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Digest command
# ---------------------------------------------------------------------------

@meta_group.command("digest")
@click.option("--org", required=True, help="Org slug (e.g. tig)")
@click.option("--period", "period_days", default=7, show_default=True,
              help="Look-back window in days.")
@click.option("--top", "top_n", default=10, show_default=True,
              help="Maximum posts to include.")
@click.option("--save", "save_to_vault", is_flag=True, default=False,
              help="Write digest to vault as a report note.")
def meta_digest(org: str, period_days: int, top_n: int, save_to_vault: bool) -> None:
    """Generate a watchlist intelligence digest of top-lift posts."""
    from sable.pulse.meta.digest import generate_digest, render_digest, save_digest_to_vault
    from sable.pulse.meta import db as meta_db
    from sable.shared.paths import vault_dir

    top_n = min(top_n, 25)

    meta_db.migrate()
    report = generate_digest(
        org=org,
        period_days=period_days,
        top_n=top_n,
    )
    console.print(render_digest(report))
    if save_to_vault:
        from sable.shared.paths import vault_dir as _vd
        saved_path = save_digest_to_vault(report, _vd(org))
        console.print(f"\n[dim]Saved: {saved_path}[/dim]")
