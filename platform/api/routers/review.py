"""Read-only review of consultations, for someone who is not the clinician.

Answers "what actually happened in that consultation?" -- which model replied,
whether a fallback served it, which tools ran, what the verifier said --
without database or log access. Built on `ExecutionTrace.llm_calls` (AB#14).

Deliberately NOT under `auth/deps.py`: those resolve a `User`, and a reviewer
is not one. Guarded by its own shared secret (`settings.review_token`), same
trust model as `/internal/tick` (see `internal.py`), with three differences:

- **Unset token = 404, not 200-disabled.** Nothing is exposed until someone
  sets it on purpose.
- **GET only.** There is no write route here and the token opens no other one.
- **Every read is audited** in `review_access_log`, by a fingerprint of the
  token (never the token) -- including reads of a trace that does not exist.

What leaves is de-identified: the patient is a stable pseudonym, the clinician
is not named, and free text goes through `sephiroth.safety.deidentify` (the
patient's own name and record number removed wherever they appear, plus
patterns). That is best-effort, not a guarantee -- hence the token.
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.db import get_session
from core.rate_limit import limiter
from data.schemas import Consultation, Patient, ResponseRating, ReviewAccessLog
from sephiroth.safety.deidentify import deidentify

from ..provenance import answering_call, llm_calls, provenance

router = APIRouter()

#: Rows read from the database to fill one page of a filtered list. Fallback
#: and status live inside JSON columns, so they are filtered here rather than in
#: SQL (portable across SQLite and Postgres); the cap keeps a rare filter from
#: scanning the whole table.
_SCAN_CAP = 1000
_CHUNK = 200


def _fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()[:12]


async def require_review_token(x_review_token: Optional[str] = Header(default=None)) -> str:
    expected = settings.review_token or ""
    if not expected:
        raise HTTPException(status_code=404, detail="Not found")
    if not x_review_token or not hmac.compare_digest(x_review_token, expected):
        raise HTTPException(status_code=401, detail="Invalid review token")
    return _fingerprint(x_review_token)


def _pseudonym(patient_id: Optional[str]) -> str:
    if not patient_id:
        return ""
    digest = hmac.new(settings.phi_encryption_key.encode(), patient_id.encode(), hashlib.sha256)
    return "pt_" + digest.hexdigest()[:10]


def _calls(row: Consultation) -> list[dict[str, Any]]:
    return llm_calls(row.trace)


def _status(row: Consultation) -> str:
    status = (row.abstention or {}).get("status")
    return status or ("abstain" if row.abstained else "answer")


def _summary(row: Consultation) -> dict[str, Any]:
    calls = _calls(row)
    answering = answering_call(calls)
    return {
        "trace_id": row.trace_id or "",
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "agents": list(row.agents or []),
        "provider": answering.get("provider", ""),
        "model": answering.get("model", ""),
        "fallback": any(c.get("fallback") for c in calls),
        "llm_calls": len(calls),
        "status": _status(row),
        "risk_level": row.risk_level,
        "latency_ms": (row.trace or {}).get("latency_ms", 0),
        "patient": _pseudonym(row.patient_id),
    }


async def _audit(
    session: AsyncSession,
    fingerprint: str,
    request: Request,
    *,
    trace_id: str | None,
    filters: dict[str, Any],
) -> None:
    session.add(
        ReviewAccessLog(
            token_fingerprint=fingerprint,
            route=request.url.path[:200],
            method=request.method,
            trace_id=trace_id,
            filters=filters,
        )
    )
    await session.commit()


@router.get("/consultations")
@limiter.limit("60/minute")
async def list_consultations(
    request: Request,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    fallback: Optional[bool] = None,
    status: Optional[str] = Query(default=None, pattern="^(answer|partial|abstain)$"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    fingerprint: str = Depends(require_review_token),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    await _audit(
        session,
        fingerprint,
        request,
        trace_id=None,
        filters={
            "since": since.isoformat() if since else None,
            "until": until.isoformat() if until else None,
            "fallback": fallback,
            "status": status,
            "limit": limit,
            "offset": offset,
        },
    )

    stmt = select(Consultation).where(Consultation.trace_id.is_not(None))
    if since:
        stmt = stmt.where(Consultation.created_at >= since)
    if until:
        stmt = stmt.where(Consultation.created_at <= until)
    stmt = stmt.order_by(Consultation.created_at.desc(), Consultation.id.desc())

    wanted = offset + limit
    matched: list[dict[str, Any]] = []
    scanned = 0
    exhausted = False
    while len(matched) < wanted + 1 and scanned < _SCAN_CAP:
        rows = (await session.execute(stmt.limit(_CHUNK).offset(scanned))).scalars().all()
        if not rows:
            exhausted = True
            break
        scanned += len(rows)
        for row in rows:
            item = _summary(row)
            if fallback is not None and item["fallback"] != fallback:
                continue
            if status is not None and item["status"] != status:
                continue
            matched.append(item)
        if len(rows) < _CHUNK:
            exhausted = True
            break

    return {
        "items": matched[offset:wanted],
        "limit": limit,
        "offset": offset,
        "has_more": len(matched) > wanted,
        # False when the scan cap stopped the search before the table ran out:
        # a narrower date range finds the rest.
        "complete": exhausted or len(matched) > wanted,
    }


@router.get("/queue")
@limiter.limit("60/minute")
async def review_queue(
    request: Request,
    status: str = Query(default="pending", pattern="^(pending|reviewed|all)$"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    fingerprint: str = Depends(require_review_token),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """The answers clinicians rated "not useful", oldest first, read-only.
    Provenance and the reason code; the comment is de-identified."""
    await _audit(
        session,
        fingerprint,
        request,
        trace_id=None,
        filters={"queue": status, "limit": limit, "offset": offset},
    )
    stmt = (
        select(ResponseRating, Consultation)
        .join(Consultation, Consultation.id == ResponseRating.consultation_id)
        .where(ResponseRating.value == "down")
        .order_by(ResponseRating.created_at.asc(), ResponseRating.id.asc())
    )
    if status != "all":
        stmt = stmt.where(ResponseRating.review_status == status)
    rows = (await session.execute(stmt.limit(limit + 1).offset(offset))).all()
    items = []
    for rating, consultation in rows[:limit]:
        items.append(
            {
                "trace_id": rating.trace_id or "",
                "created_at": rating.created_at.isoformat() if rating.created_at else None,
                "reason": rating.reason,
                "comment": deidentify(rating.comment),
                "agents": list(consultation.agents or []),
                **provenance(consultation.trace),
                "review_status": rating.review_status,
                "review_outcome": rating.review_outcome,
            }
        )
    return {"items": items, "limit": limit, "offset": offset, "has_more": len(rows) > limit}


@router.get("/consultations/{trace_id}")
@limiter.limit("60/minute")
async def get_consultation(
    request: Request,
    trace_id: str,
    fingerprint: str = Depends(require_review_token),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    await _audit(session, fingerprint, request, trace_id=trace_id[:64], filters={})

    row = (
        (await session.execute(select(Consultation).where(Consultation.trace_id == trace_id)))
        .scalars()
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")

    patient = await session.get(Patient, row.patient_id) if row.patient_id else None
    known = [patient.name, patient.medical_record_number] if patient else []

    def clean(text: Any) -> str:
        return deidentify(str(text or ""), known)

    trace = row.trace or {}
    verification = row.verification_report or {}
    citation = row.citation_report or {}
    return {
        **_summary(row),
        "query": clean(row.query),
        "answer": clean(row.answer),
        "llm_call_records": _calls(row),
        "tool_calls": [
            {
                "tool": t.get("tool", ""),
                "agent": t.get("agent", ""),
                "ok": t.get("ok", True),
                "latency_ms": t.get("latency_ms", 0),
            }
            for t in (row.tool_calls or [])
        ],
        "citations": {
            "verified": len(citation.get("verified") or []),
            "fabricated": len(citation.get("fabricated") or []),
            "total_checked": citation.get("total_checked", 0),
        },
        "claims": [
            {
                "text": clean(c.get("text")),
                "status": c.get("status", ""),
                "risk": c.get("risk", ""),
                "confidence": c.get("confidence", 0),
            }
            for c in (verification.get("claims") or [])
        ],
        "abstention": {
            "status": _status(row),
            "reason": (row.abstention or {}).get("reason"),
            "confidence": (row.abstention or {}).get("confidence"),
            "supported_claim_ratio": row.supported_claim_ratio,
        },
        "tokens": trace.get("tokens", {}),
        "cost_usd": trace.get("cost_usd", 0.0),
        "failures": [
            {"category": f.get("category", ""), "component": f.get("component", "")}
            for f in (trace.get("failures") or [])
        ],
    }


__all__ = ["router"]
