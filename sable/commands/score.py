"""CLI for sable score command."""
from __future__ import annotations

import sys
import click


@click.command("score")
@click.argument("handle")
@click.option("--text", "draft_text", required=True, help="Draft tweet text to score.")
@click.option("--format", "format_bucket", default="standalone_text", show_default=True,
              help="Format bucket to score against.")
@click.option("--org", default=None, help="Org slug (defaults to account's org).")
def score_command(handle, draft_text, format_bucket, org):
    """Score a draft tweet's hook against recent high-performing patterns."""
    from sable.platform.errors import SableError
    from sable.write.scorer import score_draft

    try:
        result = score_draft(handle, draft_text, format_bucket, org)
    except SableError as e:
        click.echo(f"Error [{e.code}]: {e.message}", err=True)
        sys.exit(1)
    except Exception as e:
        from sable.platform.errors import redact_error
        click.echo(f"Error: {redact_error(str(e))}", err=True)
        sys.exit(1)

    click.echo(f"\nHook Score: {result.grade}  ({result.score}/10)")
    if result.matched_pattern:
        click.echo(f"Pattern match: {result.matched_pattern}")
    click.echo(f"Voice fit: {result.voice_fit}/10")
    if result.flags:
        click.echo("\nFlags:")
        for f in result.flags:
            click.echo(f"  • {f}")
    if result.suggested_rewrite:
        click.echo(f'\nSuggested rewrite:\n  "{result.suggested_rewrite}"')
    click.echo("")
