"""
RAG (Retrieval-Augmented Generation) pipeline for medical evidence.

Keyword-scored retrieval over an in-memory corpus seeded with clinical
guideline excerpts. Designed so the vector-store backend (pgvector +
LlamaIndex) can replace `retrieve()` internals without changing callers —
every result always carries a citation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List

STOPWORDS = {
    "the", "a", "an", "is", "are", "of", "for", "in", "on", "to", "and",
    "or", "what", "which", "with", "how", "when", "should", "be", "my",
}


@dataclass
class Document:
    """Medical document with mandatory citation metadata."""

    id: str
    content: str
    source: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def citation(self) -> str:
        org = self.metadata.get("organization", "")
        year = self.metadata.get("year", "")
        title = self.metadata.get("title", self.source)
        parts = [p for p in [title, org, str(year) if year else ""] if p]
        return ", ".join(parts)


# Seed corpus: short excerpts from public clinical guidelines. Extend by
# calling RAGPipeline.add_document() or the /api/rag ingestion endpoint.
SEED_GUIDELINES: List[Document] = [
    Document(
        id="ada-2024-hba1c",
        content=(
            "An A1C goal for many nonpregnant adults with diabetes of <7% "
            "without significant hypoglycemia is appropriate. Metformin is the "
            "preferred initial pharmacologic agent for type 2 diabetes."
        ),
        source="ADA Standards of Care in Diabetes",
        metadata={"organization": "American Diabetes Association", "year": 2024,
                  "title": "Glycemic Targets & Pharmacologic Approaches"},
    ),
    Document(
        id="acc-aha-2023-htn",
        content=(
            "A blood pressure target of <130/80 mmHg is recommended for most "
            "adults with hypertension. First-line agents include thiazide "
            "diuretics, ACE inhibitors, ARBs, and calcium channel blockers."
        ),
        source="ACC/AHA Hypertension Guideline",
        metadata={"organization": "ACC/AHA", "year": 2023,
                  "title": "High Blood Pressure Management"},
    ),
    Document(
        id="aha-2022-hf",
        content=(
            "In patients with heart failure with reduced ejection fraction "
            "(HFrEF), guideline-directed medical therapy includes ARNI/ACEi/ARB, "
            "beta-blockers, mineralocorticoid receptor antagonists, and SGLT2 "
            "inhibitors. SGLT2 inhibitors are recommended regardless of diabetes status."
        ),
        source="AHA/ACC/HFSA Heart Failure Guideline",
        metadata={"organization": "AHA/ACC/HFSA", "year": 2022,
                  "title": "Management of Heart Failure"},
    ),
    Document(
        id="gold-2024-copd",
        content=(
            "For COPD patients with frequent exacerbations, LABA+LAMA combination "
            "therapy is preferred. Inhaled corticosteroids are added for patients "
            "with blood eosinophils >=300 cells/uL or continued exacerbations."
        ),
        source="GOLD COPD Report",
        metadata={"organization": "GOLD", "year": 2024,
                  "title": "COPD Diagnosis, Management and Prevention"},
    ),
    Document(
        id="idsa-2023-cap",
        content=(
            "For outpatient community-acquired pneumonia in healthy adults, "
            "amoxicillin or doxycycline is recommended. For inpatients, "
            "beta-lactam plus macrolide combination therapy is standard."
        ),
        source="ATS/IDSA Community-Acquired Pneumonia Guideline",
        metadata={"organization": "ATS/IDSA", "year": 2023,
                  "title": "Treatment of Community-Acquired Pneumonia"},
    ),
]


def _tokenize(text: str) -> List[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOPWORDS]


class RAGPipeline:
    """Retrieval pipeline over medical documents. Every hit carries a citation."""

    def __init__(self, seed: bool = True):
        self.documents: List[Document] = list(SEED_GUIDELINES) if seed else []

    def add_document(self, doc: Document) -> None:
        self.documents.append(doc)

    def retrieve(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Score documents by weighted keyword overlap and return the top_k
        as dicts with content, source, citation, and score."""
        query_tokens = set(_tokenize(query))
        if not query_tokens:
            return []

        scored = []
        for doc in self.documents:
            doc_tokens = _tokenize(doc.content)
            if not doc_tokens:
                continue
            overlap = sum(1 for t in doc_tokens if t in query_tokens)
            score = overlap / len(doc_tokens) ** 0.5
            if score > 0:
                scored.append((score, doc))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [
            {
                "id": doc.id,
                "content": doc.content,
                "source": doc.source,
                "citation": doc.citation,
                "score": round(score, 4),
                "metadata": doc.metadata,
            }
            for score, doc in scored[:top_k]
        ]


class MedicalKnowledgeBase:
    """Named collections of medical knowledge sources."""

    def __init__(self):
        self.pipeline = RAGPipeline()

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        return self.pipeline.retrieve(query, top_k=top_k)


__all__ = ["RAGPipeline", "Document", "MedicalKnowledgeBase", "SEED_GUIDELINES"]
