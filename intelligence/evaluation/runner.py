"""Evaluation runner — the two modes described in `run.py`'s CLI help.

`EvalRunner` is deliberately split into small, independently testable
methods rather than one monolithic `run()`, so `tests/test_evaluation.py`
can exercise each piece (hashing, threshold comparison, retrieval scoring)
without needing a full agent run.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from data.rag import RAGPipeline
from intelligence.evaluation import metrics
from intelligence.evaluation.dataset import GoldenCase, load_dataset
from intelligence.evaluation.faithfulness import heuristic_proxy

EVAL_DIR = Path(__file__).parent
DATASET_PATH = EVAL_DIR / "datasets" / "golden.json"
TRANSCRIPTS_DIR = EVAL_DIR / "transcripts"
RESULTS_PATH = EVAL_DIR / "results" / "latest.json"
THRESHOLDS_PATH = EVAL_DIR / "thresholds.json"

RETRIEVAL_K_VALUES = (1, 3, 5)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_transcripts(transcripts_dir: Path = TRANSCRIPTS_DIR) -> str:
    """Stable hash over every transcript file's content, order-independent."""
    digest = hashlib.sha256()
    for path in sorted(transcripts_dir.glob("*.json")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def load_transcripts(transcripts_dir: Path = TRANSCRIPTS_DIR) -> List[Dict[str, Any]]:
    return [json.loads(p.read_text()) for p in sorted(transcripts_dir.glob("*.json"))]


def load_thresholds(path: Path = THRESHOLDS_PATH) -> Dict[str, float]:
    return json.loads(path.read_text())


def extract_evidence_texts(tool_calls: List[Dict[str, Any]]) -> List[str]:
    """Guideline excerpt text a transcript actually retrieved, from
    `search_clinical_guidelines` tool results (the shape returned by
    `intelligence.mcp.rag_server`)."""
    texts: List[str] = []
    for call in tool_calls:
        if call.get("name") != "search_clinical_guidelines":
            continue
        result = call.get("result") or {}
        for hit in result.get("results", []):
            if isinstance(hit, dict) and hit.get("content"):
                texts.append(hit["content"])
    return texts


def retrieved_ids_by_case(
    cases: List[GoldenCase], pipeline: Optional[RAGPipeline] = None, top_k: int = 5
) -> Dict[str, List[str]]:
    pipeline = pipeline or RAGPipeline()
    return {case.id: [hit["id"] for hit in pipeline.retrieve(case.query, top_k=top_k)] for case in cases}


def compute_retrieval_metrics(
    cases: List[GoldenCase], pipeline: Optional[RAGPipeline] = None
) -> Dict[str, float]:
    ids_by_case = retrieved_ids_by_case(cases, pipeline, top_k=max(RETRIEVAL_K_VALUES))
    result = {f"recall_at_{k}": metrics.recall_at_k(cases, ids_by_case, k) for k in RETRIEVAL_K_VALUES}
    result["mrr"] = metrics.mrr(cases, ids_by_case)
    return result


def compute_replay_metrics(cases: List[GoldenCase], transcripts: List[Dict[str, Any]]) -> Dict[str, Any]:
    transcripts_by_case = {t["case_id"]: t for t in transcripts}
    cm = metrics.citation_metrics(transcripts)

    proxy_scores = []
    for t in transcripts:
        proxy = heuristic_proxy(t["answer"], extract_evidence_texts(t.get("tool_calls", [])))
        if proxy.claims_checked:
            proxy_scores.append(proxy.score)

    return {
        "citation": cm.as_dict(),
        "citation_recall": metrics.citation_recall(cases, transcripts_by_case),
        "fabrication_rate_adversarial": metrics.fabrication_rate_on_adversarial(cases, transcripts_by_case),
        "faithfulness_heuristic_proxy": (sum(proxy_scores) / len(proxy_scores) if proxy_scores else 0.0),
    }


def compare_thresholds(observed: Dict[str, float], thresholds: Dict[str, float]) -> List[Dict[str, Any]]:
    """Return one row per gated metric: pass/fail + the delta. A metric in
    `thresholds` but absent from `observed` is treated as a failure."""
    rows = []
    for name, minimum in thresholds.items():
        value = observed.get(name)
        passed = value is not None and value >= minimum
        rows.append(
            {
                "metric": name,
                "value": value,
                "threshold": minimum,
                "passed": passed,
            }
        )
    return rows


def run_ci_mode(
    dataset_path: Path = DATASET_PATH,
    transcripts_dir: Path = TRANSCRIPTS_DIR,
    results_path: Path = RESULTS_PATH,
    thresholds_path: Path = THRESHOLDS_PATH,
) -> Dict[str, Any]:
    """Deterministic, offline evaluation: retrieval metrics from live code +
    golden dataset, replay metrics from committed transcripts, faithfulness
    (LLM judge) pulled from the committed `results/latest.json` after
    verifying it isn't stale."""
    cases = load_dataset(dataset_path)
    transcripts = load_transcripts(transcripts_dir)
    thresholds = load_thresholds(thresholds_path)

    observed: Dict[str, Any] = {}
    observed.update(compute_retrieval_metrics(cases))
    replay = compute_replay_metrics(cases, transcripts)
    observed["citation_precision"] = replay["citation"]["precision"]

    stale = True
    results_data: Dict[str, Any] = {}
    if results_path.exists():
        results_data = json.loads(results_path.read_text())
        run_meta = results_data.get("run", {})
        current_dataset_hash = sha256_file(dataset_path)
        current_transcripts_hash = sha256_transcripts(transcripts_dir)
        stale = (
            run_meta.get("dataset_sha256") != current_dataset_hash
            or run_meta.get("transcripts_sha256") != current_transcripts_hash
        )
        if not stale:
            observed["faithfulness_llm_judge"] = results_data.get("faithfulness", {}).get("llm_judge")

    rows = compare_thresholds(observed, thresholds)
    passed = all(row["passed"] for row in rows) and not stale

    return {
        "mode": "ci",
        "passed": passed,
        "stale_results": stale,
        "observed": observed,
        "replay": replay,
        "threshold_rows": rows,
        "n_cases": len(cases),
    }


async def run_full_mode(
    client: Any,
    dataset_path: Path = DATASET_PATH,
    transcripts_dir: Path = TRANSCRIPTS_DIR,
    results_path: Path = RESULTS_PATH,
    record: bool = False,
    skip_pubmed: bool = False,
    git_sha: str = "unknown",
    run_timestamp: str = "",
) -> Dict[str, Any]:
    """Run the real Evidence Agent against a live Ollama `client` for every
    golden case. With `record=True`, overwrites `transcripts/<case_id>.json`
    and `results/latest.json` — this is the only path that touches Ollama."""
    from intelligence.agents import EvidenceAgent
    from intelligence.evaluation.faithfulness import judge_llm

    cases = load_dataset(dataset_path)

    agent = EvidenceAgent(client)
    if skip_pubmed:
        agent.allowed_tools = ["search_clinical_guidelines"]

    transcripts: List[Dict[str, Any]] = []
    for case in cases:
        chat_result = await agent.run(case.query)
        transcripts.append(
            {
                "case_id": case.id,
                "answer": chat_result.content,
                "tool_calls": chat_result.tool_calls,
            }
        )

    if record:
        transcripts_dir.mkdir(parents=True, exist_ok=True)
        for t in transcripts:
            (transcripts_dir / f"{t['case_id']}.json").write_text(json.dumps(t, indent=2))

    retrieval = compute_retrieval_metrics(cases)
    replay = compute_replay_metrics(cases, transcripts)

    faithfulness_scores = []
    per_case_faithfulness = []
    for t in transcripts:
        evidence_texts = extract_evidence_texts(t["tool_calls"])
        judged = await judge_llm(t["answer"], evidence_texts, client)
        if judged.claims_checked:
            faithfulness_scores.append(judged.score)
        per_case_faithfulness.append(
            {"id": t["case_id"], "score": judged.score, "claims_checked": judged.claims_checked}
        )
    faithfulness_llm_judge = (
        sum(faithfulness_scores) / len(faithfulness_scores) if faithfulness_scores else 0.0
    )

    results = {
        "run": {
            "mode": "full",
            "timestamp": run_timestamp,
            "model": getattr(client, "model", "unknown"),
            "git_sha": git_sha,
            "n_cases": len(cases),
            "dataset_sha256": sha256_file(dataset_path),
            "transcripts_sha256": sha256_transcripts(transcripts_dir) if record else "",
        },
        "retrieval": retrieval,
        "citation": replay["citation"],
        "faithfulness": {
            "llm_judge": round(faithfulness_llm_judge, 4),
            "heuristic_proxy": round(replay["faithfulness_heuristic_proxy"], 4),
            "claims_checked": sum(f["claims_checked"] for f in per_case_faithfulness),
        },
        "per_case": per_case_faithfulness,
    }

    if record:
        results_path.parent.mkdir(parents=True, exist_ok=True)
        results_path.write_text(json.dumps(results, indent=2))

    return results
