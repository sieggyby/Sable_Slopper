"""Account audit runner for `sable diagnose`."""
from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

from sable.platform.db import get_db
from sable.pulse.account_report import compute_account_format_lift
from sable.vault.notes import load_all_notes

_FORMAT_OVERINDEX_RATIO = 0.50
_NICHE_LIFT_FLOOR = 0.8
_ENGAGEMENT_DROP_THRESHOLD = 0.80

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class FindingSeverity(Enum):
    WARNING = "warning"
    INFO = "info"
    OK = "ok"


@dataclass
class Finding:
    section: str
    severity: FindingSeverity
    message: str
    detail: str | None = None


@dataclass
class DiagnosisReport:
    handle: str
    org: str
    days: int
    generated_at: str
    findings: list[Finding] = field(default_factory=list)
    artifact_id: str | None = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _norm_handle(handle: str) -> str:
    return handle if handle.startswith("@") else f"@{handle}"


def _age_days(ts: str | None) -> float:
    if not ts:
        return 0.0
    try:
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 86400
    except (ValueError, TypeError):
        return 0.0


# ---------------------------------------------------------------------------
# Section name constants
# ---------------------------------------------------------------------------

_SECTION_FORMAT = "Format Portfolio"
_SECTION_TOPIC = "Topic Freshness"
_SECTION_VAULT = "Vault Utilization"
_SECTION_CADENCE = "Posting Cadence"
_SECTION_ENGAGEMENT = "Engagement Trend"


# ---------------------------------------------------------------------------
# Audit helpers
# ---------------------------------------------------------------------------

def _audit_format_portfolio(
    handle: str,
    org: str,
    days: int,
    pulse_db_path: Path,
    meta_db_path: Optional[Path],
) -> list[Finding]:
    try:
        report = compute_account_format_lift(handle, org, days, pulse_db_path, meta_db_path)
    except Exception:
        return []

    findings: list[Finding] = []

    # Over-indexing check
    if report.total_posts >= 5:
        for entry in report.entries:
            ratio = entry.post_count / report.total_posts
            if ratio > _FORMAT_OVERINDEX_RATIO:
                findings.append(Finding(
                    section=_SECTION_FORMAT,
                    severity=FindingSeverity.WARNING,
                    message=(
                        f"Over-indexed on {entry.format_bucket} "
                        f"({entry.post_count}/{report.total_posts} posts, {ratio:.0%})"
                    ),
                ))

    # Primary format diagnostics
    if report.entries:
        primary = max(report.entries, key=lambda e: e.post_count)

        if primary.divergence_signal == "EXECUTION GAP":
            detail = None
            if primary.account_lift is not None and primary.niche_lift is not None:
                detail = (
                    f"account_lift={primary.account_lift:.2f}, "
                    f"niche_lift={primary.niche_lift:.2f}"
                )
            findings.append(Finding(
                section=_SECTION_FORMAT,
                severity=FindingSeverity.WARNING,
                message=(
                    f"Execution gap on primary format {primary.format_bucket}: "
                    "niche surging but account underperforming"
                ),
                detail=detail,
            ))

        if primary.niche_lift is not None and primary.niche_lift < _NICHE_LIFT_FLOOR:
            findings.append(Finding(
                section=_SECTION_FORMAT,
                severity=FindingSeverity.WARNING,
                message=(
                    f"Primary format {primary.format_bucket} declining in niche "
                    f"(niche_lift={primary.niche_lift:.2f})"
                ),
            ))

    # Format gaps (surging in niche but unused by account)
    for fmt in report.missing_niche_formats:
        findings.append(Finding(
            section=_SECTION_FORMAT,
            severity=FindingSeverity.INFO,
            message=f"Niche surging format unused by account: {fmt}",
        ))

    return findings


