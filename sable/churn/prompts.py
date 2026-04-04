"""Prompt templates for churn intervention playbook generation."""
from __future__ import annotations

INTERVENTION_SYSTEM = """\
You are a crypto community re-engagement strategist for Sable.
Given an at-risk community member's profile, generate a targeted re-engagement playbook.
Be specific, actionable, and grounded in their known interests and activity patterns.
Do NOT suggest generic "reach out" actions — every recommendation must reference
something concrete from the member's data."""

INTERVENTION_USER = """\
Generate a re-engagement playbook for this at-risk community member.

Handle: {handle}
Decay score: {decay_score}
Last active: {last_active}
Role: {role}
Topics of interest: {topics}
Additional notes: {notes}

Respond with a JSON object containing:
- "handle": the member handle
- "interest_tags": list of 3-5 interest-matched tags for targeting content
- "role_recommendation": a specific role or responsibility to offer them
- "spotlight_suggestion": a concrete way to spotlight this member publicly
- "engagement_prompts": list of 3-5 specific conversation starters or content ideas to re-engage them
- "urgency": "high", "medium", or "low" based on decay score and role importance"""
