"""Automatic grading of a sample of consultations by a second model (AB#17)."""

import asyncio
from datetime import datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text

from api.main import app
from api.routers.agents import ConsultRequest, _persist
from api.services import auto_grading
from api.services.auto_grading import (
    CRITERIA_VERSION,
    build_prompt,
    grade_consultation,
    is_sampled,
    schedule_auto_grade,
)
from core.config import Settings, settings
from core.db import get_session
from data.schemas import AutoGrade, Consultation, ResponseRating, User
from sephiroth.models import LLMUnavailableError, ProviderInfo

pytestmark = pytest.mark.asyncio

REVIEW_TOKEN = "review-token-that-is-definitely-long-enough"
GOOD = {"grounding": 5, "completeness": 4, "safety": 5, "abstention": 4, "justification": "Well supported."}
BAD = {
    "grounding": 1,
    "completeness": 2,
    "safety": 2,
    "abstention": 1,
    "justification": "Claims lack support.",
}


class Grader:
    """A scripted grader that records what it was sent."""

    def __init__(
        self, payload=None, *, exc=None, provider="groq", model="grader-model", local=False, delay=0.0
    ):
        self.payload, self.exc, self.delay = payload, exc, delay
        self.info = ProviderInfo(provider=provider, model=model, local=local)
        self.prompts: list[str] = []
        self.systems: list[str] = []

    def describe(self):
        return self.info

    async def generate_json(self, prompt, schema, *, system_prompt=None):
        self.prompts.append(prompt)
        self.systems.append(system_prompt or "")
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.exc:
            raise self.exc
        return self.payload


class _Ctx:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *exc):
        return False


@pytest.fixture
def on(db_session, monkeypatch):
    """Grading enabled at rate 1, running against the test database."""
    monkeypatch.setattr(auto_grading, "SessionLocal", lambda: _Ctx(db_session))
    monkeypatch.setattr(settings, "enable_auto_grading", True)
    monkeypatch.setattr(settings, "auto_grading_sample_rate", 1.0)
    monkeypatch.setattr(settings, "auto_grading_provider", "groq")
    monkeypatch.setattr(settings, "auto_grading_model", "grader-model")
    monkeypatch.setattr(settings, "auto_grading_low_score", 3.0)
    monkeypatch.setattr(settings, "auto_grading_max_per_hour", 20)
    monkeypatch.setattr(settings, "auto_grading_max_per_day", 100)
    monkeypatch.setattr(settings, "auto_grading_timeout_seconds", 5.0)
    monkeypatch.setattr(settings, "ai_allow_phi", True)
    return db_session


def _answered_by(provider="gemini", model="gemini-flash-latest"):
    return [{"kind": "chat", "provider": provider, "model": model, "ok": True, "fallback": False}]


async def _consultation(db_session, cid="C1", *, calls=None, trace_id="tr-C1", created=None, user="U1"):
    row = Consultation(
        id=cid,
        user_id=user,
        query="Is the warfarin dose safe with INR 4.8?",
        answer="Hold the dose and recheck the INR [1].",
        agents=["evidence"],
        abstention={"status": "answer"},
        trace={
            "trace_id": trace_id,
            "llm_calls": _answered_by() if calls is None else calls,
            "evidence": [
                {
                    "id": "ev1",
                    "source": "guideline",
                    "citation": {"title": "CHEST"},
                    "content": "INR above 4.5: hold.",
                }
            ],
        }
        if trace_id
        else None,
        trace_id=trace_id,
        created_at=created or datetime(2026, 10, 1),
    )
    db_session.add(row)
    await db_session.commit()
    return row


async def _grades(db_session):
    return (await db_session.execute(select(AutoGrade).order_by(AutoGrade.created_at))).scalars().all()


# --- sampling ---------------------------------------------------------------


def test_sampling_is_deterministic_and_respects_the_extremes():
    ids = [f"trace-{i}" for i in range(2000)]

    assert not any(is_sampled(i, 0.0) for i in ids)
    assert all(is_sampled(i, 1.0) for i in ids)
    first = [is_sampled(i, 0.3) for i in ids]
    assert first == [is_sampled(i, 0.3) for i in ids]
    assert 0.25 < sum(first) / len(ids) < 0.35