def _audit_topic_freshness(
    handle: str,
    org: str,
    pulse_db_path: Path,
    meta_db_path: Optional[Path],
) -> list[Finding]:
    try:
        pulse_conn = sqlite3.connect(str(pulse_db_path))
        pulse_conn.row_factory = sqlite3.Row
        rows = pulse_conn.execute(
            "SELECT text FROM posts WHERE account_handle = ? ORDER BY posted_at DESC LIMIT 20",
            (handle,),
        ).fetchall()
        pulse_conn.close()
    except Exception:
        return []

    # Extract terms from last 20 posts
    combined = " ".join((r["text"] or "") for r in rows)
    tickers = re.findall(r'\$[A-Z]{2,6}', combined)
    phrases = re.findall(r'\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)*\b', combined)
    all_terms = [t.lower() for t in tickers + phrases]
    term_counts = Counter(all_terms)
    account_term_set = set(all_terms)

    # Load niche signals from meta.db
    niche_terms: list[str] = []
    if meta_db_path and org:
        try:
            meta_conn = sqlite3.connect(str(meta_db_path))
            meta_conn.row_factory = sqlite3.Row
            meta_rows = meta_conn.execute(
                """SELECT term FROM topic_signals
                   WHERE org = ?
                   ORDER BY avg_lift * unique_authors DESC
                   LIMIT 10""",
                (org,),
            ).fetchall()
            meta_conn.close()
            niche_terms = [r["term"].lower() for r in meta_rows]
        except Exception:
            pass

    findings: list[Finding] = []

    # Topic gap: niche top-10 term not in account corpus
    for term in niche_terms:
        if term not in account_term_set:
            findings.append(Finding(
                section=_SECTION_TOPIC,
                severity=FindingSeverity.INFO,
                message=f"Topic gap: '{term}' trending in niche but absent from recent posts",
            ))

    # Differentiation: account top-1 not in niche top-10
    if term_counts and niche_terms:
        top_account_term = term_counts.most_common(1)[0][0]
        if top_account_term not in niche_terms:
            findings.append(Finding(
                section=_SECTION_TOPIC,
                severity=FindingSeverity.INFO,
                message=f"Possible differentiation: account top topic '{top_account_term}' not in niche top-10",
            ))

    return findings


def _audit_vault_utilization(
    handle: str,
    org: str,
    vault_root: Optional[Path],
    meta_db_path: Optional[Path],
) -> list[Finding]:
    if vault_root is None:
        return []

    try:
        all_notes = load_all_notes(vault_root)
    except Exception:
        return []

    account_notes = [
        n for n in all_notes
        if n.get("account") == handle or handle in (n.get("suggested_for") or [])
    ]
    unposted = [n for n in account_notes if not n.get("posted_by")]
    stale_unposted = [n for n in unposted if _age_days(n.get("assembled_at")) > 7]

    findings: list[Finding] = []

    if stale_unposted:
        findings.append(Finding(
            section=_SECTION_VAULT,
            severity=FindingSeverity.WARNING,
            message=f"Stale inventory: {len(stale_unposted)} unposted note(s) older than 7 days",
            detail=", ".join(n.get("_note_path", "?") for n in stale_unposted[:3]),
        ))

    # Hot topic sitting idle: check if any unposted note's topic matches niche signals
    niche_top: list[str] = []
    if meta_db_path and org:
        try:
            meta_conn = sqlite3.connect(str(meta_db_path))
            meta_conn.row_factory = sqlite3.Row
            meta_rows = meta_conn.execute(
                """SELECT term FROM topic_signals
                   WHERE org = ?
                   ORDER BY avg_lift * unique_authors DESC
                   LIMIT 5""",
                (org,),
            ).fetchall()
            meta_conn.close()
            niche_top = [r["term"].lower() for r in meta_rows]
        except Exception:
            pass

    for note in unposted:
        topic = (note.get("topic") or "").lower()
        if topic and any(nt in topic or topic in nt for nt in niche_top):
            findings.append(Finding(
                section=_SECTION_VAULT,
                severity=FindingSeverity.WARNING,
                message=(
                    f"Hot topic sitting idle: note on '{note.get('topic')}' "
                    "matches niche signal but is unposted"
                ),
            ))
            break

    return findings


