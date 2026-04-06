"""Churn intervention playbook generation."""
from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field

from sable.churn.prompts import INTERVENTION_SYSTEM, INTERVENTION_USER
from sable.platform.errors import SableError

logger = logging.getLogger(__name__)

SOFT_CAP = 50


@dataclass
class InterventionResult:
    handle: str
    interest_tags: list[str] = field(default_factory=list)
    role_recommendation: str = ""
    spotlight_suggestion: str = ""
    engagement_prompts: list[str] = field(default_factory=list)
    urgency: str = "medium"
    error: str | None = None


def generate_playbook(
    org: str,
    at_risk_members: list[dict],
    conn: sqlite3.Connection,
    *,
    force: bool = False,
    dry_run: bool = False,
) -> list[InterventionResult]:
    """Generate re-engagement playbooks for at-risk members.

    Args:
        org: Org ID for budget tracking.
        at_risk_members: List of dicts with keys: handle, decay_score, topics,
            last_active, role, notes.
        conn: Platform DB connection for budget checks.
        force: Allow >SOFT_CAP members.
        dry_run: Print estimates, no API calls.

    Returns:
        List of InterventionResult, one per member.
    """
    if not at_risk_members:
        return []

    if len(at_risk_members) > SOFT_CAP and not force:
        raise SableError(
            "CHURN_CAP_EXCEEDED",
            f"At-risk list has {len(at_risk_members)} members (cap: {SOFT_CAP}). "
            f"Use --force to proceed.",
        )

    if dry_run:
        return []

    from sable.platform.cost import check_budget
    from sable.shared.api import call_claude_json

    results: list[InterventionResult] = []

    for member in at_risk_members:
        handle = member.get("handle", "unknown")

        # Budget check before each call
        check_budget(conn, org)

        prompt = INTERVENTION_USER.format(
            handle=handle,
            decay_score=member.get("decay_score", "N/A"),
            last_active=member.get("last_active", "unknown"),
            role=member.get("role", "member"),
            topics=", ".join(member.get("topics", [])) if member.get("topics") else "none",
            notes=member.get("notes", ""),
            total_posts=member.get("total_posts_in_window", "unknown"),
            days_active=member.get("days_active", "unknown"),
        )

        try:
            raw = call_claude_json(
                prompt,
                system=INTERVENTION_SYSTEM,
                max_tokens=800,
                org_id=org,
                call_type="churn_intervention",
                budget_check=False,
            )
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                raise ValueError(f"Expected JSON object, got {type(parsed).__name__}")
            results.append(InterventionResult(
                handle=handle,
                interest_tags=parsed.get("interest_tags", []),
                role_recommendation=parsed.get("role_recommendation", ""),
                spotlight_suggestion=parsed.get("spotlight_suggestion", ""),
                engagement_prompts=parsed.get("engagement_prompts", []),
                urgency=parsed.get("urgency", "medium"),
            ))
        except SableError:
            raise
        except Exception as e:
            logger.warning("Churn intervention failed for %s: %s", handle, e)
            results.append(InterventionResult(handle=handle, error=str(e)))

    return results
