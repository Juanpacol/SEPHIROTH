"""Tests for the runner's `run_ci_mode` (staleness/threshold gate) and
`run_full_mode` (real EvidenceAgent through a FakeOllamaClient) paths —
the parts not already covered by test_evaluation.py's pure-function tests."""

import json

import pytest

from intelligence.evaluation.runner import (
    run_ci_mode,
    run_full_mode,
    sha256_file,
    sha256_transcripts,
)
from tests.conftest import FakeOllamaClient

GOLDEN = {
    "cases": [
        {
            "id": "dm-a1c-target",
            "query": "What A1C goal is appropriate for adults with type 2 diabetes?",
            "category": "golden",
            "relevant_doc_ids": ["ada-2024-hba1c"],
        },
        {
            "id": "adv-unrelated",
            "query": "What do guidelines say about tax filing?",
            "category": "adversarial-negative",
            "relevant_doc_ids": [],
            "expects_abstention": True,
        },
    ]
}

TRANSCRIPT_A1C = {
    "case_id": "dm-a1c-target",
    "answer": "Target A1C is below 7% [ADA Standards of Care in Diabetes, 2024].",
    "tool_calls": [
        {
            "name": "search_clinical_guidelines",
            "arguments": {"query": "A1C goal"},
            "result": {
                "results": [
                    {
                        "id": "ada-2024-hba1c",
                        "content": "An A1C goal for many nonpregnant adults with diabetes of <7%.",
                        "citation": "ADA Standards of Care in Diabetes",
                    }
                ]
            },
        }
    ],
}

TRANSCRIPT_ADV = {"case_id": "adv-unrelated", "answer": "No relevant evidence was found.", "tool_calls": []}


@pytest.fixture
def eval_fixtures(tmp_path):
    dataset_path = tmp_path / "golden.json"
    dataset_path.write_text(json.dumps(GOLDEN))

    transcripts_dir = tmp_path / "transcripts"
    transcripts_dir.mkdir()
    (transcripts_dir / "dm-a1c-target.json").write_text(json.dumps(TRANSCRIPT_A1C))
    (transcripts_dir / "adv-unrelated.json").write_text(json.dumps(TRANSCRIPT_ADV))

    thresholds_path = tmp_path / "thresholds.json"
    thresholds_path.write_text(json.dumps({"recall_at_1": 0.0, "citation_precision": 0.0}))

    results_path = tmp_path / "results" / "latest.json"

    return {
        "dataset_path": dataset_path,
        "transcripts_dir": transcripts_dir,
        "thresholds_path": thresholds_path,
        "results_path": results_path,
    }


def test_run_ci_mode_stale_when_no_results_file(eval_fixtures):
    result = run_ci_mode(**eval_fixtures)
    assert result["stale_results"] is True
    assert result["passed"] is False


def test_run_ci_mode_passes_with_fresh_results(eval_fixtures):
    results_path = eval_fixtures["results_path"]
    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text(
        json.dumps(
            {
                "run": {
                    "dataset_sha256": sha256_file(eval_fixtures["dataset_path"]),
                    "transcripts_sha256": sha256_transcripts(eval_fixtures["transcripts_dir"]),
                },
                "faithfulness": {"llm_judge": 0.5},
            }
        )
    )
    result = run_ci_mode(**eval_fixtures)
    assert result["stale_results"] is False
    assert result["passed"] is True
    assert result["n_cases"] == 2


def test_run_ci_mode_stale_when_dataset_changes_after_results_written(eval_fixtures):
    results_path = eval_fixtures["results_path"]
    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text(
        json.dumps(
            {
                "run": {
                    "dataset_sha256": sha256_file(eval_fixtures["dataset_path"]),
                    "transcripts_sha256": sha256_transcripts(eval_fixtures["transcripts_dir"]),
                },
                "faithfulness": {"llm_judge": 0.5},
            }
        )
    )
    eval_fixtures["dataset_path"].write_text(json.dumps({"cases": GOLDEN["cases"][:1]}))
    result = run_ci_mode(**eval_fixtures)
    assert result["stale_results"] is True


@pytest.mark.asyncio
async def test_run_full_mode_runs_real_agent_and_writes_results(tmp_path):
    dataset_path = tmp_path / "golden.json"
    dataset_path.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "id": "dm-a1c-target",
                        "query": "What A1C goal is appropriate for type 2 diabetes?",
                        "category": "golden",
                        "relevant_doc_ids": ["ada-2024-hba1c"],
                    }
                ]
            }
        )
    )
    transcripts_dir = tmp_path / "transcripts"
    results_path = tmp_path / "results" / "latest.json"

    client = FakeOllamaClient(
        scripts={
            "clinical evidence specialist": [
                ("tool", "search_clinical_guidelines", {"query": "A1C goal", "top_k": 5}),
                ("answer", "Target A1C is below seven percent for most adults."),
            ]
        },
        json_payloads=[{"supported": True}],
    )

    results = await run_full_mode(
        client,
        dataset_path=dataset_path,
        transcripts_dir=transcripts_dir,
        results_path=results_path,
        record=True,
        skip_pubmed=True,
        git_sha="test-sha",
        run_timestamp="2026-01-01T00:00:00Z",
    )

    assert results["run"]["model"] == "fake-model"
    assert results["run"]["git_sha"] == "test-sha"
    assert (transcripts_dir / "dm-a1c-target.json").exists()
    assert results_path.exists()
    assert results["retrieval"]["recall_at_1"] == 1.0


@pytest.mark.asyncio
async def test_run_full_mode_without_record_does_not_write_files(tmp_path):
    dataset_path = tmp_path / "golden.json"
    dataset_path.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "id": "dm-a1c-target",
                        "query": "What A1C goal is appropriate?",
                        "category": "golden",
                        "relevant_doc_ids": ["ada-2024-hba1c"],
                    }
                ]
            }
        )
    )
    transcripts_dir = tmp_path / "transcripts"
    results_path = tmp_path / "results" / "latest.json"

    client = FakeOllamaClient(
        scripts={
            "clinical evidence specialist": [
                ("tool", "search_clinical_guidelines", {"query": "A1C", "top_k": 5}),
                ("answer", "Short answer here."),
            ]
        },
        json_payloads=[{"supported": False}],
    )

    await run_full_mode(
        client,
        dataset_path=dataset_path,
        transcripts_dir=transcripts_dir,
        results_path=results_path,
        record=False,
        skip_pubmed=True,
    )
    assert not results_path.exists()
    assert not transcripts_dir.exists()
