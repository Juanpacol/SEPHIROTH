"""`mmr_rerank` — lexical Maximal Marginal Relevance (F-035, SPEC-005).

Verifies AC-005-02 (docs/specs/SPEC-005-context-engine.md)."""

from sephiroth.context.rerank import mmr_rerank


def _doc(id_, content, score):
    return {"id": id_, "content": content, "score": score}


def test_fewer_than_two_candidates_returned_unchanged():
    assert mmr_rerank([], top_k=5) == []
    one = [_doc("a", "text", 1.0)]
    assert mmr_rerank(one, top_k=5) == one


def test_top_relevance_candidate_is_selected_first():
    candidates = [
        _doc("low", "diabetes management guideline", 0.2),
        _doc("high", "hypertension treatment guideline", 0.9),
    ]
    result = mmr_rerank(candidates, top_k=2)
    assert result[0]["id"] == "high"


def test_diversity_prefers_dissimilar_second_pick_over_near_duplicate():
    """Two near-duplicate high-scoring docs and one dissimilar lower-scoring
    doc: with heavy diversity weighting, the dissimilar doc should be
    preferred as the second pick over the near-duplicate."""
    candidates = [
        _doc("dup1", "aspirin dosing guidelines for cardiovascular prevention", 0.95),
        _doc("dup2", "aspirin dosing guidelines for cardiovascular disease", 0.94),
        _doc("distinct", "insulin titration protocol for type 1 diabetes", 0.80),
    ]
    result = mmr_rerank(candidates, lambda_mult=0.3, top_k=2)
    assert result[0]["id"] == "dup1"
    assert result[1]["id"] == "distinct"


def test_respects_top_k():
    candidates = [_doc(str(i), f"document number {i}", 1.0 - i * 0.1) for i in range(10)]
    result = mmr_rerank(candidates, top_k=3)
    assert len(result) == 3


def test_missing_content_or_score_does_not_crash():
    candidates = [{"id": "a"}, {"id": "b", "content": "text"}]
    result = mmr_rerank(candidates, top_k=2)
    assert len(result) == 2
