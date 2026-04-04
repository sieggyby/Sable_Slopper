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
@click.option("--lexicon", "use_lexicon", is_flag=True, default=False,
              help="Inject community vocabulary from lexicon into prompt.")
@click.option("--voice-check", "voice_check", is_flag=True, default=False,
              help="Use full voice corpus for richer draft scoring (implies --score).")
def write_command(handle, format_bucket, topic, source_url, variants, org, run_score,
                  watchlist_wire, no_anatomy, use_lexicon, voice_check):
    """Generate tweet variants for a managed account."""
    from sable.platform.errors import SableError
    from sable.roster.manager import require_account
    from sable.shared.paths import meta_db_path, vault_dir
    from sable.write.generator import generate_tweet_variants

    try:
        acc = require_account(handle)
    except (ValueError, SableError) as e:
        from sable.platform.errors import redact_error
        click.echo(f"Error: {redact_error(str(e))}", err=True)
        sys.exit(1)

    # --voice-check implies --score
    if voice_check:
        run_score = True

    resolved_org = org or acc.org
    vault_root = vault_dir(resolved_org) if resolved_org else None

    # Build voice corpus if --voice-check
    voice_corpus = None
    if voice_check:
        from sable.write.generator import assemble_voice_corpus
        voice_corpus = assemble_voice_corpus(
            handle=acc.handle,
            org=resolved_org or "",
            vault_path=vault_root,
        )

    # Load lexicon terms if requested
    lex_terms = None
    if use_lexicon and resolved_org:
        try:
            from sable.pulse.meta import db as meta_db
            from sable.lexicon.store import list_terms
            meta_db.migrate()
            lex_terms = list_terms(resolved_org, meta_db.get_conn())
        except Exception as e:
            from sable.platform.errors import redact_error
            click.echo(f"Warning: lexicon load failed: {redact_error(str(e))}", err=True)

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
            lexicon_terms=lex_terms,
        )
    except SableError as e:
        click.echo(f"Error [{e.code}]: {e.message}", err=True)
        sys.exit(1)
    except Exception as e:
        from sable.platform.errors import redact_error
        click.echo(f"Error: {redact_error(str(e))}", err=True)
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
                    voice_corpus=voice_corpus,
                )
                hook_str = f"  ·  hook: {hs.grade} ({hs.score}/10)"
            except SableError as e:
                hook_str = f"  ·  hook: [error: {e.code}]"
            except Exception as e:
                from sable.platform.errors import redact_error
                hook_str = f"  ·  hook: [error: {redact_error(str(e))}]"

        click.echo(f"\n{'='*60}")
        click.echo(f"Variant {i}  ·  fit: {v.format_fit_score}/10{hook_str}  ·  {v.structural_move}")
        click.echo("="*60)
        click.echo(v.text)
        if v.notes:
            click.echo(f"\nNotes: {v.notes}")

    if result.vault_hint:
        click.echo(f"\nTo pair with media: {result.vault_hint}")
    click.echo()
