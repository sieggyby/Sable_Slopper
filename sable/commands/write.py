"""CLI for sable write command."""
from __future__ import annotations

import sys
import click


@click.command("write")
@click.argument("handle")
@click.option("--format", "format_bucket", default=None,
              help="Format bucket (e.g. standalone_text, short_clip). Auto-selects if omitted.")
@click.option("--topic", default=None, help="Topic to write about (uses account interests if omitted).")
@click.option("--source-url", default=None, help="Source tweet URL for quote-tweet format.")
@click.option("--variants", default=3, show_default=True, help="Number of variants to generate.")
@click.option("--org", default=None,
              help="Org context for trend data (defaults to roster org).")
@click.option("--score", "run_score", is_flag=True, default=False,
              help="Score each variant's hook against recent high-performing patterns.")
@click.option("--watchlist-wire", is_flag=True, default=False,
              help="Inject top niche topics from meta.db into prompt.")
@click.option("--no-anatomy", "no_anatomy", is_flag=True, default=False,
              help="Skip viral anatomy pattern injection.")
def write_command(handle, format_bucket, topic, source_url, variants, org, run_score,
                  watchlist_wire, no_anatomy):
    """Generate tweet variants for a managed account."""
    from sable.platform.errors import SableError
    from sable.roster.manager import require_account
    from sable.shared.paths import meta_db_path, vault_dir
    from sable.write.generator import generate_tweet_variants

    try:
        acc = require_account(handle)
    except (ValueError, SableError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    resolved_org = org or acc.org
    vault_root = vault_dir(resolved_org) if resolved_org else None

    try:
        result = generate_tweet_variants(
            handle=acc.handle,
            org=resolved_org or "",
            format_bucket=format_bucket,
            topic=topic,
            source_url=source_url,
            num_variants=variants,
            meta_db_path=meta_db_path() if resolved_org else None,
            vault_root=vault_root,
            watchlist_wire=watchlist_wire,
            use_anatomy=not no_anatomy,
        )
    except SableError as e:
        click.echo(f"Error [{e.code}]: {e.message}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    if result.anatomy_ref:
        click.echo(f"Structural ref: {result.anatomy_ref}")

    variant_list = result.variants
    if not variant_list:
        click.echo("No variants generated. Check logs for details.", err=True)
        sys.exit(1)

    for i, v in enumerate(variant_list, 1):
        hook_str = ""
        if run_score:
            from sable.write.scorer import score_draft
            try:
                hs = score_draft(
                    handle=acc.handle,
                    draft_text=v.text,
                    format_bucket=format_bucket or "standalone_text",
                    org=resolved_org,
                )
                hook_str = f"  ·  hook: {hs.grade} ({hs.score}/10)"
            except SableError as e:
                hook_str = f"  ·  hook: [error: {e.code}]"
            except Exception as e:
                hook_str = f"  ·  hook: [error: {e}]"

        click.echo(f"\n{'='*60}")
        click.echo(f"Variant {i}  ·  fit: {v.format_fit_score}/10{hook_str}  ·  {v.structural_move}")
        click.echo("="*60)
        click.echo(v.text)
        if v.notes:
            click.echo(f"\nNotes: {v.notes}")

    if result.vault_hint:
        click.echo(f"\nTo pair with media: {result.vault_hint}")
    click.echo()
