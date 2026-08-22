"""Approximate per-token USD pricing, keyed by a model-name substring
(SPEC-016, closing SPEC-006 NG-2's cost half).

Provider list prices change independently of this codebase and are not
fetched live -- `PRICING_USD_PER_MILLION` is a hand-maintained snapshot,
not a billing source of truth. `estimate_cost_usd` returns `0.0` for an
unrecognized model rather than guessing, and the caller (`build_trace`)
always labels the number as an estimate.
"""

from __future__ import annotations

from typing import Dict, Tuple

#: model-name substring -> (prompt $/1M tokens, completion $/1M tokens).
#: Longest/most-specific substring wins on a tie (see `_lookup`).
PRICING_USD_PER_MILLION: Dict[str, Tuple[float, float]] = {
    "gemini-flash-latest": (0.10, 0.40),
    "gemini-2.0-flash": (0.10, 0.40),
    "gemini-1.5-flash": (0.075, 0.30),
    "gemini-1.5-pro": (1.25, 5.00),
    "llama-3.3-70b-versatile": (0.59, 0.79),
    "llama-3.1-8b-instant": (0.05, 0.08),
}


def _lookup(model: str) -> Tuple[float, float] | None:
    model = model.lower()
    best: Tuple[float, float] | None = None
    best_len = -1
    for key, rates in PRICING_USD_PER_MILLION.items():
        if key in model and len(key) > best_len:
            best, best_len = rates, len(key)
    return best


def estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Returns 0.0 for an unrecognized model -- silence, not a guess."""
    if not model:
        return 0.0
    rates = _lookup(model)
    if rates is None:
        return 0.0
    prompt_rate, completion_rate = rates
    return round((prompt_tokens * prompt_rate + completion_tokens * completion_rate) / 1_000_000, 6)


__all__ = ["PRICING_USD_PER_MILLION", "estimate_cost_usd"]
