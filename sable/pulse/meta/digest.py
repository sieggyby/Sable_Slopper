"""Watchlist digest: surface top-lift posts with structural analysis."""
from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class DigestEntry:
    author_handle: str
    tweet_id: str
    total_lift: float
    format_bucket: str
    tweet_text: str
    hook_pattern: str
    analysis: str
    steal: str


@dataclass
class DigestReport:
    org: str
    period_days: int
    generated_at: str       # ISO UTC
    entries: list[DigestEntry] = field(default_factory=list)
    total_posts_considered: int = 0


def _get_digest_posts(org: str, period_days: int, top_n: int, conn: sqlite3.Connection) -> tuple[list[dict], int]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=period_days)).isoformat()
    rows = conn.execute(
        """
        SELECT st.tweet_id, st.text, st.author_handle, st.total_lift, st.format_bucket,
               va.anatomy_json
        FROM scanned_tweets st
        LEFT JOIN viral_anatomies va ON (va.tweet_id = st.tweet_id AND va.org = st.org)
        WHERE st.org = ?
          AND st.total_lift >= 3.0
          AND st.posted_at >= ?
        ORDER BY st.total_lift DESC
        LIMIT ?
        """,
        (org, cutoff, top_n),
    ).fetchall()

    count_row = conn.execute(
        """
        SELECT COUNT(*) FROM scanned_tweets
        WHERE org = ? AND total_lift >= 3.0 AND posted_at >= ?
        """,
        (org, cutoff),
    ).fetchone()
    total = count_row[0] if count_row else 0

    result = []
    for row in rows:
        d = dict(row) if hasattr(row, "keys") else {
            "tweet_id": row[0],
            "text": row[1],
            "author_handle": row[2],
            "total_lift": row[3],
            "format_bucket": row[4],
            "anatomy_json": row[5],
        }
        result.append(d)
    # Attach total as a side-channel via a sentinel entry (handled in generate_digest)
    return result, total


def _analyze_post_for_digest(post: dict, org_id: Optional[str]) -> tuple[str, str, str]:
    """Return (hook_pattern, analysis, steal). Never raises."""
    anatomy_json = post.get("anatomy_json")
    if anatomy_json:
        try:
            anatomy = json.loads(anatomy_json)
            hook_pattern = anatomy.get("hook_structure", "unknown")
            emotional = anatomy.get("emotional_register", "")
            topic = anatomy.get("topic_cluster", "")
            analysis = f"Emotionally {emotional} post about {topic}." if (emotional and topic) else "Analysis from cached anatomy."
            steal = anatomy.get("retweet_bait_element") or ""
            return hook_pattern, analysis, steal
        except Exception:
            pass

    # Cache miss — call Claude
    from sable.shared.api import call_claude_json
    author = post.get("author_handle", "unknown")
    text = post.get("text", "")
    lift = post.get("total_lift", 0.0)
    prompt = (
        f"This crypto Twitter post achieved {lift:.1f}x average engagement.\n\n"
        f'Post by @{author}:\n"{text}"\n\n'
        "In 3 sentences: (1) What structural move is it making? (2) What should we steal from it? "
        "(3) What's the hook pattern in one phrase?\n\n"
        'Return JSON: {"analysis": "...", "steal": "...", "hook_pattern": "..."}'
    )
    try:
        raw = call_claude_json(prompt, call_type="pulse_meta_digest", org_id=org_id, max_tokens=256)
        data = json.loads(raw)
        return (
            data.get("hook_pattern", "unknown"),
            data.get("analysis", "analysis unavailable"),
            data.get("steal", ""),
        )
    except Exception:
        return "unknown", "analysis unavailable", ""


def generate_digest(
    org: str,
    period_days: int,
    top_n: int,
) -> DigestReport:
    from sable.pulse.meta.db import get_conn

    conn = get_conn()
    conn.row_factory = sqlite3.Row

    posts, total = _get_digest_posts(org, period_days, top_n, conn)

    org_id: Optional[str] = None
    try:
        from sable.platform.db import get_db
        platform_conn = get_db()
        try:
            row = platform_conn.execute("SELECT org_id FROM orgs WHERE org_id = ?", (org,)).fetchone()
            if row:
                org_id = str(row["org_id"])
        finally:
            platform_conn.close()
    except Exception as e:
        logger.warning("Could not resolve org_id for '%s': %s", org, e)

    generated_at = datetime.now(timezone.utc).isoformat()
    report = DigestReport(org=org, period_days=period_days, generated_at=generated_at)
    report.total_posts_considered = total

    for post in posts:
        hook_pattern, analysis, steal = _analyze_post_for_digest(post, org_id)
        entry = DigestEntry(
            author_handle=post.get("author_handle", ""),
            tweet_id=post.get("tweet_id", ""),
            total_lift=post.get("total_lift") or 0.0,
            format_bucket=post.get("format_bucket") or "",
            tweet_text=post.get("text") or "",
            hook_pattern=hook_pattern,
            analysis=analysis,
            steal=steal,
        )
        report.entries.append(entry)

    conn.close()
    return report


def render_digest(report: DigestReport) -> str:
    if not report.entries:
        return f"No posts with 3x+ lift in the last {report.period_days} days."

    # Week label: first day of the period
    try:
        generated = datetime.fromisoformat(report.generated_at)
    except Exception:
        generated = datetime.now(timezone.utc)
    week_start = generated - timedelta(days=report.period_days)
    week_label = "Week of " + week_start.strftime("%b %-d, %Y")
    date_str = generated.strftime("%Y-%m-%d")

    lines = [
        f"## Watchlist Digest — {week_label}",
        "",
        f"*{len(report.entries)} posts with 3x+ lift · Generated {date_str}*",
        "",
        "---",
    ]

    for i, entry in enumerate(report.entries, 1):
        lines += [
            "",
            f"### {i}. @{entry.author_handle} — {entry.total_lift:.1f}x lift — {entry.format_bucket}",
            "",
            f"> {entry.tweet_text[:280]}",
            "",
            f"**Hook pattern:** {entry.hook_pattern}",
            f"**Analysis:** {entry.analysis}",
            f"**What to steal:** {entry.steal}",
        ]

    return "\n".join(lines)


def save_digest_to_vault(report: DigestReport, vault_root: Path) -> Path:
    date_str = report.generated_at[:10]
    out_dir = vault_root / "digests"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"watchlist_digest_{date_str}.md"
    frontmatter = (
        f"---\ntype: digest\norg: {report.org}\n"
        f"period_days: {report.period_days}\ngenerated_at: {report.generated_at}\n---\n\n"
    )
    out_path.write_text(frontmatter + render_digest(report))
    return out_path