def test_a_bigger_sample_contains_the_smaller_one():
    ids = [f"trace-{i}" for i in range(500)]

    small = {i for i in ids if is_sampled(i, 0.1)}
    large = {i for i in ids if is_sampled(i, 0.5)}

    assert small <= large


# --- when nothing happens ---------------------------------------------------


async def test_disabled_means_no_model_call_and_no_row(on, monkeypatch):
    monkeypatch.setattr(settings, "enable_auto_grading", False)
    row = await _consultation(on)
    grader = Grader(GOOD)

    assert await grade_consultation(row.id, grader) is None
    assert grader.prompts == [] and await _grades(on) == []


async def test_a_consultation_the_sample_did_not_pick_leaves_no_row(on, monkeypatch):
    monkeypatch.setattr(settings, "auto_grading_sample_rate", 0.0)
    row = await _consultation(on)
    grader = Grader(GOOD)

    assert await grade_consultation(row.id, grader) is None
    assert grader.prompts == [] and await _grades(on) == []


async def test_the_fast_path_and_unknown_ids_are_not_graded(on):
    fast = await _consultation(on, "C-fast", trace_id=None)
    no_model = await _consultation(on, "C-nomodel", calls=[], trace_id="tr-nomodel")
    grader = Grader(GOOD)

    for cid in (fast.id, no_model.id, "missing"):
        assert await grade_consultation(cid, grader) is None
    assert grader.prompts == [] and await _grades(on) == []


# --- grading ---------------------------------------------------------------


async def test_a_graded_consultation_stores_scores_version_and_grader(on):
    row = await _consultation(on)
    grader = Grader(GOOD)

    stored = await grade_consultation(row.id, grader)

    assert stored.status == "graded"
    assert stored.scores == {"grounding": 5, "completeness": 4, "safety": 5, "abstention": 4}
    assert stored.overall == 4.5
    assert stored.justification == "Well supported."
    assert (stored.grader_provider, stored.grader_model) == ("groq", "grader-model")
    assert stored.criteria_version == CRITERIA_VERSION
    assert stored.trace_id == "tr-C1"
    assert stored.review_status is None


async def test_the_grader_is_sent_question_answer_and_evidence_under_a_fixed_rubric(on):
    row = await _consultation(on)
    grader = Grader(GOOD)

    await grade_consultation(row.id, grader)

    (prompt,) = grader.prompts
    assert "warfarin" in prompt and "Hold the dose" in prompt and "INR above 4.5: hold." in prompt
    assert prompt == build_prompt(row)
    assert all(c in grader.systems[0] for c in ("grounding", "completeness", "safety", "abstention"))


async def test_the_justification_is_encrypted_at_rest(on):
    row = await _consultation(on)
    await grade_consultation(row.id, Grader(GOOD))

    raw = (await on.execute(text("select justification from auto_grades"))).scalar_one()

    assert "Well supported" not in raw


async def test_a_low_mean_opens_a_review_item_and_a_high_one_does_not(on):
    low = await _consultation(on, "C-low", trace_id="tr-low")
    high = await _consultation(on, "C-high", trace_id="tr-high")

    low_row = await grade_consultation(low.id, Grader(BAD))
    high_row = await grade_consultation(high.id, Grader(GOOD))

    assert low_row.overall == 1.5 and low_row.review_status == "pending"
    assert high_row.review_status is None


async def test_the_threshold_is_configurable(on, monkeypatch):
    monkeypatch.setattr(settings, "auto_grading_low_score", 5.0)
    row = await _consultation(on)

    stored = await grade_consultation(row.id, Grader(GOOD))  # mean 4.5 < 5.0

    assert stored.review_status == "pending"


async def test_grading_twice_does_not_duplicate_or_spend_again(on):
    row = await _consultation(on)
    grader = Grader(GOOD)

    await grade_consultation(row.id, grader)
    assert await grade_consultation(row.id, grader) is None

    assert len(grader.prompts) == 1 and len(await _grades(on)) == 1


