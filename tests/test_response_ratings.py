"""Rating an answer, the review queue, and the numbers built on them (AB#16)."""

from datetime import datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text

from api.main import app
from auth.security import create_access_token, hash_password
from core.config import settings
from core.db import get_session
from data.schemas import Consultation, Patient, ResponseRating, User

pytestmark = pytest.mark.asyncio

REVIEW_TOKEN = "review-token-that-is-definitely-long-enough"


@pytest.fixture
def client(db_session, monkeypatch):
    monkeypatch.setattr(settings, "review_token", REVIEW_TOKEN)

    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    yield AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    app.dependency_overrides.clear()


async def _clinician(client, email) -> tuple[dict, str]:
    res = await client.post(
        "/api/auth/register", json={"email": email, "name": "Dr. R", "password": "password123"}
    )
    body = res.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body["user"]["id"]


def _consultation(cid, user_id, *, trace=True, created=None, calls=None):
    return Consultation(
        id=cid,
        user_id=user_id,
        query="q",
        answer="a",
        agents=["evidence"],
        trace={"trace_id": f"tr-{cid}", "llm_calls": calls or []} if trace else None,
        trace_id=f"tr-{cid}" if trace else None,
        created_at=created or datetime(2026, 10, 1),
    )


def _url(cid):
    return f"/api/agents/consultations/{cid}/rating"


async def _rows(db_session):
    return (await db_session.execute(select(ResponseRating))).scalars().all()


# --- rating -----------------------------------------------------------------


async def test_a_clinician_rates_their_own_answer_up(client, db_session):
    h, uid = await _clinician(client, "r1@example.org")
    db_session.add(_consultation("C1", uid))
    await db_session.commit()

    res = await client.post(_url("C1"), headers=h, json={"value": "up"})

    assert res.status_code == 200
    assert res.json()["value"] == "up"
    (row,) = await _rows(db_session)
    assert (row.consultation_id, row.user_id, row.trace_id, row.value) == ("C1", uid, "tr-C1", "up")
    assert row.review_status is None


async def test_down_keeps_reason_and_comment_and_enters_the_queue(client, db_session):
    h, uid = await _clinician(client, "r2@example.org")
    db_session.add(_consultation("C1", uid))
    await db_session.commit()

    res = await client.post(
        _url("C1"), headers=h, json={"value": "down", "reason": "unsafe", "comment": "  dose off  "}
    )

    assert res.json() == {**res.json(), "value": "down", "reason": "unsafe", "comment": "dose off"}
    (row,) = await _rows(db_session)
    assert row.review_status == "pending"


async def test_up_drops_a_reason_and_comment_it_was_sent(client, db_session):
    h, uid = await _clinician(client, "r3@example.org")
    db_session.add(_consultation("C1", uid))
    await db_session.commit()

    await client.post(_url("C1"), headers=h, json={"value": "up", "reason": "unsafe", "comment": "x"})

    (row,) = await _rows(db_session)
    assert row.reason is None and row.comment == ""


async def test_rating_again_replaces_it_and_never_duplicates(client, db_session):
    h, uid = await _clinician(client, "r4@example.org")
    db_session.add(_consultation("C1", uid))
    await db_session.commit()

    await client.post(_url("C1"), headers=h, json={"value": "down", "reason": "incorrect"})
    await client.post(_url("C1"), headers=h, json={"value": "up"})

    (row,) = await _rows(db_session)
    assert row.value == "up" and row.reason is None and row.review_status is None


async def test_changing_a_reviewed_verdict_reopens_it_but_resending_the_same_does_not(client, db_session):
    h, uid = await _clinician(client, "r5@example.org")
    db_session.add(_consultation("C1", uid))
    await db_session.commit()
    await client.post(_url("C1"), headers=h, json={"value": "down", "reason": "incorrect"})
    rid = (await client.get("/api/quality/queue", headers=h)).json()["items"][0]["item_id"]
    await client.post(f"/api/quality/queue/{rid}/review", headers=h, json={"outcome": "model_failure"})

    await client.post(_url("C1"), headers=h, json={"value": "down", "reason": "incorrect"})
    (row,) = await _rows(db_session)
    await db_session.refresh(row)
    assert row.review_status == "reviewed", "the same verdict again must not undo the review"

    await client.post(_url("C1"), headers=h, json={"value": "down", "reason": "unsafe"})
    await db_session.refresh(row)
    assert row.review_status == "pending" and row.review_outcome is None and row.reviewed_by is None


@pytest.mark.parametrize(
    "body",
    [
        {"value": "meh"},
        {"value": "down", "reason": "because"},
        {"value": "down", "comment": "x" * 501},
        {},
    ],
)
async def test_invalid_ratings_are_422(client, db_session, body):
    h, uid = await _clinician(client, "r6@example.org")
    db_session.add(_consultation("C1", uid))
    await db_session.commit()

    assert (await client.post(_url("C1"), headers=h, json=body)).status_code == 422
    assert await _rows(db_session) == []


