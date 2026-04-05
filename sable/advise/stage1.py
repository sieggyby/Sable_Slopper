"""Stage 1: Deterministic input assembly for Twitter strategy brief."""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# SS-20: TrackingMetadata contract validation
try:
    from sable_platform.contracts.tracking import TrackingMetadata
    _HAS_TRACKING_CONTRACT = True
except ImportError:
    _HAS_TRACKING_CONTRACT = False

_KNOWN_SCHEMA_VERSIONS = {1}


class _MetaFallback:
    """Attribute-access wrapper over a raw metadata dict."""

    def __init__(self, data: dict) -> None:
        self._data = data

    def __getattr__(self, name: str) -> Any:
        return self._data.get(name)


def _validate_tracking_meta(meta: dict) -> Any:
    """Validate metadata_json against TrackingMetadata contract.

    Returns a validated TrackingMetadata instance (typed field access).
    Falls back to a plain namespace if sable_platform is not installed.
    """
    if not _HAS_TRACKING_CONTRACT:
        return _MetaFallback(meta)

    try:
        validated = TrackingMetadata.model_validate(meta)
        if validated.schema_version not in _KNOWN_SCHEMA_VERSIONS:
            logger.warning(
                "TrackingMetadata schema_version %d is unknown (known: %s) — "
                "using anyway with forward compatibility",
                validated.schema_version, _KNOWN_SCHEMA_VERSIONS,
            )
        return validated
    except Exception as e:
        logger.warning("TrackingMetadata validation failed, using raw dict: %s", e)
        return _MetaFallback(meta)


def _open_db_readonly(path: Path) -> Optional[sqlite3.Connection]:
    """Open a SQLite database read-only. Returns None if unavailable."""
    try:
        if not path.exists():
            return None
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        logger.warning("stage1: _open_db_readonly failed (path=%s): %s", path, e)
        return None


def _read_profile_file(handle_dir: Path, filename: str) -> str:
    p = handle_dir / filename
    if p.exists():
        try:
            return p.read_text(encoding="utf-8").strip()
        except Exception as e:
            logger.warning("stage1: _read_profile_file failed (path=%s): %s", p, e)
    return "(not configured)"


def _compute_lift(row) -> float:
    likes = row["likes"] or 0
    replies = row["replies"] or 0
    retweets = row["retweets"] or 0
    quotes = row["quotes"] or 0
    bookmarks = row["bookmarks"] or 0
    views = row["views"] or 0
    # why: weights reflect signal strength — quotes > reposts > replies > bookmarks > likes > views
    return (likes * 1.0) + (replies * 3.0) + (retweets * 4.0) + (quotes * 5.0) + (bookmarks * 2.0) + (views * 0.5)


