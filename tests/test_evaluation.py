"""Tests for the RAG evaluation harness itself: metric math, dataset
validation, threshold comparison, and the hash-staleness gate."""

import json

import pytest

from intelligence.evaluation import metrics
from intelligence.evaluation.dataset import DatasetError, GoldenCase, load_dataset
from intelligence.evaluation.faithfulness import heuristic_proxy
from intelligence.evaluation.runner import (
    compare_thresholds,
    sha256_transcripts,
)

CASES = [
    GoldenCase(id="a", query="q1", category="golden", relevant_doc_ids=["doc1"]),
    GoldenCase(id="b", query="q2", category="golden", relevant_doc_ids=["doc2"]),
    GoldenCase(id="c", query="q3", category="adversarial-negative", expects_abstention=True),
]


def test_recall_at_k_perfect_when_relevant_doc_in_top_k():
    retrieved = {"a": ["doc1", "doc9"], "b": ["doc2"], "c": []}
    assert metrics.recall_at_k(CASES, retrieved, k=1) == 1.0


def test_recall_at_k_zero_when_relevant_doc_missing():
    retrieved = {"a": ["doc9"], "b": ["doc9"], "c": []}
    assert metrics.recall_at_k(CASES, retrieved, k=5) == 0.0


def test_recall_at_k_excludes_adversarial_cases_from_denominator():
    # Only "a" and "b" have relevant_doc_ids; "c" must not affect the mean.
    retrieved = {"a": ["doc1"], "b": ["doc2"], "c": ["doc1", "doc2"]}
    assert metrics.recall_at_k(CASES, retrieved, k=5) == 1.0


def test_mrr_reciprocal_rank():
    retrieved = {"a": ["docX", "doc1"], "b": ["doc2"], "c": []}
    # a: rank 2 -> 0.5, b: rank 1 -> 1.0, mean = 0.75
    assert metrics.mrr(CASES, retrieved) == pytest.approx(0.75)


def test_mrr_zero_when_not_found():
    retrieved = {"a": [], "b": [], "c": []}
    assert metrics.mrr(CASES, retrieved) == 0.0


def test_citation_metrics_aggregation():
    transcripts = [
        {
            "case_id": "a",
            "answer": "Backed by [Real Source, 2024].",
            "tool_calls": [{"name": "t", "result": {"citation": "Real Source, 2024"}}],
        },
        {
            "case_id": "b",
            "answer": "Backed by [Fake Source].",
            "tool_calls": [],
        },
    ]
    cm = metrics.citation_metrics(transcripts)
    assert cm.verified == 1
    assert cm.fabricated == 1
    assert cm.precision == pytest.approx(0.5)


def test_citation_metrics_no_citations_defaults_precision_to_one():
    transcripts = [{"case_id": "a", "answer": "No citations here.", "tool_calls": []}]
    cm = metrics.citation_metrics(transcripts)
    assert cm.precision == 1.0


def test_citation_recall_counts_expected_substrings():
    cases = [
        GoldenCase(
            id="a",
            query="q",
            category="golden",
            expected_citation_substrings=["ADA Standards", "2024"],
        )
    ]
    transcripts_by_case = {"a": {"answer": "Per ADA Standards of Care in Diabetes, 2024."}}
    assert metrics.citation_recall(cases, transcripts_by_case) == 1.0


def test_citation_recall_partial_match():
    cases = [GoldenCase(id="a", query="q", category="golden", expected_citation_substrings=["Foo", "Bar"])]
    transcripts_by_case = {"a": {"answer": "Mentions Foo but not the other one."}}
    assert metrics.citation_recall(cases, transcripts_by_case) == pytest.approx(0.5)


def test_fabrication_rate_on_adversarial_flags_fabricated_citation():
    cases = [GoldenCase(id="c", query="q", category="adversarial-negative", expects_abstention=True)]
    transcripts_by_case = {"c": {"answer": "See [Made Up Source].", "tool_calls": []}}
    assert metrics.fabrication_rate_on_adversarial(cases, transcripts_by_case) == 1.0


def test_fabrication_rate_zero_when_no_fabrication():
    cases = [GoldenCase(id="c", query="q", category="adversarial-negative", expects_abstention=True)]
    transcripts_by_case = {"c": {"answer": "No relevant evidence was found.", "tool_calls": []}}
    assert metrics.fabrication_rate_on_adversarial(cases, transcripts_by_case) == 0.0


def test_heuristic_proxy_supported_claim():
    answer = "Metformin is the preferred initial agent for type 2 diabetes."
    evidence = ["Metformin is the preferred initial pharmacologic agent for type 2 diabetes."]
    result = heuristic_proxy(answer, evidence)
    assert result.score == 1.0
    assert result.claims_checked == 1


def test_heuristic_proxy_unsupported_claim():
    answer = "Crystals realign your energy meridians for optimal healing."
    evidence = ["Metformin is the preferred initial pharmacologic agent for type 2 diabetes."]
    result = heuristic_proxy(answer, evidence)
    assert result.score == 0.0


def test_heuristic_proxy_no_claims_defaults_to_one():
    assert heuristic_proxy("", []).score == 1.0


def test_load_dataset_validates_doc_ids(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps(
            {
                "cases": [
                    {"id": "x", "query": "q", "category": "golden", "relevant_doc_ids": ["does-not-exist"]}
                ]
            }
        )
    )
    with pytest.raises(DatasetError):
        load_dataset(bad)


def test_load_dataset_real_file_loads_without_error():
    cases = load_dataset()
    assert len(cases) >= 20
    assert any(c.category == "adversarial-negative" for c in cases)


def test_compare_thresholds_pass_and_fail():
    observed = {"recall_at_1": 0.8, "mrr": 0.5}
    thresholds = {"recall_at_1": 0.75, "mrr": 0.6}
    rows = compare_thresholds(observed, thresholds)
    by_metric = {r["metric"]: r["passed"] for r in rows}
    assert by_metric["recall_at_1"] is True
    assert by_metric["mrr"] is False


def test_compare_thresholds_missing_metric_fails():
    rows = compare_thresholds({}, {"recall_at_1": 0.5})
    assert rows[0]["passed"] is False
    assert rows[0]["value"] is None


def test_sha256_transcripts_changes_with_content(tmp_path):
    (tmp_path / "a.json").write_text('{"case_id": "a"}')
    hash1 = sha256_transcripts(tmp_path)
    (tmp_path / "a.json").write_text('{"case_id": "a", "extra": true}')
    hash2 = sha256_transcripts(tmp_path)
    assert hash1 != hash2


def test_sha256_transcripts_order_independent(tmp_path):
    (tmp_path / "a.json").write_text('{"case_id": "a"}')
    (tmp_path / "b.json").write_text('{"case_id": "b"}')
    hash1 = sha256_transcripts(tmp_path)

    tmp_path2_files = sorted(tmp_path.glob("*.json"))
    assert len(tmp_path2_files) == 2
    # Re-hashing the same directory is deterministic regardless of glob order.
    hash2 = sha256_transcripts(tmp_path)
    assert hash1 == hash2