async def test_another_clinicians_consultation_is_404(client, db_session):
    _, owner = await _clinician(client, "owner@example.org")
    other, _ = await _clinician(client, "other@example.org")
    db_session.add(_consultation("C1", owner))
    await db_session.commit()

    assert (await client.post(_url("C1"), headers=other, json={"value": "up"})).status_code == 404
    assert await _rows(db_session) == []


async def test_unknown_consultation_is_404_and_unauthenticated_is_401(client):
    h, _ = await _clinician(client, "r7@example.org")

    assert (await client.post(_url("nope"), headers=h, json={"value": "up"})).status_code == 404
    assert (await client.post(_url("nope"), json={"value": "up"})).status_code == 401


async def test_a_consultation_without_a_trace_can_still_be_rated(client, db_session):
    h, uid = await _clinician(client, "r8@example.org")
    db_session.add(_consultation("C1", uid, trace=False))
    await db_session.commit()

    assert (await client.post(_url("C1"), headers=h, json={"value": "up"})).status_code == 200
    (row,) = await _rows(db_session)
    assert row.trace_id is None


async def test_history_returns_my_rating(client, db_session):
    h, uid = await _clinician(client, "r9@example.org")
    other, other_id = await _clinician(client, "r9b@example.org")
    db_session.add_all([_consultation("C1", uid), _consultation("C2", uid, created=datetime(2026, 10, 2))])
    await db_session.commit()
    await client.post(
        _url("C1"), headers=h, json={"value": "down", "reason": "incomplete", "comment": "short"}
    )

    items = {i["id"]: i for i in (await client.get("/api/agents/history", headers=h)).json()}

    assert items["C1"]["rating"]["value"] == "down"
    assert items["C1"]["rating"]["reason"] == "incomplete"
    assert items["C2"]["rating"] is None


async def test_the_comment_is_encrypted_at_rest(client, db_session):
    h, uid = await _clinician(client, "r10@example.org")
    db_session.add(_consultation("C1", uid))
    await db_session.commit()

    await client.post(_url("C1"), headers=h, json={"value": "down", "comment": "metformina contraindicada"})

    raw = (await db_session.execute(text("select comment from response_ratings"))).scalar_one()
    assert "metformina" not in raw
    (row,) = await _rows(db_session)
    assert row.comment == "metformina contraindicada"


# --- queue ------------------------------------------------------------------


async def _down(client, db_session, headers, uid, cid, created, **kw):
    db_session.add(_consultation(cid, uid, created=created, **kw))
    await db_session.commit()
    res = await client.post(_url(cid), headers=headers, json={"value": "down", "reason": "incorrect"})
    assert res.status_code == 200


async def test_queue_lists_pending_downs_oldest_first_with_provenance(client, db_session):
    h, uid = await _clinician(client, "q1@example.org")
    calls = [
        {"kind": "chat", "provider": "gemini", "model": "g", "ok": False, "fallback": False},
        {"kind": "chat", "provider": "groq", "model": "llama", "ok": True, "fallback": True},
    ]
    await _down(client, db_session, h, uid, "C-new", datetime(2026, 10, 5), calls=calls)
    await _down(client, db_session, h, uid, "C-old", datetime(2026, 10, 1))
    db_session.add(_consultation("C-up", uid))
    await db_session.commit()
    await client.post(_url("C-up"), headers=h, json={"value": "up"})

    body = (await client.get("/api/quality/queue", headers=h)).json()

    # Ordered by when the rating was made: C-new was rated first in this test.
    assert {i["consultation_id"] for i in body["items"]} == {"C-new", "C-old"}
    new = next(i for i in body["items"] if i["consultation_id"] == "C-new")
    assert (new["provider"], new["model"], new["fallback"]) == ("groq", "llama", True)
    assert new["reason"] == "incorrect" and new["review_status"] == "pending"
    assert "query" not in new and "answer" not in new


async def test_queue_is_oldest_rating_first_and_paginates(client, db_session):
    h, uid = await _clinician(client, "q2@example.org")
    for i in range(3):
        await _down(client, db_session, h, uid, f"C{i}", datetime(2026, 10, 1))
    rows = await _rows(db_session)
    for i, r in enumerate(sorted(rows, key=lambda r: r.consultation_id)):
        r.created_at = datetime(2026, 10, 1) + timedelta(days=2 - i)  # C0 newest
    await db_session.commit()

    p1 = (await client.get("/api/quality/queue", headers=h, params={"limit": 2})).json()
    p2 = (await client.get("/api/quality/queue", headers=h, params={"limit": 2, "offset": 2})).json()

    assert [i["consultation_id"] for i in p1["items"]] == ["C2", "C1"]
    assert [i["consultation_id"] for i in p2["items"]] == ["C0"]
    assert p1["has_more"] is True and p2["has_more"] is False


