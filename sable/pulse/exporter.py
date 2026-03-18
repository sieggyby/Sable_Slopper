"""CSV and JSON export for pulse data."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from sable.pulse.db import get_posts_for_account, get_latest_snapshot
from sable.pulse.scorer import score_post


def export_csv(handle: str, output_path: str, followers: int = 1000) -> None:
    """Export performance data as CSV."""
    posts = get_posts_for_account(handle, limit=1000)
    rows = []
    for post in posts:
        snap = get_latest_snapshot(post["id"])
        if not snap:
            continue
        scores = score_post(snap, followers=followers)
        rows.append({
            "post_id": post["id"],
            "account": handle,
            "posted_at": post.get("posted_at", ""),
            "content_type": post.get("sable_content_type", "unknown"),
            "text": post.get("text", "")[:200],
            **scores,
        })

    if not rows:
        print(f"No data for {handle}")
        return

    fieldnames = list(rows[0].keys())
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Exported {len(rows)} rows to {output_path}")


def export_json(handle: str, output_path: str, followers: int = 1000) -> None:
    """Export performance data as JSON."""
    posts = get_posts_for_account(handle, limit=1000)
    rows = []
    for post in posts:
        snap = get_latest_snapshot(post["id"])
        if not snap:
            continue
        scores = score_post(snap, followers=followers)
        rows.append({
            "post_id": post["id"],
            "account": handle,
            "posted_at": post.get("posted_at", ""),
            "content_type": post.get("sable_content_type", "unknown"),
            "text": post.get("text", ""),
            **scores,
        })

    with open(output_path, "w") as f:
        json.dump(rows, f, indent=2)

    print(f"Exported {len(rows)} records to {output_path}")
