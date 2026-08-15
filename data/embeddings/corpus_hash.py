"""Hash of the exact inputs the committed embeddings artifact covers:
`SEED_GUIDELINES` document content + the golden-set queries. Used by the
eval harness's staleness gate (mirrors the dataset/transcripts hashing
pattern already in `intelligence/evaluation/runner.py`) so a corpus or
golden-set change without a fresh `build_artifact.py` run fails loudly
instead of silently degrading a new/changed entry to keyword-only."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import List

from data.rag import SEED_GUIDELINES

_REPO_ROOT = Path(__file__).parent.parent.parent
GOLDEN_DATASET_PATH = _REPO_ROOT / "intelligence" / "evaluation" / "datasets" / "golden.json"


def _golden_queries(golden_path: Path = GOLDEN_DATASET_PATH) -> List[str]:
    raw = json.loads(golden_path.read_text())
    return [case["query"] for case in raw["cases"]]


def compute_corpus_sha256(golden_path: Path = GOLDEN_DATASET_PATH) -> str:
    digest = hashlib.sha256()
    for doc in sorted(SEED_GUIDELINES, key=lambda d: d.id):
        digest.update(doc.id.encode())
        digest.update(b"\x00")
        digest.update(doc.content.encode())
        digest.update(b"\x00")
    for query in sorted(_golden_queries(golden_path)):
        digest.update(query.encode())
        digest.update(b"\x00")
    return digest.hexdigest()