# --- a grade is never invented --------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        {**GOOD, "safety": 9},
        {**GOOD, "grounding": 0},
        {k: v for k, v in GOOD.items() if k != "safety"},
        {**GOOD, "justification": "x" * 601},
        "not json at all",
        ["a", "list"],
        None,
        {**GOOD, "grounding": "five"},
    ],
)
async def test_invalid_grader_output_is_a_failure_with_no_score(on, payload):
    row = await _consultation(on)

    stored = await grade_consultation(row.id, Grader(payload))

    assert stored.status == "failed" and stored.reason == "invalid_output"
    assert stored.scores == {} and stored.overall is None and stored.review_status is None


async def test_a_json_string_from_the_grader_is_accepted(on):
    import json

    row = await _consultation(on)

    stored = await grade_consultation(row.id, Grader(json.dumps(GOOD)))

    assert stored.status == "graded" and stored.overall == 4.5


async def test_a_provider_error_is_a_failure_carrying_its_reason_code(on):
    row = await _consultation(on)

    stored = await grade_consultation(row.id, Grader(exc=LLMUnavailableError("429 Too Many Requests")))

    assert stored.status == "failed" and stored.reason == "rate_limited" and stored.overall is None


async def test_a_slow_grader_times_out_as_a_failure(on, monkeypatch):
    monkeypatch.setattr(settings, "auto_grading_timeout_seconds", 0.05)
    row = await _consultation(on)

    stored = await grade_consultation(row.id, Grader(GOOD, delay=1.0))

    assert stored.status == "failed" and stored.reason == "timeout"


async def test_an_unexpected_grader_crash_never_escapes(on):
    row = await _consultation(on)

    stored = await grade_consultation(row.id, Grader(exc=RuntimeError("boom")))

    assert stored.status == "failed" and stored.reason == "internal_error"


# --- who may grade ----------------------------------------------------------


async def test_the_model_that_answered_does_not_grade_itself(on):
    row = await _consultation(on, calls=_answered_by("groq", "grader-model"))
    grader = Grader(GOOD, provider="groq", model="grader-model")

    stored = await grade_consultation(row.id, grader)

    assert stored.status == "skipped" and stored.reason == "same_model"
    assert grader.prompts == [] and stored.scores == {}


async def test_the_same_provider_with_another_model_may_grade(on):
    row = await _consultation(on, calls=_answered_by("groq", "llama-3.3-70b-versatile"))

    stored = await grade_consultation(row.id, Grader(GOOD, provider="groq", model="grader-model"))

    assert stored.status == "graded"


async def test_the_answering_call_is_the_last_successful_chat_not_a_failed_primary(on):
    calls = [
        {"kind": "chat", "provider": "gemini", "model": "g", "ok": False, "fallback": False},
        {"kind": "chat", "provider": "groq", "model": "grader-model", "ok": True, "fallback": True},
    ]
    row = await _consultation(on, calls=calls)

    stored = await grade_consultation(row.id, Grader(GOOD, provider="groq", model="grader-model"))

    assert stored.reason == "same_model"


async def test_a_remote_grader_is_refused_unless_phi_may_leave(on, monkeypatch):
    monkeypatch.setattr(settings, "ai_allow_phi", False)
    row = await _consultation(on)
    remote = Grader(GOOD, local=False)

    stored = await grade_consultation(row.id, remote)

    assert stored.status == "skipped" and stored.reason == "phi_not_allowed"
    assert remote.prompts == [], "nothing may be sent before the gate"


async def test_a_local_grader_is_fine_when_phi_may_not_leave(on, monkeypatch):
    monkeypatch.setattr(settings, "ai_allow_phi", False)
    row = await _consultation(on)

    stored = await grade_consultation(row.id, Grader(GOOD, provider="ollama", model="qwen3:8b", local=True))

    assert stored.status == "graded"


async def test_no_grader_configured_is_recorded(on, monkeypatch):
    monkeypatch.setattr(auto_grading, "build_grader_client", lambda: None)
    row = await _consultation(on)

    stored = await grade_consultation(row.id)

    assert stored.status == "skipped" and stored.reason == "not_configured"


# --- spend ceiling ----------------------------------------------------------


async def test_the_hourly_ceiling_skips_further_gradings(on, monkeypatch):
    monkeypatch.setattr(settings, "auto_grading_max_per_hour", 2)
    grader = Grader(GOOD)
    for i in range(4):
        row = await _consultation(on, f"C{i}", trace_id=f"tr-{i}")
        await grade_consultation(row.id, grader)

    statuses = [(g.status, g.reason) for g in await _grades(on)]

    assert statuses.count(("graded", None)) == 2
    assert statuses.count(("skipped", "budget")) == 2
    assert len(grader.prompts) == 2


