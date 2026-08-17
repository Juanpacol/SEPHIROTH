"""`truncate` — character-budget truncation (F-035, SPEC-005).

Verifies AC-005-04 (docs/specs/SPEC-005-context-engine.md)."""

from sephiroth.context.budget import TRUNCATION_MARKER, truncate


def test_text_under_limit_is_unchanged():
    assert truncate("short text", 100) == "short text"


def test_text_over_limit_is_truncated_with_marker():
    text = "word " * 100
    result = truncate(text, 20)
    assert len(result) < len(text)
    assert result.endswith(TRUNCATION_MARKER)


def test_truncation_cuts_at_word_boundary_not_mid_word():
    text = "The quick brown fox jumps over the lazy dog"
    result = truncate(text, 12)
    kept = result[: -len(TRUNCATION_MARKER)].strip()
    assert text.startswith(kept)
    assert kept == "" or kept[-1] != " "
    assert all(word in text.split() for word in kept.split())


def test_empty_text_is_unchanged():
    assert truncate("", 10) == ""


def test_no_space_before_limit_falls_back_to_hard_cutoff():
    text = "a" * 50
    result = truncate(text, 10)
    assert result.startswith("a" * 10)
    assert result.endswith(TRUNCATION_MARKER)
