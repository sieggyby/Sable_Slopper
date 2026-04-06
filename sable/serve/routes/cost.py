"""Cost forecast API routes."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from sable.serve.auth import require_org_access
from sable.vault.permissions import Action

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/org/{org_id}/cost-forecast")
def cost_forecast(org_id: str, request: Request):
    """Return cost forecast and budget status for an org."""
    require_org_access(request, org_id, Action.pulse_read)

    from sable.platform.db import get_db
    from sable.platform.cost import get_weekly_spend, get_org_cost_cap

    conn = get_db()
    try:
        # Last 7 days actual spend
        row = conn.execute(
            """SELECT COALESCE(SUM(cost_usd), 0) AS total
               FROM cost_events
               WHERE org_id = ? AND created_at >= datetime('now', '-7 days')""",
            (org_id,),
        ).fetchone()
        last_7d = row[0] if row else 0.0

        # Weekly/monthly estimates (project from last 7d)
        weekly_est = last_7d
        monthly_est = round(weekly_est * 4.33, 2)

        # Budget remaining
        spend = get_weekly_spend(conn, org_id)
        cap = get_org_cost_cap(conn, org_id)
        budget_remaining = max(0.0, cap - spend)

        # Top cost drivers (last 7 days)
        drivers = conn.execute(
            """SELECT call_type, COALESCE(SUM(cost_usd), 0) AS cost_usd
               FROM cost_events
               WHERE org_id = ? AND created_at >= datetime('now', '-7 days')
               GROUP BY call_type
               ORDER BY cost_usd DESC
               LIMIT 10""",
            (org_id,),
        ).fetchall()

        top_drivers = [
            {"call_type": r[0], "cost_usd": round(r[1], 2)}
            for r in drivers
        ]
    finally:
        conn.close()

    return {
        "weekly_estimated_usd": round(weekly_est, 2),
        "monthly_estimated_usd": monthly_est,
        "last_7d_actual_usd": round(last_7d, 2),
        "budget_remaining_usd": round(budget_remaining, 2),
        "top_cost_drivers": top_drivers,
    }