async def test_the_daily_ceiling_counts_failures_but_not_skips(on, monkeypatch):
    monkeypatch.setattr(settings, "auto_grading_max_per_day", 2)
    monkeypatch.setattr(settings, "auto_grading_max_per_hour", 100)
    broken = Grader(exc=LLMUnavailableError("timeout"))
    for i in range(2):
        row = await _consultation(on, f"F{i}", trace_id=f"tr-f{i}")
        await grade_consultation(row.id, broken)
    over = await _consultation(on, "C-over", trace_id="tr-over")

    stored = await grade_consultation(over.id, Grader(GOOD))

    assert stored.reason == "budget"


async def test_gradings_older_than_the_window_do_not_count(on, monkeypatch):
    monkeypatch.setattr(settings, "auto_grading_max_per_hour", 1)
    old = await _consultation(on, "C-old", trace_id="tr-old")
    await grade_consultation(old.id, Grader(GOOD))
    (g,) = await _grades(on)
    g.created_at = datetime.utcnow() - timedelta(hours=2)
    await on.commit()
    fresh = await _consultation(on, "C-new", trace_id="tr-new")

    stored = await grade_consultation(fresh.id, Grader(GOOD))

    assert stored.status == "graded"


# --- running in the background ---------------------------------------------


async def test_scheduling_is_a_no_op_when_grading_is_off(monkeypatch):
    monkeypatch.setattr(settings, "enable_auto_grading", False)
    started = []
    monkeypatch.setattr(auto_grading, "grade_consultation", lambda cid: started.append(cid))

    schedule_auto_grade("C1")

    assert started == [] and not auto_grading._background


async def test_scheduling_runs_grading_detached_and_keeps_the_task(monkeypatch):
    monkeypatch.setattr(settings, "enable_auto_grading", True)
    ran = []

    async def fake(cid):
        ran.append(cid)

    monkeypatch.setattr(auto_grading, "grade_consultation", fake)

    schedule_auto_grade("C1")
    assert ran == [], "it must not run inline"
    await asyncio.gather(*list(auto_grading._background))

    assert ran == ["C1"] and not auto_grading._background


async def test_persisting_a_consultation_schedules_its_grading(db_session, monkeypatch):
    from api.routers import agents

    scheduled = []
    monkeypatch.setattr(agents, "schedule_auto_grade", scheduled.append)
    user = User(id="U1", email="g@example.org", name="G", hashed_password="x", role="clinician")
    db_session.add(user)
    await db_session.commit()

    consultation = await _persist(
        db_session,
        user,
        ConsultRequest(query="a clinical question"),
        {"final_answer": "ok", "trace": {"trace_id": "t"}},
    )

    assert scheduled == [consultation.id]


# --- queue, review token, dashboard ---------------------------------------


@pytest.fixture
def client(on, monkeypatch):
    monkeypatch.setattr(settings, "review_token", REVIEW_TOKEN)

    async def override_session():
        yield on

    app.dependency_overrides[get_session] = override_session
    yield AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    app.dependency_overrides.clear()


async def _clinician(client, email="ag@example.org"):
    res = await client.post(
        "/api/auth/register", json={"email": email, "name": "Dr. G", "password": "password123"}
    )
    body = res.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body["user"]["id"]


