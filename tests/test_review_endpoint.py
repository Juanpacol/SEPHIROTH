"""`/api/review/*` -- read-only consultation review behind its own token (AB#15)."""

from datetime import datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from api.main import app
from core.config import settings
from core.db import get_session
from data.schemas import Consultation, Patient, ReviewAccessLog
from sephiroth.safety.deidentify import deidentify

pytestmark = pytest.mark.asyncio

TOKEN = "review-token-that-is-definitely-long-enough"
H = {"X-Review-Token": TOKEN}


@pytest.fixture
def client(db_session, monkeypatch):
    monkeypatch.setattr(settings, "review_token", TOKEN)

    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    yield AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    app.dependency_overrides.clear()


def _call(provider="gemini", model="gemini-flash-latest", ok=True, fallback=False, kind="chat"):
    return {
        "kind": kind,
        "provider": provider,
        "model": model,
        "ok": ok,
        "error": "" if ok else "rate_limited",
        "fallback": fallback,
        "fallback_from": "gemini" if fallback else "",
        "fallback_reason": "rate_limited" if fallback else "",
        "duration_ms": 10,
        "prompt_tokens": 0,
        "completion_tokens": 0,
    }


def _row(
    trace_id, *, created=None, calls=None, status="answer", query="q", answer="a", patient_id=None, **kw
):
    return Consultation(
        id=f"C-{trace_id}",
        user_id="U1",
        patient_id=patient_id,
        query=query,
        answer=answer,
        agents=["evidence"],
        abstention={"status": status},
        trace={
            "trace_id": trace_id,
            "llm_calls": calls if calls is not None else [_call()],
            "latency_ms": 42,
        },
        trace_id=trace_id,
        created_at=created or datetime(2026, 10, 1, 12, 0, 0),
        **kw,
    )


async def _audit_rows(db_session):
    return (await db_session.execute(select(ReviewAccessLog).order_by(ReviewAccessLog.id))).scalars().all()


# --- access -----------------------------------------------------------------


async def test_unset_token_means_the_routes_do_not_exist(client, monkeypatch):
    monkeypatch.setattr(settings, "review_token", None)

    assert (await client.get("/api/review/consultations", headers=H)).status_code == 404
    assert (await client.get("/api/review/consultations/abc", headers=H)).status_code == 404


async def test_missing_or_wrong_token_is_401(client):
    assert (await client.get("/api/review/consultations")).status_code == 401
    assert (
        await client.get("/api/review/consultations", headers={"X-Review-Token": "nope"})
    ).status_code == 401
    assert (
        await client.get("/api/review/consultations/abc", headers={"X-Review-Token": "nope"})
    ).status_code == 401


async def test_a_clinician_jwt_is_not_a_review_token(client):
    res = await client.get("/api/review/consultations", headers={"Authorization": "Bearer something"})

    assert res.status_code == 401


async def test_the_review_token_opens_no_other_route(client):
    for path in ("/api/patients", "/api/agents/history", "/api/dashboard/stats"):
        res = await client.get(path, headers=H)
        assert res.status_code in (401, 403, 404, 405), path


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
async def test_only_get_is_allowed(client, method):
    for path in ("/api/review/consultations", "/api/review/consultations/abc"):
        res = await getattr(client, method)(path, headers=H)
        assert res.status_code == 405, (method, path)


async def test_failed_attempts_are_not_audited_as_reads(client, db_session):
    await client.get("/api/review/consultations", headers={"X-Review-Token": "nope"})

    assert await _audit_rows(db_session) == []


# --- list -------------------------------------------------------------------


async def test_list_is_newest_first_with_the_fields_a_reviewer_needs(client, db_session):
    db_session.add_all(
        [
            _row("old", created=datetime(2026, 10, 1)),
            _row(
                "new",
                created=datetime(2026, 10, 2),
                calls=[_call(ok=False), _call("groq", "llama-3.3-70b-versatile", fallback=True)],
            ),
        ]
    )
    await db_session.commit()

    body = (await client.get("/api/review/consultations", headers=H)).json()

    assert [i["trace_id"] for i in body["items"]] == ["new", "old"]
    first = body["items"][0]
    assert first["provider"] == "groq"
    assert first["model"] == "llama-3.3-70b-versatile"
    assert first["fallback"] is True
    assert first["status"] == "answer"
    assert first["latency_ms"] == 42
    assert first["agents"] == ["evidence"]
    assert body["items"][1]["fallback"] is False