def assemble_input(normalized_handle: str, org_id: str, platform_conn) -> dict:
    """
    Read from pulse.db, meta.db, sable.db (entities, content_items), and profile files.
    Returns a dict with all assembled data and freshness metadata.
    """
    from sable.shared.paths import pulse_db_path, meta_db_path, profile_dir

    result: dict[str, Any] = {
        "handle": normalized_handle,
        "org_id": org_id,
        "profile": {},
        "posts": [],
        "post_freshness": None,
        "pulse_available": False,
        "topics": [],
        "formats": [],
        "meta_scan_date": None,
        "meta_available": False,
        "meta_stale": False,
        "entities": [],
        "content_items": [],
        "tracking_last_sync": None,
        "attribution": None,
        "data_freshness": {
            "pulse_last_track": None,
            "meta_last_scan": None,
            "tracking_last_sync": None,
        },
    }

    # --- Profile files ---
    handle_dir = profile_dir(normalized_handle)
    result["profile"] = {
        "tone": _read_profile_file(handle_dir, "tone.md"),
        "interests": _read_profile_file(handle_dir, "interests.md"),
        "context": _read_profile_file(handle_dir, "context.md"),
        "notes": _read_profile_file(handle_dir, "notes.md"),
    }

    # --- Pulse.db ---
    pulse_conn = _open_db_readonly(pulse_db_path())
    if pulse_conn:
        result["pulse_available"] = True
        # Normalize once for all pulse.db queries
        _norm_handle = normalized_handle if normalized_handle.startswith("@") else f"@{normalized_handle}"
        try:
            rows = pulse_conn.execute(
                """SELECT p.id, p.text, p.posted_at, p.sable_content_type,
                          s.likes, s.retweets, s.replies, s.views, s.bookmarks, s.quotes,
                          s.taken_at
                   FROM posts p
                   JOIN snapshots s ON s.post_id = p.id
                   WHERE p.account_handle = ?
                     AND p.posted_at >= datetime('now', '-14 days')
                     AND s.id = (SELECT MAX(s2.id) FROM snapshots s2 WHERE s2.post_id = p.id)
                   ORDER BY p.posted_at DESC""",
                (_norm_handle,)
            ).fetchall()

            posts = []
            for row in rows:
                eng = _compute_lift(row)
                posts.append({
                    "id": row["id"],
                    "text": row["text"] or "",
                    "posted_at": row["posted_at"] or "",
                    "content_type": row["sable_content_type"] or "unknown",
                    "engagement": eng,
                    "taken_at": row["taken_at"],
                })

            result["posts"] = posts

            # Freshness: latest snapshot taken_at for this handle
            latest_snap = pulse_conn.execute(
                """SELECT MAX(s.taken_at) FROM snapshots s
                   JOIN posts p ON s.post_id = p.id
                   WHERE p.account_handle = ?""",
                (_norm_handle,)
            ).fetchone()[0]
            result["data_freshness"]["pulse_last_track"] = latest_snap
            result["post_freshness"] = latest_snap
        except Exception as e:
            logger.warning("pulse.db read failed: %s", e, exc_info=True)
            result.setdefault("failed_sources", []).append("pulse.db")
            result["pulse_available"] = False
        finally:
            pulse_conn.close()

    # --- Compute lift for posts ---
    if result["posts"]:
        engagements = [p["engagement"] for p in result["posts"]]
        engagements_sorted = sorted(engagements)
        n = len(engagements_sorted)
        if n % 2 == 0:
            median = (engagements_sorted[n // 2 - 1] + engagements_sorted[n // 2]) / 2
        else:
            median = engagements_sorted[n // 2]
        result["median_engagement"] = median
        for p in result["posts"]:
            p["lift"] = p["engagement"] / median if median > 0 else 1.0
    else:
        result["median_engagement"] = 0

    # Check pulse staleness
    if result["post_freshness"]:
        try:
            latest = datetime.fromisoformat(result["post_freshness"].replace("Z", "+00:00"))
            if _now_utc() - latest > timedelta(days=14):
                result["pulse_available"] = False  # treat as stale
        except Exception as e:
            logger.warning("stage1 pulse freshness parse failed for org %s: %s", org_id, e, exc_info=True)
            result["pulse_available"] = False
            result.setdefault("failed_sources", []).append("pulse.freshness")

    # --- meta.db ---
    meta_conn = _open_db_readonly(meta_db_path())
    if meta_conn:
        result["meta_available"] = True
        try:
            scan_row = meta_conn.execute(
                "SELECT id, completed_at FROM scan_runs WHERE org = ? ORDER BY completed_at DESC LIMIT 1",
                (org_id,)
            ).fetchone()

            if scan_row:
                scan_id = scan_row["id"]
                scan_date = scan_row["completed_at"]
                result["data_freshness"]["meta_last_scan"] = scan_date
                result["meta_scan_date"] = scan_date

                # Check staleness
                try:
                    scan_dt = datetime.fromisoformat((scan_date or "").replace("Z", "+00:00"))
                    if _now_utc() - scan_dt > timedelta(days=7):
                        result["meta_stale"] = True
                except Exception as e:
                    logger.warning("stage1 meta scan-date parse failed for org %s: %s", org_id, e, exc_info=True)
                    result["meta_stale"] = True

                # Topic signals
                topics = meta_conn.execute(
                    """SELECT term, mention_count, unique_authors, avg_lift, acceleration
                       FROM topic_signals WHERE org = ? AND scan_id = ?
                       ORDER BY avg_lift DESC LIMIT 20""",
                    (org_id, scan_id)
                ).fetchall()
                result["topics"] = [dict(t) for t in topics]

                # Format baselines
                formats = meta_conn.execute(
                    """SELECT format_bucket, avg_total_lift, sample_count
                       FROM format_baselines WHERE org = ? AND period_days = 7
                       ORDER BY avg_total_lift DESC""",
                    (org_id,)
                ).fetchall()
                result["formats"] = [dict(f) for f in formats]
        except Exception as e:
            logger.warning("meta.db read failed: %s", e, exc_info=True)
            result.setdefault("failed_sources", []).append("meta.db")
            result["meta_available"] = False
        finally:
            meta_conn.close()

    # --- sable.db: entities ---
    platform_ok = True
    try:
        priority_tags = ["cultist_candidate", "bridge_node", "top_contributor"]
        entity_rows: list[Any] = []
        for tag in priority_tags:
            rows = platform_conn.execute(
                """SELECT DISTINCT e.entity_id, e.display_name, e.status
                   FROM entities e
                   JOIN entity_tags t ON e.entity_id = t.entity_id
                   WHERE e.org_id = ? AND t.tag = ? AND t.is_current = 1
                     AND (t.expires_at IS NULL OR t.expires_at > datetime('now'))
                     AND e.status != 'archived'
                   LIMIT 5""",
                (org_id, tag)
            ).fetchall()
            for row in rows:
                if len(entity_rows) >= 5:
                    break
                eid = row["entity_id"]
                if not any(e["entity_id"] == eid for e in entity_rows):
                    handles = platform_conn.execute(
                        "SELECT platform, handle FROM entity_handles WHERE entity_id=?",
                        (eid,)
                    ).fetchall()
                    tags_rows = platform_conn.execute(
                        """SELECT tag FROM entity_tags WHERE entity_id=? AND is_current=1
                           AND (expires_at IS NULL OR expires_at > datetime('now'))""",
                        (eid,)
                    ).fetchall()
                    entity_rows.append({
                        "entity_id": eid,
                        "display_name": row["display_name"] or eid,
                        "status": row["status"],
                        "handles": [dict(h) for h in handles],
                        "tags": [r["tag"] for r in tags_rows],
                    })
        result["entities"] = entity_rows
    except Exception as e:
        logger.warning("sable.db entity read failed: %s", e, exc_info=True)
        result.setdefault("failed_sources", []).append("sable.db entity")
        result["entities"] = []
        platform_ok = False

    # --- sable.db: content_items ---
    try:
        # TODO(sable-tracking): SableTracking must populate posted_at with source publish time.
        # Until then, COALESCE falls back to created_at (ingestion time).
        cutoff = (_now_utc() - timedelta(days=14)).isoformat()
        content_rows = platform_conn.execute(
            """SELECT *, COALESCE(posted_at, created_at) AS source_time
               FROM content_items
               WHERE org_id = ? AND COALESCE(posted_at, created_at) >= ?
               ORDER BY COALESCE(posted_at, created_at) DESC""",
            (org_id, cutoff)
        ).fetchall()

        items = []
        for row in content_rows:
            try:
                meta = json.loads(row["metadata_json"] or "{}")
            except Exception as e:
                logger.warning("stage1 tracker metadata_json parse failed (row skipped): %s", e, exc_info=True)
                meta = {}
            if meta.get("source_tool") == "sable_tracking":
                # Validate against TrackingMetadata contract (SS-20)
                validated = _validate_tracking_meta(meta)
                items.append({
                    "content_type": row["content_type"] or "unknown",
                    "body": row["body"] or "",
                    "created_at": row["created_at"] or "",
                    "source_time": row["source_time"] or "",
                    "entity_id": row["entity_id"],
                    "format_type": validated.format_type,
                    "intent_type": validated.intent_type,
                    "quality_score": validated.quality_score,
                    "engagement_score": validated.engagement_score,
                    "is_reusable_template": validated.is_reusable_template,
                })
        result["content_items"] = items
    except Exception as e:
        logger.warning("sable.db content_items read failed: %s", e, exc_info=True)
        result.setdefault("failed_sources", []).append("sable.db content")
        result["content_items"] = []
        platform_ok = False

    # --- tracking last sync ---
    try:
        sync_row = platform_conn.execute(
            """SELECT MAX(completed_at) FROM sync_runs
               WHERE org_id = ? AND sync_type = 'sable_tracking'""",
            (org_id,)
        ).fetchone()
        result["data_freshness"]["tracking_last_sync"] = sync_row[0] if sync_row else None
    except Exception as e:
        logger.warning("tracking read failed: %s", e, exc_info=True)
        result.setdefault("failed_sources", []).append("tracking")
        platform_ok = False

    # --- Content attribution ---
    try:
        from sable.pulse.attribution import compute_attribution
        attr = compute_attribution(normalized_handle, days=30, org=org_id if org_id else None)
        result["attribution"] = attr
    except Exception as e:
        logger.warning("attribution computation failed: %s", e, exc_info=True)
        result["attribution"] = None

    result["data_quality"] = {
        "pulse_ok": result["pulse_available"],
        "meta_ok": result["meta_available"],
        "platform_ok": platform_ok,
    }

    return result


def _assemble_bridge_section(
    org_id: str,
    platform_conn: sqlite3.Connection,
    meta_conn: Optional[sqlite3.Connection],
) -> str:
    """Assemble bridge node activity section for advise prompt.

    Queries sable.db for entities with 'bridge_node' tag, then meta.db
    for each bridge node's recent engagement. Returns empty string if
    zero bridge nodes or meta.db unavailable.
    """
    try:
        rows = platform_conn.execute(
            """SELECT DISTINCT e.entity_id, e.display_name
               FROM entities e
               JOIN entity_tags t ON e.entity_id = t.entity_id
               WHERE e.org_id = ? AND t.tag = 'bridge_node' AND t.is_current = 1
                 AND (t.expires_at IS NULL OR t.expires_at > datetime('now'))
                 AND e.status != 'archived'
               LIMIT 5""",
            (org_id,),
        ).fetchall()
    except Exception as e:
        logger.warning("_assemble_bridge_section entity query failed: %s", e)
        return ""

    if not rows:
        return ""

    if meta_conn is None:
        return ""

    lines = ["## Bridge Node Activity"]
    for row in rows:
        eid = row["entity_id"]
        name = row["display_name"] or eid

        # Get Twitter handle for this entity
        try:
            handle_row = platform_conn.execute(
                "SELECT handle FROM entity_handles WHERE entity_id = ? AND platform = 'twitter'",
                (eid,),
            ).fetchone()
        except Exception:
            handle_row = None

        if not handle_row:
            lines.append(f"  - {name}: no Twitter handle linked")
            continue

        handle = handle_row["handle"]
        norm = handle if handle.startswith("@") else f"@{handle}"

        # Recent engagement from meta.db
        try:
            stats = meta_conn.execute(
                """SELECT COUNT(*) as cnt,
                          AVG(COALESCE(total_lift, 0)) as avg_lift
                   FROM scanned_tweets
                   WHERE author_handle = ? AND org = ?
                     AND posted_at >= datetime('now', '-14 days')""",
                (norm, org_id),
            ).fetchone()
            cnt = stats["cnt"] if stats else 0
            avg_lift = stats["avg_lift"] if stats and stats["avg_lift"] else 0
            if cnt > 0:
                lines.append(f"  - {name} ({norm}): {cnt} tweets, avg lift {avg_lift:.1f}x")
            else:
                lines.append(f"  - {name} ({norm}): no recent activity")
        except Exception as e:
            logger.warning("_assemble_bridge_section meta query failed for %s: %s", norm, e)
            lines.append(f"  - {name} ({norm}): data unavailable")

    lines.append("")
    return "\n".join(lines)


def _assemble_community_language(
    org_id: str,
    platform_conn: sqlite3.Connection,
) -> str:
    """Assemble community language signal section from CultGrader diagnostic data.

    Queries diagnostic_runs for the latest completed run with non-null language
    fields. 14-day freshness gate. Returns empty string if no data, stale, or
    columns don't exist yet (pre-migration).
    """
    try:
        row = platform_conn.execute(
            """SELECT language_arc_phase, emergent_cultural_terms_json,
                      mantra_candidates_json, started_at
               FROM diagnostic_runs
               WHERE org_id = ? AND started_at IS NOT NULL
                 AND started_at > datetime('now', '-14 days')
               ORDER BY started_at DESC LIMIT 1""",
            (org_id,),
        ).fetchone()
    except Exception as e:
        # Columns may not exist yet (pre-migration)
        logger.debug("_assemble_community_language query failed (expected pre-migration): %s", e)
        return ""

    if not row:
        return ""

    arc_phase = row["language_arc_phase"] if row["language_arc_phase"] else None
    terms_json = row["emergent_cultural_terms_json"] if row["emergent_cultural_terms_json"] else None
    mantras_json = row["mantra_candidates_json"] if row["mantra_candidates_json"] else None

    if not any([arc_phase, terms_json, mantras_json]):
        return ""

    lines = ["## Community Language Signal"]

    if arc_phase:
        lines.append(f"Language arc phase: {arc_phase}")

    if terms_json:
        try:
            terms = json.loads(terms_json)
            if isinstance(terms, list) and terms:
                lines.append(f"Emergent cultural terms: {', '.join(str(t) for t in terms[:10])}")
        except (json.JSONDecodeError, TypeError):
            pass

    if mantras_json:
        try:
            mantras = json.loads(mantras_json)
            if isinstance(mantras, list) and mantras:
                lines.append(f"Mantra candidates: {', '.join(str(m) for m in mantras[:5])}")
        except (json.JSONDecodeError, TypeError):
            pass

    lines.append("")
    return "\n".join(lines)


def render_summary(data: dict) -> str:
    """Build the structured text summary for Claude."""
    lines = []
    profile = data["profile"]

    # Profile
    lines.append("## Account Profile")
    lines.append(f"Tone: {profile.get('tone', '(not configured)')[:500]}")
    lines.append(f"Interests: {profile.get('interests', '(not configured)')[:500]}")
    lines.append(f"Context: {profile.get('context', '(not configured)')[:500]}")
    lines.append("")

    # Post performance
    posts = data.get("posts", [])
    pulse_available = data.get("pulse_available", False)
    freshness = data.get("data_freshness", {})

    if not pulse_available and freshness.get("pulse_last_track"):
        lines.append("## Post Performance")
        lines.append("*Performance data stale. Run 'sable pulse track' to refresh.*")
        lines.append("")
    elif pulse_available and len(posts) >= 5:
        lines.append(f"## Post Performance ({len(posts)} posts, last 14 days)")
        # Top 5 by lift
        top5 = sorted(posts, key=lambda p: p.get("lift", 0), reverse=True)[:5]
        lines.append("Top 5 by lift:")
        for p in top5:
            text_exc = (p["text"] or "")[:80]
            lines.append(f'  - "{text_exc}" ({p["posted_at"][:10]}) — lift: {p.get("lift", 0):.2f}, format: {p["content_type"]}')
        lines.append(f"Median engagement: {data.get('median_engagement', 0):.1f}")
        if len(posts) >= 10:
            # Worst format
            format_eng: dict[str, Any] = {}
            for p in posts:
                ft = p["content_type"]
                if ft not in format_eng:
                    format_eng[ft] = []
                format_eng[ft].append(p.get("lift", 0))
            worst: Any = min(format_eng.items(), key=lambda x: sum(x[1]) / len(x[1]), default=(None, []))
            if worst[0]:
                avg = sum(worst[1]) / len(worst[1])
                lines.append(f"Worst format: {worst[0]} — avg lift: {avg:.2f}")
        lines.append("")

    # Content Attribution
    attr = data.get("attribution")
    if attr and attr.sable_posts >= 5:
        lines.append("## Content Attribution (last 30 days)")
        lines.append(
            f"Sable-produced: {attr.sable_posts} of {attr.total_posts} posts "
            f"({attr.sable_share_of_posts:.0%}), generating {attr.sable_share_of_engagement:.0%} of total engagement."
        )
        if attr.sable_lift_vs_organic is not None:
            lines.append(
                f"Sable avg engagement: {attr.sable_avg_engagement:.0f} "
                f"vs organic: {attr.organic_avg_engagement:.0f} ({attr.sable_lift_vs_organic:+.0%})."
            )
        if attr.meta_available and attr.meta_lift is not None:
            lines.append(
                f"Meta-informed content ({attr.meta_informed_posts} of {attr.sable_posts} Sable posts): "
                f"avg {attr.meta_informed_avg:.0f} vs non-meta {attr.non_meta_informed_avg:.0f} ({attr.meta_lift:+.0%})."
            )
        lines.append("")

    # Pulse Meta Trends
    meta_available = data.get("meta_available", False)
    meta_stale = data.get("meta_stale", False)
    meta_scan_date = data.get("meta_scan_date", "")
    topics = data.get("topics", [])
    formats = data.get("formats", [])

    if meta_available or meta_stale:
        lines.append("## Pulse Meta Trends")
        if meta_stale and meta_scan_date:
            lines.append(f"*Trend data last updated {(meta_scan_date or '')[:10]} — may be outdated.*")

        surging = [t for t in topics
                   if t.get("acceleration", 0) > 0
                   and t.get("unique_authors", 0) >= 3
                   and t.get("avg_lift", 0) >= 1.5]
        if surging:
            lines.append("Surging topics (acceleration > 0, unique_authors >= 3, avg_lift >= 1.5):")
            for t in surging[:5]:
                lines.append(f"  - {t['term']}: lift {t['avg_lift']:.2f}, acceleration {t['acceleration']:.2f}")
        else:
            lines.append("Insufficient trend data.")

        if formats:
            lines.append("Top formats by lift:")
            for f in formats[:5]:
                lines.append(f"  - {f['format_bucket']}: avg lift {f['avg_total_lift']:.2f}")
        lines.append("")

    # Entity graph
    entities = data.get("entities", [])
    if entities:
        lines.append("## Entity Graph")
        for e in entities[:5]:
            twitter_handle = next(
                (h["handle"] for h in e.get("handles", []) if h["platform"] == "twitter"), ""
            )
            handle_str = f" (@{twitter_handle})" if twitter_handle else ""
            tags_str = ", ".join(e.get("tags", []))
            lines.append(f"  - {e['display_name']}{handle_str} — tags: {tags_str}")
        lines.append("")

    # Community content
    content_items = data.get("content_items", [])
    if content_items:
        lines.append("## Community Content (last 14 days)")
        for c in content_items[:5]:
            lines.append(f"  - [{c['content_type']}] {(c['body'] or '')[:80]} ({c['created_at'][:10]})")
        lines.append("")

    # Data freshness footer
    lines.append("## Data Freshness")
    lines.append(f"pulse_last_track: {freshness.get('pulse_last_track', 'null')}")
    lines.append(f"meta_last_scan: {freshness.get('meta_last_scan', 'null')}")
    lines.append(f"tracking_last_sync: {freshness.get('tracking_last_sync', 'null')}")

    return "\n".join(lines)
