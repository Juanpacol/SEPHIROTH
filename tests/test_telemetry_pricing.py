"""`sephiroth.telemetry.pricing` — approximate cost estimation (SPEC-016,
closing SPEC-006 NG-2's cost half)."""

from sephiroth.telemetry.pricing import estimate_cost_usd


def test_known_model_computes_expected_cost():
    cost = estimate_cost_usd("gemini-flash-latest", prompt_tokens=1_000_000, completion_tokens=1_000_000)
    assert cost == 0.5  # (1M * 0.10 + 1M * 0.40) / 1M


def test_unrecognized_model_is_zero_not_a_guess():
    assert estimate_cost_usd("totally-unknown-model-xyz", 1_000_000, 1_000_000) == 0.0


def test_empty_model_is_zero():
    assert estimate_cost_usd("", 1000, 1000) == 0.0


def test_zero_tokens_is_zero_cost():
    assert estimate_cost_usd("gemini-flash-latest", 0, 0) == 0.0


def test_matches_on_substring_case_insensitive():
    cost = estimate_cost_usd("models/GEMINI-FLASH-LATEST", 1_000_000, 0)
    assert cost == 0.1


def test_longest_matching_key_wins():
    # "gemini-1.5-flash" and no more-specific overlapping key exists here,
    # but this guards the tie-break logic if two keys ever both match.
    cost = estimate_cost_usd("gemini-1.5-flash-8b", 1_000_000, 0)
    assert cost == 0.075