async def test_list_filters_by_date_fallback_and_status(client, db_session):
    db_session.add_all(
        [
            _row("a", created=datetime(2026, 10, 1)),
            _row("b", created=datetime(2026, 10, 5), calls=[_call("groq", fallback=True)]),
            _row("c", created=datetime(2026, 10, 9), status="abstain"),
        ]
    )
    await db_session.commit()

    async def ids(**params):
        body = (await client.get("/api/review/consultations", headers=H, params=params)).json()
        return [i["trace_id"] for i in body["items"]]

    assert await ids(fallback="true") == ["b"]
    assert await ids(fallback="false") == ["c", "a"]
    assert await ids(status="abstain") == ["c"]
    assert await ids(since="2026-10-04T00:00:00", until="2026-10-06T00:00:00") == ["b"]
    assert await ids(since="2026-10-04T00:00:00", fallback="false") == ["c"]


async def test_list_rejects_an_unknown_status(client):
    res = await client.get("/api/review/consultations", headers=H, params={"status": "bogus"})

    assert res.status_code == 422


async def test_list_paginates_without_skipping_or_repeating(client, db_session):
    base = datetime(2026, 10, 1)
    db_session.add_all([_row(f"t{i:02d}", created=base + timedelta(hours=i)) for i in range(5)])
    await db_session.commit()

    page1 = (await client.get("/api/review/consultations", headers=H, params={"limit": 2})).json()
    page2 = (
        await client.get("/api/review/consultations", headers=H, params={"limit": 2, "offset": 2})
    ).json()
    page3 = (
        await client.get("/api/review/consultations", headers=H, params={"limit": 2, "offset": 4})
    ).json()

    seen = [i["trace_id"] for p in (page1, page2, page3) for i in p["items"]]
    assert seen == ["t04", "t03", "t02", "t01", "t00"]
    assert page1["has_more"] is True
    assert page3["has_more"] is False


async def test_list_skips_consultations_that_have_no_trace(client, db_session):
    db_session.add_all(
        [
            _row("traced"),
            Consultation(id="C-old", user_id="U1", query="q", answer="a", created_at=datetime(2026, 10, 3)),
        ]
    )
    await db_session.commit()

    body = (await client.get("/api/review/consultations", headers=H)).json()

    assert [i["trace_id"] for i in body["items"]] == ["traced"]


async def test_a_consultation_with_no_model_call_reports_no_provider(client, db_session):
    db_session.add(_row("fast", calls=[]))
    await db_session.commit()

    item = (await client.get("/api/review/consultations", headers=H)).json()["items"][0]

    assert item["provider"] == ""
    assert item["fallback"] is False
    assert item["llm_calls"] == 0


# --- detail -----------------------------------------------------------------


async def test_detail_returns_the_trace_a_reviewer_needs(client, db_session):
    db_session.add(
        _row(
            "abc",
            calls=[_call(ok=False), _call("groq", "llama", fallback=True)],
            citation_report={"verified": ["PMID:1", "PMID:2"], "fabricated": ["PMID:9"], "total_checked": 3},
            verification_report={"claims": [{"text": "claim one", "status": "supported", "risk": "low"}]},
            tool_calls=[
                {
                    "tool": "search_guidelines",
                    "agent": "evidence",
                    "ok": True,
                    "latency_ms": 5,
                    "arguments": {"q": "SECRET"},
                }
            ],
        )
    )
    await db_session.commit()

    res = await client.get("/api/review/consultations/abc", headers=H)

    assert res.status_code == 200
    body = res.json()
    assert [c["provider"] for c in body["llm_call_records"]] == ["gemini", "groq"]
    assert body["llm_call_records"][1]["fallback_reason"] == "rate_limited"
    assert body["citations"] == {"verified": 2, "fabricated": 1, "total_checked": 3}
    assert body["claims"][0]["text"] == "claim one"
    assert body["tool_calls"] == [
        {"tool": "search_guidelines", "agent": "evidence", "ok": True, "latency_ms": 5}
    ]
    assert "SECRET" not in res.text, "tool arguments must not leave"
    assert body["abstention"]["status"] == "answer"


async def test_unknown_trace_id_is_404_and_says_nothing_else(client):
    res = await client.get("/api/review/consultations/does-not-exist", headers=H)

    assert res.status_code == 404
    assert res.json() == {"detail": "Not found"}


# --- de-identification ------------------------------------------------------


