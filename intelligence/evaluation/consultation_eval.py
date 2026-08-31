"""Coherence eval for the text consultation pipeline (Evidence + patient-
context agents) — the chat/tool-calling model configured via
`settings.llm_provider` (today: local Ollama, qwen3:8b — see
`platform/core/config.py`).

    PYTHONPATH=.:platform .venv/bin/python -m intelligence.evaluation.consultation_eval

Runs every case in `consultation_golden.json` through the real multi-agent
pipeline (`sephiroth.runtime.run_consultation`, in-process — no HTTP, no
auth) and checks, per case:

1. **No fabricated citations** — `citation_report.fabricated` must be
   empty. Citation Guard already computes this server-side; this eval
   just asserts it stays at zero across the golden set, the same way
   `imaging_eval.py` asserts zero cross-region hallucination.
2. **Keyword grounding** — the answer mentions at least one term
   consistent with the real evidence/patient data for this case
   (`must_mention_any`).
3. **No cross-patient/off-record hallucination** — for `patient_grounded`
   cases, the answer must never mention a medication or value that
   belongs to a *different* patient or was never in this patient's
   record (`must_not_mention`). This is the direct hallucination
   signal: naming Patient B's warfarin while answering about Patient A
   is confabulation, not a vague miss.
4. **Sane abstention** — a case with real, retrievable evidence
   (`evidence_library`, `patient_grounded` with full context) should
   not silently abstain; an "abstain"/"partial" here would mean the
   pipeline is failing to use evidence it actually has.

Each local run is slow (this hardware's qwen3:8b ceiling — see the
session's own latency investigation), so this is a manual/CI-optional
harness, same posture as `imaging_eval.py` and the RAG harness's
`--mode full`, not something pytest runs on every commit.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

_HERE = Path(__file__).parent
GOLDEN_PATH = _HERE / "consultation_golden.json"
RESULTS_PATH = _HERE / "results" / "consultation_latest.json"

THRESHOLDS = {
    "citation_fabrication_free_rate": 1.0,
    "keyword_grounding_rate": 1.0,
    "hallucination_free_rate": 1.0,
    "sane_abstention_rate": 1.0,
}


@dataclass
class CaseResult:
    case_id: str
    family: str
    answer: str
    abstention_status: str
    fabricated_citations: List[str]
    matched_keywords: List[str]
    matched_forbidden: List[str] = field(default_factory=list)
    citation_fabrication_free: bool = True
    keyword_grounded: bool = False
    hallucination_free: bool = True
    sane_abstention: bool = True


async def run_case(case: dict) -> CaseResult:
    from sephiroth.models import get_llm_client
    from sephiroth.runtime import run_consultation

    client = get_llm_client()
    state = await run_consultation(
        client,
        query=case["query"],
        patient_id=case.get("patient_id") or "",
        context=case.get("context") or {},
    )

    answer = state.get("final_answer", "") or ""
    text = answer.lower()

    fabricated = (state.get("citation_report") or {}).get("fabricated", [])
    abstention_status = (state.get("abstention") or {}).get("status", "answer")

    must_mention = case.get("must_mention_any", [])
    matched_keywords = [kw for kw in must_mention if kw.lower() in text]

    must_not_mention = case.get("must_not_mention", [])
    matched_forbidden = [kw for kw in must_not_mention if kw.lower() in text]

    result = CaseResult(
        case_id=case["id"],
        family=case["family"],
        answer=answer,
        abstention_status=abstention_status,
        fabricated_citations=fabricated,
        matched_keywords=matched_keywords,
        matched_forbidden=matched_forbidden,
    )
    result.citation_fabrication_free = len(fabricated) == 0
    result.keyword_grounded = len(matched_keywords) > 0 if must_mention else True
    result.hallucination_free = len(matched_forbidden) == 0
    result.sane_abstention = abstention_status == "answer"
    return result


def _aggregate(results: List[CaseResult]) -> dict:
    n = len(results)
    metrics = {
        "citation_fabrication_free_rate": sum(r.citation_fabrication_free for r in results) / n,
        "keyword_grounding_rate": sum(r.keyword_grounded for r in results) / n,
        "hallucination_free_rate": sum(r.hallucination_free for r in results) / n,
        "sane_abstention_rate": sum(r.sane_abstention for r in results) / n,
    }
    threshold_rows = [
        {"metric": k, "value": v, "threshold": THRESHOLDS[k], "passed": v >= THRESHOLDS[k]}
        for k, v in metrics.items()
    ]
    return {
        "n_cases": n,
        "metrics": metrics,
        "threshold_rows": threshold_rows,
        "passed": all(row["passed"] for row in threshold_rows),
    }


def _print_report(results: List[CaseResult], summary: dict) -> None:
    print("\n=== Per-case detail ===")
    for r in results:
        flags = []
        if not r.citation_fabrication_free:
            flags.append(f"fabricated citations: {r.fabricated_citations}")
        if not r.keyword_grounded:
            flags.append("no expected keyword found — answer may be ungrounded")
        if not r.hallucination_free:
            flags.append(f"hallucinated off-record terms: {r.matched_forbidden}")
        if not r.sane_abstention:
            flags.append(f"unexpected abstention status: {r.abstention_status}")

        status = "PASS" if not flags else "FAIL"
        print(f"[{status}] {r.case_id} ({r.family})" + (f" — {'; '.join(flags)}" if flags else ""))
        print(f"    answer: {r.answer[:160]}{'…' if len(r.answer) > 160 else ''}")

    print("\n=== Aggregate ===")
    print("| Metric | Value | Threshold | Status |")
    print("|---|---|---|---|")
    for row in summary["threshold_rows"]:
        status = "PASS" if row["passed"] else "FAIL"
        print(f"| {row['metric']} | {row['value']:.3f} | {row['threshold']:.3f} | {status} |")
    print(f"\nOverall: {'PASS' if summary['passed'] else 'FAIL'}")


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--record", action="store_true", help="Write results/consultation_latest.json")
    parser.add_argument("--case", help="Run only this case id")
    args = parser.parse_args()

    sys.path.insert(0, ".")
    sys.path.insert(0, "platform")

    golden = json.loads(GOLDEN_PATH.read_text())
    cases = golden["cases"]
    if args.case:
        cases = [c for c in cases if c["id"] == args.case]
        if not cases:
            print(f"No case named {args.case!r}")
            return 1

    print(f"Running consultation coherence eval on {len(cases)} case(s) "
          f"(each is a full multi-agent consultation — slow on local hardware)...\n")

    results = []
    for case in cases:
        print(f"  {case['id']}...", end=" ", flush=True)
        result = await run_case(case)
        results.append(result)
        print("done")

    summary = _aggregate(results)
    _print_report(results, summary)

    if args.record:
        RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        RESULTS_PATH.write_text(json.dumps({"summary": summary, "cases": [asdict(r) for r in results]}, indent=2))
        print(f"\nWrote {RESULTS_PATH}")

    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
