"""Best-effort removal of personal identifiers from free text.

Used by the read-only review endpoint (`platform/api/routers/review.py`), whose
reader is not the clinician who owns the consultation. Two layers:

1. **Known identifiers** -- the patient's own name parts and record number are
   removed wherever they appear, case-insensitively. This is the strong layer:
   it does not depend on guessing what an identifier looks like.
2. **Patterns** -- emails, URLs, phone numbers, long digit runs (document and
   record numbers) and full dates, for identifiers nobody told us about.

It is a heuristic, not a guarantee: a name that is not the patient's, or an
identifier in an unusual shape, can get through. The review endpoint says so in
its docs and keeps the free text behind a token for that reason.
"""

from __future__ import annotations

import re
from typing import Iterable

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_URL = re.compile(r"\bhttps?://\S+|\bwww\.\S+", re.IGNORECASE)
# 7+ digits, allowing the separators people type inside a phone number.
_PHONE = re.compile(r"(?<![\w.])\+?\d[\d\s().-]{5,}\d(?![\w])")
_LONG_ID = re.compile(r"\b[A-Za-z]{0,4}-?\d{6,}\b")
_ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_SLASH_DATE = re.compile(r"\b\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}\b")

# Words too short or too common to remove on their own ("de", "la", "Jr").
_MIN_NAME_PART = 3


def _known_pattern(values: Iterable[str]) -> re.Pattern[str] | None:
    parts: set[str] = set()
    for value in values:
        value = (value or "").strip()
        if not value:
            continue
        parts.add(value)
        parts.update(p for p in re.split(r"[\s,]+", value) if len(p) >= _MIN_NAME_PART)
    if not parts:
        return None
    # Longest first, so "Maria Perez" goes before "Maria".
    ordered = sorted(parts, key=len, reverse=True)
    return re.compile("|".join(re.escape(p) for p in ordered), re.IGNORECASE)


def deidentify(text: str, known: Iterable[str] = ()) -> str:
    """`text` with the `known` identifiers and recognisable patterns replaced
    by bracketed placeholders. Never raises on odd input; `None` -> ""."""
    if not text:
        return ""
    out = text
    pattern = _known_pattern(known)
    if pattern is not None:
        out = pattern.sub("[REDACTED]", out)
    out = _EMAIL.sub("[EMAIL]", out)
    out = _URL.sub("[URL]", out)
    out = _ISO_DATE.sub("[DATE]", out)
    out = _SLASH_DATE.sub("[DATE]", out)
    out = _PHONE.sub("[PHONE]", out)
    out = _LONG_ID.sub("[ID]", out)
    return out


__all__ = ["deidentify"]