async def test_a_clinician_reviews_an_item_and_it_leaves_the_pending_queue(client, db_session):
    h, uid = await _clinician(client, "q3@example.org")
    await _down(client, db_session, h, uid, "C1", datetime(2026, 10, 1))
    rid = (await client.get("/api/quality/queue", headers=h)).json()["items"][0]["item_id"]

    res = await client.post(
        f"/api/quality/queue/{rid}/review",
        headers=h,
        json={"outcome": "source_failure", "note": "bad source"},
    )

    assert res.status_code == 200
    assert res.json()["review_status"] == "reviewed" and res.json()["review_outcome"] == "source_failure"
    assert (await client.get("/api/quality/queue", headers=h)).json()["items"] == []
    done = (await client.get("/api/quality/queue", headers=h, params={"status": "reviewed"})).json()["items"]
    assert [i["review_note"] for i in done] == ["bad source"]
    (row,) = await _rows(db_session)
    assert row.reviewed_by == uid and row.reviewed_at is not None


async def test_review_rejects_bad_outcome_double_review_and_unknown_or_up_items(client, db_session):
    h, uid = await _clinician(client, "q4@example.org")
    await _down(client, db_session, h, uid, "C1", datetime(2026, 10, 1))
    db_session.add(_consultation("C2", uid))
    await db_session.commit()
    await client.post(_url("C2"), headers=h, json={"value": "up"})
    rid = (await client.get("/api/quality/queue", headers=h)).json()["items"][0]["item_id"]
    up_id = next(r.id for r in await _rows(db_session) if r.value == "up")

    assert (
        await client.post(f"/api/quality/queue/{rid}/review", headers=h, json={"outcome": "meh"})
    ).status_code == 422
    assert (
        await client.post(f"/api/quality/queue/{rid}/review", headers=h, json={"outcome": "no_action"})
    ).status_code == 200
    assert (
        await client.post(f"/api/quality/queue/{rid}/review", headers=h, json={"outcome": "no_action"})
    ).status_code == 409
    assert (
        await client.post("/api/quality/queue/nope/review", headers=h, json={"outcome": "no_action"})
    ).status_code == 404
    assert (
        await client.post(f"/api/quality/queue/{up_id}/review", headers=h, json={"outcome": "no_action"})
    ).status_code == 404


async def test_the_queue_is_for_clinicians_only(client, db_session):
    db_session.add(Patient(id="PQ1", name="Pat", age=40, sex="F", medical_record_number="PT-Q1"))
    await db_session.commit()
    db_session.add(
        User(
            id="pat-user",
            email="pat@example.org",
            name="Pat",
            hashed_password=await hash_password("password123"),
            role="patient",
            patient_id="PQ1",
        )
    )
    await db_session.commit()
    patient = {"Authorization": f"Bearer {create_access_token('pat-user')}"}

    assert (await client.get("/api/quality/queue")).status_code == 401
    assert (await client.get("/api/quality/queue", headers=patient)).status_code in (401, 403)
    assert (
        await client.post("/api/quality/queue/x/review", headers=patient, json={"outcome": "no_action"})
    ).status_code in (401, 403)


# --- token (read only) -----------------------------------------------------


async def test_the_review_token_reads_the_queue_without_the_clinicians_text(client, db_session):
    h, uid = await _clinician(client, "t1@example.org")
    db_session.add(_consultation("C1", uid))
    await db_session.commit()
    await client.post(
        _url("C1"),
        headers=h,
        json={"value": "down", "reason": "unsafe", "comment": "call me at maria@example.org"},
    )

    res = await client.get("/api/review/queue", headers={"X-Review-Token": REVIEW_TOKEN})

    assert res.status_code == 200
    item = res.json()["items"][0]
    assert item["trace_id"] == "tr-C1" and item["reason"] == "unsafe"
    assert "maria@example.org" not in res.text and "[EMAIL]" in item["comment"]
    assert "item_id" not in item and "consultation_id" not in item


async def test_the_review_token_cannot_rate_or_review(client, db_session):
    h, uid = await _clinician(client, "t2@example.org")
    await _down(client, db_session, h, uid, "C1", datetime(2026, 10, 1))
    token = {"X-Review-Token": REVIEW_TOKEN}

    assert (await client.get("/api/review/queue")).status_code == 401
    assert (await client.post("/api/review/queue", headers=token)).status_code == 405
    assert (await client.post(_url("C1"), headers=token, json={"value": "up"})).status_code == 401
    assert (await client.get("/api/quality/queue", headers=token)).status_code == 401


# --- dashboard --------------------------------------------------------------


async def test_dashboard_ai_reports_the_helpful_ratio_and_pending_reviews(client, db_session):
    h, uid = await _clinician(client, "d1@example.org")
    empty = (await client.get("/api/dashboard/ai", headers=h)).json()
    assert (
        empty["ratings_count"] == 0 and empty["helpful_ratio"] is None and empty["pending_review_count"] == 0
    )

    for cid in ("C1", "C2", "C3"):
        db_session.add(_consultation(cid, uid))
    await db_session.commit()
    await client.post(_url("C1"), headers=h, json={"value": "up"})
    await client.post(_url("C2"), headers=h, json={"value": "up"})
    await client.post(_url("C3"), headers=h, json={"value": "down", "reason": "other"})

    body = (await client.get("/api/dashboard/ai", headers=h)).json()

    assert body["ratings_count"] == 3
    assert body["helpful_count"] == 2
    assert body["helpful_ratio"] == pytest.approx(0.667, abs=0.001)
    assert body["pending_review_count"] == 1