def _audit_posting_cadence(
    handle: str,
    pulse_db_path: Path,
    days: int,
) -> list[Finding]:
    try:
        since_iso = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        conn = sqlite3.connect(str(pulse_db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT DATE(posted_at) AS post_date, COUNT(*) AS post_count
            FROM posts
            WHERE account_handle = ? AND posted_at >= ?
            GROUP BY DATE(posted_at)
            ORDER BY post_date
            """,
            (handle, since_iso),
        ).fetchall()
        conn.close()
    except Exception:
        return []

    total_posts = sum(r["post_count"] for r in rows)
    avg_posts_per_day = total_posts / days if days > 0 else 0.0
    distinct_dates = sorted(r["post_date"] for r in rows)

    # Compute longest dry spell (consecutive days with no posts)
    longest_dry_spell = 0
    if distinct_dates:
        date_objects = [date.fromisoformat(d) for d in distinct_dates]
        window_start = (datetime.now(timezone.utc) - timedelta(days=days)).date()
        # Gap before first post
        gap = (date_objects[0] - window_start).days - 1
        longest_dry_spell = max(longest_dry_spell, max(0, gap))
        # Gaps between consecutive posts
        for i in range(1, len(date_objects)):
            gap = (date_objects[i] - date_objects[i - 1]).days - 1
            longest_dry_spell = max(longest_dry_spell, gap)
        # Gap after last post
        today = datetime.now(timezone.utc).date()
        gap = (today - date_objects[-1]).days - 1
        longest_dry_spell = max(longest_dry_spell, max(0, gap))
    else:
        longest_dry_spell = days

    findings: list[Finding] = []

    if avg_posts_per_day > 3.0:
        findings.append(Finding(
            section=_SECTION_CADENCE,
            severity=FindingSeverity.INFO,
            message=f"High posting rate: {avg_posts_per_day:.1f} posts/day avg over {days} days",
        ))
    elif avg_posts_per_day < 0.5:
        findings.append(Finding(
            section=_SECTION_CADENCE,
            severity=FindingSeverity.WARNING,
            message=f"Low activity: {avg_posts_per_day:.2f} posts/day avg over {days} days",
        ))

    if longest_dry_spell >= 5:
        findings.append(Finding(
            section=_SECTION_CADENCE,
            severity=FindingSeverity.WARNING,
            message=f"Longest dry spell: {longest_dry_spell} days with no posts",
        ))

    if not findings:
        findings.append(Finding(
            section=_SECTION_CADENCE,
            severity=FindingSeverity.OK,
            message="Cadence healthy",
        ))

    return findings


def _audit_engagement_trend(
    handle: str,
    pulse_db_path: Path,
) -> list[Finding]:
    try:
        conn = sqlite3.connect(str(pulse_db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT p.posted_at,
                   COALESCE(s.likes,0) + 3*COALESCE(s.replies,0) + 4*COALESCE(s.retweets,0)
                   + 5*COALESCE(s.quotes,0) + 2*COALESCE(s.bookmarks,0) + 0.5*COALESCE(s.views,0) AS eng
            FROM posts p
            LEFT JOIN snapshots s ON (
                p.id = s.post_id
                AND s.id = (SELECT MAX(s2.id) FROM snapshots s2 WHERE s2.post_id = p.id)
            )
            WHERE p.account_handle = ?
              AND p.posted_at >= datetime('now', '-28 days')
            ORDER BY p.posted_at
            """,
            (handle,),
        ).fetchall()
        conn.close()
    except Exception:
        return []

    if len(rows) < 10:
        return [Finding(
            section=_SECTION_ENGAGEMENT,
            severity=FindingSeverity.INFO,
            message="Insufficient data for engagement trend analysis (< 10 posts in last 28 days)",
        )]

    # Bucket into 4 × 7-day windows (windows[0]=oldest, windows[3]=newest)
    now = datetime.now(timezone.utc)
    windows: list[list[float]] = [[], [], [], []]
    for row in rows:
        try:
            posted_at = datetime.fromisoformat(row["posted_at"])
            if posted_at.tzinfo is None:
                posted_at = posted_at.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
        days_ago = (now - posted_at).days
        if days_ago < 7:
            windows[3].append(float(row["eng"]))
        elif days_ago < 14:
            windows[2].append(float(row["eng"]))
        elif days_ago < 21:
            windows[1].append(float(row["eng"]))
        else:
            windows[0].append(float(row["eng"]))

    week_means: list[Optional[float]] = [
        sum(w) / len(w) if w else None
        for w in windows
    ]

    # Flag if two consecutive week-over-week drops exceed 20%
    consecutive_drops = 0
    max_consecutive = 0
    for i in range(1, 4):
        prev = week_means[i - 1]
        curr = week_means[i]
        if prev is not None and curr is not None and prev > 0:
            if curr / prev < _ENGAGEMENT_DROP_THRESHOLD:
                consecutive_drops += 1
                max_consecutive = max(max_consecutive, consecutive_drops)
            else:
                consecutive_drops = 0
        else:
            consecutive_drops = 0

    if max_consecutive >= 2:
        return [Finding(
            section=_SECTION_ENGAGEMENT,
            severity=FindingSeverity.WARNING,
            message="Engagement declining: two consecutive week-over-week drops > 20%",
        )]

    return []


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def run_diagnosis(
    handle: str,
    org: str,
    days: int,
    pulse_db_path: Path,
    meta_db_path: Optional[Path],
    vault_root: Optional[Path],
    sable_db_path: Path,
) -> DiagnosisReport:
    handle = _norm_handle(handle)
    findings: list[Finding] = []
    findings += _audit_format_portfolio(handle, org, days, pulse_db_path, meta_db_path)
    findings += _audit_topic_freshness(handle, org, pulse_db_path, meta_db_path)
    findings += _audit_vault_utilization(handle, org, vault_root, meta_db_path)
    findings += _audit_posting_cadence(handle, pulse_db_path, days)
    findings += _audit_engagement_trend(handle, pulse_db_path)
    return DiagnosisReport(
        handle=handle,
        org=org,
        days=days,
        generated_at=datetime.now(timezone.utc).isoformat(),
        findings=findings,
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

_ICONS = {
    FindingSeverity.OK: "✅",
    FindingSeverity.WARNING: "⚠",
    FindingSeverity.INFO: "ℹ",
}

_SECTION_ORDER = [
    _SECTION_FORMAT,
    _SECTION_TOPIC,
    _SECTION_VAULT,
    _SECTION_CADENCE,
    _SECTION_ENGAGEMENT,
]


def render_diagnosis(report: DiagnosisReport) -> str:
    lines: list[str] = []
    lines.append(
        f"Diagnosis: {report.handle}  |  org: {report.org}  |  last {report.days}d"
    )
    lines.append("")

    by_section: dict[str, list[Finding]] = {}
    for f in report.findings:
        by_section.setdefault(f.section, []).append(f)

    for section in _SECTION_ORDER:
        section_findings = by_section.get(section, [])
        if not section_findings:
            continue
        bar = "═" * max(1, 50 - len(section) - 1)
        lines.append(f"═══ {section} {bar}")
        for finding in section_findings:
            icon = _ICONS[finding.severity]
            lines.append(f"  {icon}  {finding.message}")
            if finding.detail:
                lines.append(f"      {finding.detail}")
        lines.append("")

    warnings = sum(1 for f in report.findings if f.severity == FindingSeverity.WARNING)
    infos = sum(1 for f in report.findings if f.severity == FindingSeverity.INFO)
    lines.append(f"{warnings} warnings, {infos} info items")

    if report.artifact_id:
        lines.append(f"Saved as artifact {report.artifact_id}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Artifact persistence
# ---------------------------------------------------------------------------

def save_diagnosis_artifact(report: DiagnosisReport, org: str) -> str:
    conn = get_db()
    row = conn.execute(
        "SELECT org_id FROM orgs WHERE org_id = ?", (org,)
    ).fetchone()
    if row is None:
        return ""
    org_id = row["org_id"]
    metadata = {
        "handle": report.handle,
        "days": report.days,
        "generated_at": report.generated_at,
        "warning_count": sum(
            1 for f in report.findings if f.severity == FindingSeverity.WARNING
        ),
        "info_count": sum(
            1 for f in report.findings if f.severity == FindingSeverity.INFO
        ),
    }
    cur = conn.execute(
        "INSERT INTO artifacts (org_id, artifact_type, metadata_json) VALUES (?,?,?)",
        (org_id, "account_diagnosis", json.dumps(metadata)),
    )
    conn.commit()
    return str(cur.lastrowid)
