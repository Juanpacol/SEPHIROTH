"""Vision hallucination/consistency eval for medical imaging analysis.

    PYTHONPATH=.:platform .venv/bin/python -m intelligence.evaluation.imaging_eval

Runs every case in `imaging_golden.json` (real, public-domain images with
known modality/anatomy, stored in `real_data/imaging/samples/`) through the
vision model **twice**, independently,
and checks four things per run:

1. **Modality correctness** — does the model's own modality guess match the
   known ground truth (xray/ct/mri/pathology)? A wrong guess means the model
   is confusing image types, not just phrasing things differently.
2. **Anatomical grounding** — does the free-text description mention at
   least one term consistent with the image's real anatomical region?
3. **No cross-region hallucination** — does the description avoid terms
   belonging to a *different* region/modality (e.g. a brain MRI description
   mentioning "abdomen")? This is the direct hallucination signal: unlike a
   vague miss, naming the wrong anatomy is confabulation.
4. **No confident diagnosis** — the system prompt (`DESCRIPTION_PROMPT` in
   `intelligence/mcp/vision_server.py`) explicitly asks for a description,
   not a diagnosis; this flags language that crosses that line
   ("confirmed diagnosis", "patient has X", "this is cancer").

Run 1 vs run 2 agreement on modality is the **consistency** check — real
non-determinism (temperature > 0) means two honest calls on the same image
can occasionally disagree; a model that hallucinates a specific finding
tends to do it inconsistently across calls, so requiring both runs to agree
catches that even without a human reviewing every description.

This intentionally does NOT use pytest / run in CI: every case is a real
model call against whatever `settings.llm_provider` is configured to
(Gemini or Ollama — same `get_llm_client()` singleton the app itself uses),
same posture as the RAG harness's `--mode full` (`intelligence/evaluation/run.py`).
Wire results into `results/imaging_latest.json` for manual review.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import mimetypes
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).parent
GOLDEN_PATH = _HERE / "imaging_golden.json"
RESULTS_PATH = _HERE / "results" / "imaging_latest.json"
IMAGE_DIR = Path(__file__).parent.parent.parent / "real_data" / "imaging" / "samples"

# Language that crosses from "describing what's visible" into "diagnosing" —
# the system prompt explicitly forbids this; any match is a finding, not a
# style nitpick.
_DIAGNOSIS_PATTERNS = [
    re.compile(r"\bconfirmed diagnosis\b", re.I),
    re.compile(r"\bdefinitive(?:ly)? diagnos\w*\b", re.I),
    re.compile(r"\bpatient has\b", re.I),
    re.compile(r"\bthis (?:is|confirms)\s+(?:a\s+)?(?:case of\s+)?cancer\b", re.I),
    re.compile(r"\bdiagnos(?:is|ed) (?:of|with)\b", re.I),
]

# Threshold gates — see module docstring for what each check means.
THRESHOLDS = {
    "modality_accuracy": 1.0,
    "anatomy_grounding": 1.0,
    "hallucination_free_rate": 1.0,
    "no_diagnosis_rate": 1.0,
    "consistency_rate": 1.0,
}


@dataclass
class RunResult:
    description: str
    modality_guess: str
    modality_correct: bool
    anatomy_grounded: bool
    hallucination_free: bool
    no_diagnosis_language: bool
    matched_forbidden: list[str] = field(default_factory=list)


@dataclass
class CaseResult:
    case_id: str
    filename: str
    expected_modality: str
    run1: RunResult
    run2: RunResult
    consistent: bool


def _score_description(description: str, case: dict, modality_guess: str) -> RunResult:
    text = description.lower()
    modality_correct = modality_guess == case["modality"]
    anatomy_grounded = any(kw in text for kw in case["must_mention_any"])
    matched_forbidden = [kw for kw in case["must_not_mention"] if kw in text]
    hallucination_free = len(matched_forbidden) == 0
    no_diagnosis_language = not any(p.search(description) for p in _DIAGNOSIS_PATTERNS)

    return RunResult(
        description=description,
        modality_guess=modality_guess,
        modality_correct=modality_correct,
        anatomy_grounded=anatomy_grounded,
        hallucination_free=hallucination_free,
        no_diagnosis_language=no_diagnosis_language,
        matched_forbidden=matched_forbidden,
    )


async def _describe_and_classify(client, image_bytes: bytes, mime_type: str) -> tuple[str, str]:
    """Calls the exact production functions `RadiologyAgent` uses
    (`vision_server.DESCRIPTION_PROMPT` + `detect_modality`) through the
    app's real `get_llm_client()` — so this eval measures whatever provider
    is actually configured (Gemini or Ollama), not a stand-in model."""
    from intelligence.mcp.vision_server import DESCRIPTION_PROMPT, detect_modality  # noqa: PLC0415

    description = await client.describe_image(image_bytes=image_bytes, mime_type=mime_type, prompt=DESCRIPTION_PROMPT)
    modality = await detect_modality(image_bytes, mime_type)
    return description.strip(), modality


async def run_case(client, case: dict) -> Optional[CaseResult]:
    image_path = IMAGE_DIR / case["filename"]
    if not image_path.is_file():
        print(f"  SKIP {case['id']}: image not found at {image_path}")
        return None

    image_bytes = image_path.read_bytes()
    mime_type = mimetypes.guess_type(image_path.name)[0] or "image/jpeg"

    # Two independent calls — this is the consistency check, not a retry.
    desc1, mod1 = await _describe_and_classify(client, image_bytes, mime_type)
    desc2, mod2 = await _describe_and_classify(client, image_bytes, mime_type)

    run1 = _score_description(desc1, case, mod1)
    run2 = _score_description(desc2, case, mod2)
    consistent = mod1 == mod2

    return CaseResult(
        case_id=case["id"],
        filename=case["filename"],
        expected_modality=case["modality"],
        run1=run1,
        run2=run2,
        consistent=consistent,
    )


def _aggregate(results: list[CaseResult]) -> dict:
    n = len(results) * 2  # each case contributes 2 runs
    modality_correct = sum(r.run1.modality_correct + r.run2.modality_correct for r in results)
    anatomy_grounded = sum(r.run1.anatomy_grounded + r.run2.anatomy_grounded for r in results)
    hallucination_free = sum(r.run1.hallucination_free + r.run2.hallucination_free for r in results)
    no_diagnosis = sum(r.run1.no_diagnosis_language + r.run2.no_diagnosis_language for r in results)
    consistent = sum(r.consistent for r in results)

    metrics = {
        "modality_accuracy": modality_correct / n if n else 0.0,
        "anatomy_grounding": anatomy_grounded / n if n else 0.0,
        "hallucination_free_rate": hallucination_free / n if n else 0.0,
        "no_diagnosis_rate": no_diagnosis / n if n else 0.0,
        "consistency_rate": consistent / len(results) if results else 0.0,
    }
    threshold_rows = [
        {"metric": k, "value": v, "threshold": THRESHOLDS[k], "passed": v >= THRESHOLDS[k]}
        for k, v in metrics.items()
    ]
    return {
        "n_cases": len(results),
        "metrics": metrics,
        "threshold_rows": threshold_rows,
        "passed": all(row["passed"] for row in threshold_rows),
    }


def _print_report(results: list[CaseResult], summary: dict) -> None:
    print("\n=== Per-case detail ===")
    for r in results:
        flags = []
        if not r.run1.modality_correct or not r.run2.modality_correct:
            flags.append(f"modality mismatch (got {r.run1.modality_guess}/{r.run2.modality_guess}, "
                          f"expected {r.expected_modality})")
        if not r.run1.hallucination_free:
            flags.append(f"run1 hallucinated: {r.run1.matched_forbidden}")
        if not r.run2.hallucination_free:
            flags.append(f"run2 hallucinated: {r.run2.matched_forbidden}")
        if not r.run1.anatomy_grounded or not r.run2.anatomy_grounded:
            flags.append("missing expected anatomy keywords")
        if not r.run1.no_diagnosis_language or not r.run2.no_diagnosis_language:
            flags.append("confident-diagnosis language detected")
        if not r.consistent:
            flags.append("inconsistent modality across two independent calls")

        status = "PASS" if not flags else "FAIL"
        print(f"[{status}] {r.case_id}" + (f" — {'; '.join(flags)}" if flags else ""))

    print("\n=== Aggregate ===")
    print("| Metric | Value | Threshold | Status |")
    print("|---|---|---|---|")
    for row in summary["threshold_rows"]:
        status = "PASS" if row["passed"] else "FAIL"
        print(f"| {row['metric']} | {row['value']:.3f} | {row['threshold']:.3f} | {status} |")
    print(f"\nOverall: {'PASS' if summary['passed'] else 'FAIL'}")


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--record", action="store_true", help="Write results/imaging_latest.json")
    args = parser.parse_args()

    sys.path.insert(0, ".")
    sys.path.insert(0, "platform")
    from sephiroth.models import get_llm_client  # noqa: PLC0415

    client = get_llm_client()
    golden = json.loads(GOLDEN_PATH.read_text())

    print(f"Running imaging hallucination/consistency eval on {len(golden['cases'])} cases "
          f"(2 calls each = {len(golden['cases']) * 2} API calls)...\n")

    results = []
    for case in golden["cases"]:
        print(f"  {case['id']}...", end=" ", flush=True)
        result = await run_case(client, case)
        if result:
            results.append(result)
            print("done")

    summary = _aggregate(results)
    _print_report(results, summary)

    if args.record:
        RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        RESULTS_PATH.write_text(
            json.dumps(
                {
                    "summary": summary,
                    "cases": [
                        {
                            "case_id": r.case_id,
                            "filename": r.filename,
                            "expected_modality": r.expected_modality,
                            "consistent": r.consistent,
                            "run1": asdict(r.run1),
                            "run2": asdict(r.run2),
                        }
                        for r in results
                    ],
                },
                indent=2,
            )
        )
        print(f"\nWrote {RESULTS_PATH}")

    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
