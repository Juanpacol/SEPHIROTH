"""
Citation Guard — validates every citation in an answer against tool output.

Local models occasionally fabricate citations (observed in testing: an
`[UpToDate]` reference no tool ever returned). This module harvests the set of
legitimate citations from the executed tool calls, audits the final answer,
and strips anything that cannot be traced back to a tool result.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List

# Words too generic to prove provenance on their own.
_GENERIC_TOKENS = {
    "source", "guideline", "guidelines", "study", "studies", "trial",
    "the", "of", "and", "for", "in", "on", "et", "al", "a", "an",
    "pmid",  # the prefix proves nothing — only the number identifies a paper
}

_BRACKET_RE = re.compile(r"\[([^\[\]]+)\]")
_PMID_RE = re.compile(r"PMID[:\s]*(\d+)", re.IGNORECASE)
_MD_LINK_RE = re.compile(r"\[([^\[\]]+)\]\((https?://[^)]+)\)")


@dataclass
class CitationReport:
    verified: List[str] = field(default_factory=list)
    fabricated: List[str] = field(default_factory=list)

    @property
    def total_checked(self) -> int:
        return len(self.verified) + len(self.fabricated)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "verified": self.verified,
            "fabricated": self.fabricated,
            "total_checked": self.total_checked,
        }


def _tokens(text: str) -> set:
    return {
        t
        for t in re.findall(r"[a-z0-9/]+", text.lower())
        if t not in _GENERIC_TOKENS and len(t) > 1
    }


def _harvest(value: Any, out: List[str]) -> None:
    """Recursively collect citation-bearing strings from a tool result."""
    if isinstance(value, dict):
        for key in ("citation", "source", "title", "organization", "pmid", "url"):
            v = value.get(key)
            if isinstance(v, str) and v:
                out.append(f"PMID:{v}" if key == "pmid" and v.isdigit() else v)
        for v in value.values():
            _harvest(v, out)
    elif isinstance(value, list):
        for item in value:
            _harvest(item, out)


def collect_allowed_citations(tool_calls: List[Dict[str, Any]]) -> List[str]:
    """Every citation string a tool actually returned, plus the tool names."""
    allowed: List[str] = []
    for call in tool_calls:
        if call.get("name"):
            allowed.append(call["name"])
        _harvest(call.get("result"), allowed)
    return allowed


def _extract_candidates(answer: str) -> List[str]:
    """Citation-shaped spans in the answer text."""
    candidates: List[str] = []
    for match in _BRACKET_RE.finditer(answer):
        content = match.group(1).strip()
        # Skip pure numeric refs like [1] and trivial markers.
        if len(content) >= 4 and re.search(r"[a-zA-Z]", content):
            candidates.append(content)
    for match in _PMID_RE.finditer(answer):
        candidates.append(f"PMID:{match.group(1)}")
    return candidates


def _is_verified(candidate: str, allowed: List[str]) -> bool:
    cand_lower = candidate.lower()
    cand_tokens = _tokens(candidate)

    for source in allowed:
        source_lower = source.lower()
        if cand_lower in source_lower or source_lower in cand_lower:
            return True
        if cand_tokens:
            source_tokens = _tokens(source)
            overlap = len(cand_tokens & source_tokens)
            if overlap / len(cand_tokens) >= 0.5:
                return True
    return False


def audit(answer: str, tool_calls: List[Dict[str, Any]]) -> CitationReport:
    """Classify every citation-shaped span as verified or fabricated."""
    allowed = collect_allowed_citations(tool_calls)
    report = CitationReport()
    seen: set = set()

    for candidate in _extract_candidates(answer):
        key = candidate.lower()
        if key in seen:
            continue
        seen.add(key)
        if _is_verified(candidate, allowed):
            report.verified.append(candidate)
        else:
            report.fabricated.append(candidate)
    return report


def sanitize(answer: str, report: CitationReport) -> str:
    """Replace fabricated citations with an explicit removal marker."""
    result = answer
    for fabricated in report.fabricated:
        # Remove markdown-link form first, then bare bracket form.
        result = re.sub(
            r"\[" + re.escape(fabricated) + r"\]\(https?://[^)]+\)",
            "[unverified — removed]",
            result,
        )
        result = result.replace(f"[{fabricated}]", "[unverified — removed]")
    return result
