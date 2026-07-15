"""RAG evaluation harness — Faithfulness, Recall, MRR, Citation Precision.

Two modes (see `run.py`):
- `--mode ci`: deterministic, offline, runs on every PR.
- `--mode full`: exercises the real Evidence Agent against local Ollama and
  refreshes the committed baseline in `results/latest.json`.
"""

from intelligence.evaluation.dataset import GoldenCase, load_dataset
from intelligence.evaluation.metrics import (
    citation_metrics,
    citation_recall,
    fabrication_rate_on_adversarial,
    mrr,
    recall_at_k,
)

__all__ = [
    "GoldenCase",
    "load_dataset",
    "recall_at_k",
    "mrr",
    "citation_metrics",
    "citation_recall",
    "fabrication_rate_on_adversarial",
]
