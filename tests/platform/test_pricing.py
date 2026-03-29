"""Tests for sable/shared/pricing.py — pricing dict completeness."""
from __future__ import annotations

# Current Claude models used in Sable Slopper. Add new models here when they are introduced.
_EXPECTED_MODELS = [
    "claude-sonnet-4-6",
    "claude-haiku-4-5-20251001",
]


def test_pricing_dict_contains_all_current_models():
    """All current Claude models must have entries in CLAUDE_COST_PER_M_TOKENS.

    When a new model is introduced, add it to _EXPECTED_MODELS above AND update
    pricing.py with the correct rates. This test prevents silent cost miscalculation
    via the _DEFAULT fallback.
    """
    from sable.shared.pricing import CLAUDE_COST_PER_M_TOKENS

    missing = [m for m in _EXPECTED_MODELS if m not in CLAUDE_COST_PER_M_TOKENS]
    assert not missing, (
        f"Models missing from CLAUDE_COST_PER_M_TOKENS: {missing}. "
        "Add them to sable/shared/pricing.py with correct input/output rates."
    )


def test_pricing_entries_have_positive_rates():
    """Every entry in CLAUDE_COST_PER_M_TOKENS must have positive input and output rates."""
    from sable.shared.pricing import CLAUDE_COST_PER_M_TOKENS

    for model, rates in CLAUDE_COST_PER_M_TOKENS.items():
        assert "input" in rates, f"{model}: missing 'input' rate"
        assert "output" in rates, f"{model}: missing 'output' rate"
        assert rates["input"] > 0, f"{model}: input rate must be > 0"
        assert rates["output"] > 0, f"{model}: output rate must be > 0"


def test_compute_cost_uses_model_rates():
    """compute_cost must use model-specific rates, not the default fallback."""
    from sable.shared.pricing import compute_cost, CLAUDE_COST_PER_M_TOKENS

    model = "claude-haiku-4-5-20251001"
    rates = CLAUDE_COST_PER_M_TOKENS[model]

    # 1M input tokens + 0 output
    cost = compute_cost(1_000_000, 0, model)
    assert abs(cost - rates["input"]) < 0.0001, (
        f"Expected {rates['input']}, got {cost}"
    )
