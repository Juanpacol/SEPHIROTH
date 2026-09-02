"""`Document` on its own so corpus modules (`corpus_primary_care.py`, etc.)
can import it without a circular import against `data.rag.__init__`, which
composes those modules into `SEED_GUIDELINES`."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


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


__all__ = ["Document"]
