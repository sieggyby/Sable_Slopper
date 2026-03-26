# last_updated: 2026-03-23
# USD per 1M tokens
CLAUDE_COST_PER_M_TOKENS: dict[str, dict[str, float]] = {
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5-20251001": {"input": 0.25, "output": 1.25},
}
_DEFAULT = {"input": 3.0, "output": 15.0}


def compute_cost(input_tokens: int, output_tokens: int, model: str) -> float:
    rates = CLAUDE_COST_PER_M_TOKENS.get(model, _DEFAULT)
    return (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000
