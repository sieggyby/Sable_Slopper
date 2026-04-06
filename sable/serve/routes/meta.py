"""Meta API routes — topic signals, format baselines, watchlist health."""
from __future__ import annotations

from fastapi import APIRouter, Query, Request

from sable.serve.auth import require_org_access
from sable.serve.deps import get_meta_db
from sable.vault.permissions import Action

router = APIRouter()

# Lift thresholds for signal classification (same as CLI)
_DOUBLE_DOWN = 1.5
_EXECUTION_GAP = 0.7


@router.get("/topics/{org}")
def topic_signals(org: str, request: Request, limit: int = Query(20, ge=1, le=100)):
    """Top topic signals from the most recent successful scan."""
    require_org_access(request, org, Action.meta_read)
    meta = get_meta_db()

    # Find latest successful scan
    scan_row = meta.execute(
        """SELECT MAX(id) AS max_id FROM scan_runs
           WHERE org = ?
             AND completed_at IS NOT NULL
             AND (claude_raw IS NULL OR claude_raw NOT LIKE 'FAILED:%')""",
        (org,),
    ).fetchone()

    scan_id = scan_row["max_id"] if scan_row else None
    if not scan_id:
        return []

    rows = meta.execute(
        """SELECT term, avg_lift, acceleration, unique_authors, mention_count
           FROM topic_signals
           WHERE org = ? AND scan_id = ? AND unique_authors >= 1
           ORDER BY (avg_lift * acceleration * unique_authors) DESC
           LIMIT ?""",
        (org, scan_id, limit),
    ).fetchall()

    results = []
    for r in rows:
        avg_lift = r["avg_lift"] or 0
        accel = r["acceleration"] or 0
        # Derive momentum and trend
        momentum = round(min(1.0, avg_lift / 5.0), 2) if avg_lift else 0
        if accel > 1.5:
            trend = "rising"
        elif accel < 0.5:
            trend = "declining"
        else:
            trend = "stable"
        mentions = r["mention_count"] or 0
        confidence = "high" if mentions >= 10 else ("medium" if mentions >= 5 else "low")
        results.append({
            "topic": r["term"],
            "momentum_score": momentum,
            "confidence": confidence,
            "trend_status": trend,
            "avg_lift": round(avg_lift, 2),
            "unique_authors": r["unique_authors"],
            "mention_count": mentions,
        })

    return results


@router.get("/baselines/{org}")
def format_baselines(org: str, request: Request):
    """Format baseline data — lift per format bucket from latest 30d window."""
    require_org_access(request, org, Action.meta_read)
    meta = get_meta_db()

    rows = meta.execute(
        """SELECT f.*
           FROM format_baselines f
           WHERE f.org = ? AND f.period_days = 30
             AND f.computed_at = (
                 SELECT MAX(f2.computed_at) FROM format_baselines f2
                 WHERE f2.org = f.org AND f2.format_bucket = f.format_bucket
                   AND f2.period_days = f.period_days
             )
           ORDER BY f.avg_total_lift DESC""",
        (org,),
    ).fetchall()

    if not rows:
        # Fall back to 7d baselines
        rows = meta.execute(
            """SELECT f.*
               FROM format_baselines f
               WHERE f.org = ? AND f.period_days = 7
                 AND f.computed_at = (
                     SELECT MAX(f2.computed_at) FROM format_baselines f2
                     WHERE f2.org = f.org AND f2.format_bucket = f.format_bucket
                       AND f2.period_days = f.period_days
                 )
               ORDER BY f.avg_total_lift DESC""",
            (org,),
        ).fetchall()

    results = []
    for r in rows:
        lift = r["avg_total_lift"] or 0
        sample = r["sample_count"] or 0
        authors = r["unique_authors"] or 0

        if lift >= _DOUBLE_DOWN:
            signal = "DOUBLE_DOWN"
        elif lift < _EXECUTION_GAP:
            signal = "EXECUTION_GAP"
        else:
            signal = "PERFORMING"

        rationale = (
            f"{r['format_bucket']} at {lift:.2f}x lift "
            f"({sample} samples, {authors} authors)"
        )
        results.append({
            "format": r["format_bucket"],
            "signal": signal,
            "avg_lift": round(lift, 2),
            "sample_count": sample,
            "unique_authors": authors,
            "rationale": rationale,
        })

    return results


@router.get("/watchlist/{org}")
def watchlist_health(org: str, request: Request):
    """Watchlist health diagnostics — coverage, staleness, scan history."""
    require_org_access(request, org, Action.meta_read)
    meta = get_meta_db()

    # Total authors
    author_row = meta.execute(
        "SELECT COUNT(*) as cnt FROM author_profiles WHERE org = ?",
        (org,),
    ).fetchone()
    total_authors = author_row["cnt"] if author_row else 0

    # Stale authors (last_seen > 14 days ago)
    stale_row = meta.execute(
        """SELECT COUNT(*) as cnt FROM author_profiles
           WHERE org = ? AND last_seen < datetime('now', '-14 days')""",
        (org,),
    ).fetchone()
    stale_authors = stale_row["cnt"] if stale_row else 0

    # Last scan
    scan_row = meta.execute(
        """SELECT completed_at FROM scan_runs
           WHERE org = ?
             AND completed_at IS NOT NULL
             AND (claude_raw IS NULL OR claude_raw NOT LIKE 'FAILED:%')
           ORDER BY completed_at DESC LIMIT 1""",
        (org,),
    ).fetchone()
    last_scan = scan_row["completed_at"] if scan_row else None

    # Total scans
    total_scans_row = meta.execute(
        "SELECT COUNT(*) as cnt FROM scan_runs WHERE org = ?",
        (org,),
    ).fetchone()

    return {
        "total_authors": total_authors,
        "stale_authors": stale_authors,
        "last_scan": last_scan,
        "coverage": round(
            (total_authors - stale_authors) / total_authors, 2
        ) if total_authors else 0,
        "total_scans": total_scans_row["cnt"] if total_scans_row else 0,
    }