async def test_a_low_grade_joins_the_queue_next_to_human_ratings_oldest_first(client, on):
    h, uid = await _clinician(client)
    human = await _consultation(on, "C-h", trace_id="tr-h", user=uid)
    auto = await _consultation(on, "C-a", trace_id="tr-a", user=uid)
    await client.post(
        f"/api/agents/consultations/{human.id}/rating", headers=h, json={"value": "down", "reason": "other"}
    )
    await grade_consultation(auto.id, Grader(BAD))
    ok = await _consultation(on, "C-ok", trace_id="tr-ok", user=uid)
    await grade_consultation(ok.id, Grader(GOOD))
    skipped = await _consultation(on, "C-s", trace_id="tr-s", user=uid)
    await grade_consultation(skipped.id, Grader(GOOD, exc=LLMUnavailableError("x")))
    rating = (await on.execute(select(ResponseRating))).scalars().one()
    grade = (
        (
            await on.execute(
                select(AutoGrade).where(AutoGrade.status == "graded", AutoGrade.review_status == "pending")
            )
        )
        .scalars()
        .one()
    )
    rating.created_at, grade.created_at = datetime(2026, 10, 2), datetime(2026, 10, 1)
    await on.commit()

    items = (await client.get("/api/quality/queue", headers=h)).json()["items"]

    assert [(i["source"], i["consultation_id"]) for i in items] == [("auto", "C-a"), ("human", "C-h")]
    auto_item = items[0]
    assert auto_item["overall"] == 1.5 and auto_item["scores"]["grounding"] == 1
    assert auto_item["justification"] == "Claims lack support."
    assert auto_item["grader"] == "groq/grader-model" and auto_item["criteria_version"] == CRITERIA_VERSION


async def test_the_queue_paginates_across_both_sources(client, on):
    h, uid = await _clinician(client, "pg@example.org")
    for i in range(3):
        row = await _consultation(on, f"A{i}", trace_id=f"tr-a{i}", user=uid)
        await grade_consultation(row.id, Grader(BAD))
    for i in range(3):
        row = await _consultation(on, f"H{i}", trace_id=f"tr-h{i}", user=uid)
        await client.post(f"/api/agents/consultations/{row.id}/rating", headers=h, json={"value": "down"})
    base = datetime(2026, 10, 1)
    for n, entry in enumerate(
        sorted(
            (await on.execute(select(AutoGrade))).scalars().all()
            + (await on.execute(select(ResponseRating))).scalars().all(),
            key=lambda e: e.consultation_id,
        )
    ):
        entry.created_at = base + timedelta(hours=n)
    await on.commit()

    seen, offset = [], 0
    while True:
        page = (
            await client.get("/api/quality/queue", headers=h, params={"limit": 2, "offset": offset})
        ).json()
        seen += [i["consultation_id"] for i in page["items"]]
        if not page["has_more"]:
            break
        offset += 2

    assert seen == ["A0", "A1", "A2", "H0", "H1", "H2"]


async def test_a_clinician_closes_an_automatic_item(client, on):
    h, uid = await _clinician(client, "rv@example.org")
    row = await _consultation(on, "C1", user=uid)
    await grade_consultation(row.id, Grader(BAD))
    item_id = (await client.get("/api/quality/queue", headers=h)).json()["items"][0]["item_id"]

    res = await client.post(
        f"/api/quality/queue/{item_id}/review", headers=h, json={"outcome": "model_failure", "note": "agree"}
    )

    assert (
        res.status_code == 200
        and res.json()["source"] == "auto"
        and res.json()["review_status"] == "reviewed"
    )
    assert (await client.get("/api/quality/queue", headers=h)).json()["items"] == []
    again = await client.post(
        f"/api/quality/queue/{item_id}/review", headers=h, json={"outcome": "no_action"}
    )
    assert again.status_code == 409
    (g,) = await _grades(on)
    assert g.reviewed_by == uid and g.reviewed_at is not None


async def test_graded_well_skipped_and_failed_rows_cannot_be_closed(client, on):
    h, uid = await _clinician(client, "nc@example.org")
    ids = {}
    for name, grader in (
        ("ok", Grader(GOOD)),
        ("failed", Grader(exc=LLMUnavailableError("x"))),
        ("same", Grader(GOOD, provider="gemini", model="gemini-flash-latest")),
    ):
        row = await _consultation(on, f"C-{name}", trace_id=f"tr-{name}", user=uid)
        ids[name] = (await grade_consultation(row.id, grader)).id

    for name, grade_id in ids.items():
        res = await client.post(
            f"/api/quality/queue/{grade_id}/review", headers=h, json={"outcome": "no_action"}
        )
        assert res.status_code == 404, name


async def test_the_review_token_sees_the_automatic_item_without_identifiers(client, on):
    _, uid = await _clinician(client, "tk@example.org")
    row = await _consultation(on, "C1", user=uid)
    bad = {**BAD, "justification": "Contact maria@example.org about the dose."}
    await grade_consultation(row.id, Grader(bad))

    res = await client.get("/api/review/queue", headers={"X-Review-Token": REVIEW_TOKEN})

    item = res.json()["items"][0]
    assert item["source"] == "auto" and item["overall"] == 1.5 and item["trace_id"] == "tr-C1"
    assert "maria@example.org" not in res.text and "[EMAIL]" in item["justification"]
    assert "item_id" not in item and "consultation_id" not in item


