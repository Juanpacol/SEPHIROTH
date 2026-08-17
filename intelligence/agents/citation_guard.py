"""Shim — relocated to `src/sephiroth/verification/citation_guard.py` (Phase 5).

Per `docs/00-migration-charter.md`'s shim rules: re-exports only, no logic.
Deleted the phase after this one, unless it becomes permanent.
"""

from sephiroth.verification.citation_guard import CitationReport, audit, collect_allowed_citations, sanitize

__all__ = ["CitationReport", "audit", "sanitize", "collect_allowed_citations"]