async def test_detail_carries_no_identifier_of_the_patient(client, db_session):
    db_session.add(
        Patient(
            id="P-77",
            name="Maria Fernanda Gomez",
            age=60,
            sex="F",
            medical_record_number="MRN-4481923",
        )
    )
    db_session.add(
        _row(
            "pii",
            patient_id="P-77",
            query="Maria Gomez, MRN-4481923, born 1964-03-02, call 300 123 4567 or maria@example.org",
            answer=(
                "Para la paciente MARIA FERNANDA GOMEZ: ver https://clinic.example/p/77 "
                "y repetir en 12/11/2026."
            ),
            verification_report={"claims": [{"text": "Gomez tolera metformina", "status": "supported"}]},
        )
    )
    await db_session.commit()

    res = await client.get("/api/review/consultations/pii", headers=H)
    text = res.text

    for leaked in (
        "Maria",
        "MARIA",
        "Gomez",
        "Fernanda",
        "4481923",
        "1964-03-02",
        "300 123 4567",
        "maria@example.org",
        "clinic.example",
        "12/11/2026",
        "P-77",
        "U1",
    ):
        assert leaked not in text, f"{leaked!r} leaked"
    body = res.json()
    assert body["patient"].startswith("pt_")
    assert "[REDACTED]" in body["query"]


async def test_the_pseudonym_is_stable_and_distinguishes_patients(client, db_session):
    db_session.add_all(
        [
            _row("p1a", patient_id="P-1"),
            _row("p1b", patient_id="P-1", created=datetime(2026, 10, 2)),
            _row("p2", patient_id="P-2", created=datetime(2026, 10, 3)),
        ]
    )
    await db_session.commit()

    items = (await client.get("/api/review/consultations", headers=H)).json()["items"]
    by_id = {i["trace_id"]: i["patient"] for i in items}

    assert by_id["p1a"] == by_id["p1b"] != by_id["p2"]
    assert "P-1" not in str(by_id.values())


def test_deidentify_patterns_without_known_identifiers():
    out = deidentify("mail a@b.co, tel +57 310 555 1234, doc 1020304050, el 2026-01-31 y 5/6/2026, www.x.org")

    assert "a@b.co" not in out
    assert "555 1234" not in out
    assert "1020304050" not in out
    assert "2026-01-31" not in out
    assert "5/6/2026" not in out
    assert "www.x.org" not in out


def test_deidentify_keeps_clinical_values_readable():
    text = "BP 142/91 mmHg, HbA1c 7.2%, metformin 850 mg twice daily, eGFR 58, K 5.1"

    assert deidentify(text) == text


def test_deidentify_ignores_short_name_particles_and_handles_empty():
    assert deidentify("", ["Ana"]) == ""
    assert deidentify(None) == ""  # type: ignore[arg-type]
    assert "de" in deidentify("paciente de Ana de la Cruz", ["Ana de la Cruz"])


# --- audit ------------------------------------------------------------------


async def test_every_read_is_audited_without_the_token(client, db_session):
    db_session.add(_row("abc"))
    await db_session.commit()

    await client.get("/api/review/consultations", headers=H, params={"fallback": "true", "limit": 5})
    await client.get("/api/review/consultations/abc", headers=H)
    await client.get("/api/review/consultations/missing", headers=H)

    rows = await _audit_rows(db_session)
    assert [(r.route, r.method, r.trace_id) for r in rows] == [
        ("/api/review/consultations", "GET", None),
        ("/api/review/consultations/abc", "GET", "abc"),
        ("/api/review/consultations/missing", "GET", "missing"),
    ]
    assert rows[0].filters["fallback"] is True
    assert rows[0].filters["limit"] == 5
    assert all(r.token_fingerprint and TOKEN not in r.token_fingerprint for r in rows)
    assert all(TOKEN not in str(r.filters) for r in rows)


async def test_reading_does_not_modify_consultations(client, db_session):
    db_session.add(_row("abc"))
    await db_session.commit()

    await client.get("/api/review/consultations", headers=H)
    await client.get("/api/review/consultations/abc", headers=H)

    assert (await db_session.execute(select(func.count()).select_from(Consultation))).scalar() == 1
    row = (await db_session.execute(select(Consultation))).scalars().one()
    assert row.answer == "a" and row.query == "q"


# --- config -----------------------------------------------------------------


def test_a_short_review_token_is_refused_in_production():
    from cryptography.fernet import Fernet

    from core.config import Settings

    valid = dict(
        environment="production",
        phi_encryption_key=Fernet.generate_key().decode(),
        jwt_secret="y" * 40,
    )
    # Everything else valid, so the only possible complaint is the token. (This
    # test once matched the echoed *input* instead of the message and passed
    # while checking nothing; startup errors no longer echo their input.)
    with pytest.raises(ValueError, match="review_token must be"):
        Settings(**valid, review_token="short")
    assert Settings(**valid, review_token="r" * 32).review_token == "r" * 32