async def test_the_review_detail_shows_the_grade_or_why_there_is_none(client, on):
    _, uid = await _clinician(client, "dt@example.org")
    graded = await _consultation(on, "C-g", trace_id="tr-g", user=uid)
    skipped = await _consultation(
        on, "C-s", trace_id="tr-s", user=uid, calls=_answered_by("groq", "grader-model")
    )
    await grade_consultation(graded.id, Grader(GOOD))
    await grade_consultation(skipped.id, Grader(GOOD))
    token = {"X-Review-Token": REVIEW_TOKEN}

    g = (await client.get("/api/review/consultations/tr-g", headers=token)).json()["auto_grade"]
    s = (await client.get("/api/review/consultations/tr-s", headers=token)).json()["auto_grade"]

    assert g["status"] == "graded" and g["overall"] == 4.5 and g["grader"] == "groq/grader-model"
    assert s["status"] == "skipped" and s["reason"] == "same_model" and s["overall"] is None


async def test_the_detail_of_an_ungraded_consultation_has_no_grade(client, on):
    _, uid = await _clinician(client, "ng@example.org")
    await _consultation(on, "C1", user=uid)

    body = (
        await client.get("/api/review/consultations/tr-C1", headers={"X-Review-Token": REVIEW_TOKEN})
    ).json()

    assert body["auto_grade"] is None


async def test_dashboard_reports_how_many_were_graded_and_the_average_per_criterion(client, on):
    h, uid = await _clinician(client, "db@example.org")
    empty = (await client.get("/api/dashboard/ai", headers=h)).json()
    assert empty["auto_graded_count"] == 0 and empty["auto_grade_averages"] == {}
    for name, payload in (("a", GOOD), ("b", BAD)):
        row = await _consultation(on, f"C-{name}", trace_id=f"tr-{name}", user=uid)
        await grade_consultation(row.id, Grader(payload))
    broken = await _consultation(on, "C-x", trace_id="tr-x", user=uid)
    await grade_consultation(broken.id, Grader(exc=LLMUnavailableError("x")))

    body = (await client.get("/api/dashboard/ai", headers=h)).json()

    assert body["auto_graded_count"] == 2, "failed gradings are not graded"
    assert body["auto_grade_averages"] == {
        "grounding": 3.0,
        "completeness": 3.0,
        "safety": 3.5,
        "abstention": 2.5,
    }


# --- configuration ---------------------------------------------------------


def test_grading_needs_a_provider_and_model_to_be_enabled():
    with pytest.raises(ValueError, match="auto_grading_provider"):
        Settings(enable_auto_grading=True, auto_grading_sample_rate=0.1)
    with pytest.raises(ValueError, match="sample_rate"):
        Settings(
            enable_auto_grading=True,
            auto_grading_sample_rate=1.5,
            auto_grading_provider="groq",
            auto_grading_model="m",
        )


def test_grading_is_off_by_default_and_a_disabled_config_is_not_validated():
    s = Settings(auto_grading_sample_rate=5)

    assert s.enable_auto_grading is False and Settings().auto_grading_sample_rate == 0.0
    assert s.auto_grading_provider is None


def test_the_grader_is_a_registered_phi_seam():
    from sephiroth.models.egress import PHI_SEAMS

    assert "api.services.auto_grading" in PHI_SEAMS


def test_the_grader_client_is_a_single_provider_never_a_fallback(monkeypatch):
    from sephiroth.models import build_grader_client
    from sephiroth.models.fallback import FallbackLLMClient

    monkeypatch.setattr(settings, "auto_grading_provider", "groq")
    monkeypatch.setattr(settings, "auto_grading_model", "grader-model")
    monkeypatch.setattr(settings, "groq_api_key", "k")

    client = build_grader_client()

    assert not isinstance(client, FallbackLLMClient)
    assert client.describe().provider == "groq" and client.describe().model == "grader-model"
    monkeypatch.setattr(settings, "auto_grading_provider", None)
    assert build_grader_client() is None
