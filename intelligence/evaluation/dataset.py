"""Golden dataset for the RAG evaluation harness.

Loads `datasets/golden.json` — a fixed set of clinical questions mapped to
the guideline documents in `data.rag.SEED_GUIDELINES` that should answer
them, plus a handful of adversarial questions with no relevant document at
all (the agent should abstain rather than fabricate an answer).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from data.rag import SEED_GUIDELINES

DATASET_PATH = Path(__file__).parent / "datasets" / "golden.json"


@dataclass
class GoldenCase:
    id: str
    query: str
    category: str
    relevant_doc_ids: List[str] = field(default_factory=list)
    expected_citation_substrings: List[str] = field(default_factory=list)
    must_not_cite: List[str] = field(default_factory=list)
    expects_abstention: bool = False


class DatasetError(ValueError):
    """Raised when the golden dataset references a document that doesn't exist."""


def load_dataset(path: Path = DATASET_PATH) -> List[GoldenCase]:
    """Load and validate the golden dataset.

    Every `relevant_doc_id` must exist in `SEED_GUIDELINES` — a renamed or
    removed corpus document should fail loudly here rather than silently
    zeroing out recall for that case.
    """
    raw = json.loads(path.read_text())
    corpus_ids = {doc.id for doc in SEED_GUIDELINES}

    cases = []
    for entry in raw["cases"]:
        case = GoldenCase(
            id=entry["id"],
            query=entry["query"],
            category=entry["category"],
            relevant_doc_ids=entry.get("relevant_doc_ids", []),
            expected_citation_substrings=entry.get("expected_citation_substrings", []),
            must_not_cite=entry.get("must_not_cite", []),
            expects_abstention=entry.get("expects_abstention", False),
        )
        unknown = [d for d in case.relevant_doc_ids if d not in corpus_ids]
        if unknown:
            raise DatasetError(f"case '{case.id}' references unknown doc id(s): {unknown}")
        cases.append(case)
    return cases
