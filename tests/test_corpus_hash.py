"""Tests for the embeddings-artifact staleness hash — must change whenever
the corpus or golden-set queries change, and stay stable otherwise."""

import json

from data.embeddings.corpus_hash import _golden_queries, compute_corpus_sha256


def test_hash_is_deterministic_across_calls():
    assert compute_corpus_sha256() == compute_corpus_sha256()


def test_hash_changes_when_golden_queries_change(tmp_path):
    original = {"cases": [{"query": "What A1C goal is appropriate?"}]}
    changed = {"cases": [{"query": "A totally different question entirely?"}]}

    path_a = tmp_path / "golden_a.json"
    path_b = tmp_path / "golden_b.json"
    path_a.write_text(json.dumps(original))
    path_b.write_text(json.dumps(changed))

    assert compute_corpus_sha256(path_a) != compute_corpus_sha256(path_b)


def test_hash_is_insensitive_to_query_order(tmp_path):
    forward = {"cases": [{"query": "first question"}, {"query": "second question"}]}
    backward = {"cases": [{"query": "second question"}, {"query": "first question"}]}

    path_a = tmp_path / "golden_a.json"
    path_b = tmp_path / "golden_b.json"
    path_a.write_text(json.dumps(forward))
    path_b.write_text(json.dumps(backward))

    assert compute_corpus_sha256(path_a) == compute_corpus_sha256(path_b)


def test_golden_queries_extracts_query_field(tmp_path):
    path = tmp_path / "golden.json"
    path.write_text(json.dumps({"cases": [{"query": "q1", "id": "x"}, {"query": "q2", "id": "y"}]}))
    assert _golden_queries(path) == ["q1", "q2"]
