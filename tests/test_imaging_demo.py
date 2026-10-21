"""The demo imaging studies that ship with the deployment (AB#32).

"Recent imaging analyses" showed "No preview" everywhere because a study's image
was a path on the machine that generated it, and the samples are not (and may not
be) in the repository or the container. A demo study names its image as
`demo:<file>`, which resolves to a file that is always there.
"""

import json
from datetime import date

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from api.routers import medical as medical_module
from auth import router as auth_router_module
from core.db import get_session
from data.schemas import Patient, TimelineEvent
from scripts import seed_imaging_demo

CREDS = {"email": "imaging-demo@example.org", "name": "Dr. Demo", "password": "password123"}

pytestmark = pytest.mark.asyncio


@pytest.fixture
def app(db_session):
    api = FastAPI()
    api.include_router(auth_router_module.router, prefix="/api/auth")
    api.include_router(medical_module.router, prefix="/api/medical")

    async def override_session():
        yield db_session

    api.dependency_overrides[get_session] = override_session
    return api


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
async def headers(client):
    token = (await client.post("/api/auth/register", json=CREDS)).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _patients(session, n=4):
    for i in range(n):
        session.add(
            Patient(id=f"PDEMO{i}", name=f"Paciente {i}", age=50, sex="F", medical_record_number=f"MRN-D{i}")
        )
    await session.commit()


async def _event(session, detail, title="XRAY vision description"):
    await _patients(session, 1)
    session.add(
        TimelineEvent(
            patient_id="PDEMO0",
            date=date(2026, 10, 1),
            type="imaging",
            title=title,
            detail=detail,
            ai_generated=True,
        )
    )
    await session.commit()


class TestTheBundledStudies:
    async def test_every_study_has_its_image_and_a_complete_analysis(self):
        analyses = seed_imaging_demo.load_analyses()

        assert len(analyses) >= 3
        for a in analyses:
            assert (seed_imaging_demo.DEMO_DIR / a["file"]).is_file()
            assert a["model"] and a["generated_on"]
            assert len(a["description"].split()) >= 40
            assert a["description"].rstrip().endswith((".", ")"))

    async def test_nothing_in_the_dockerignore_keeps_them_out_of_the_image(self):
        """The reason the old samples never reached the container."""
        from fnmatch import fnmatch
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        rules = [
            line.strip().rstrip("/")
            for line in (root / ".dockerignore").read_text().splitlines()
            if line.strip() and not line.startswith(("#", "!"))
        ]
        for name in [*(a["file"] for a in seed_imaging_demo.load_analyses()), "analyses.json"]:
            rel = f"platform/api/static/imaging-demo/{name}"
            hit = [r for r in rules if rel.startswith(r + "/") or fnmatch(rel, r) or fnmatch(name, r)]
            assert not hit, f"{rel} is excluded from the image by {hit}"


class TestResolvingAStudy:
    async def test_a_demo_name_resolves_to_the_bundled_file(self):
        name = seed_imaging_demo.load_analyses()[0]["file"]

        path = medical_module._resolve_allowed_image_path(f"demo:{name}")

        assert path.is_file() and path.name == name

    @pytest.mark.parametrize(
        "raw", ["demo:../analyses.json", "demo:analyses.json", "demo:nope.webp", "demo:", "demo:/etc/passwd"]
    )
    async def test_the_prefix_is_not_a_way_to_read_other_files(self, raw):
        with pytest.raises(HTTPException) as err:
            medical_module._resolve_allowed_image_path(raw)

        assert err.value.status_code == 404

    async def test_the_preview_route_serves_it_to_a_clinician(self, client, headers):
        name = seed_imaging_demo.load_analyses()[0]["file"]

        res = await client.get(
            "/api/medical/imaging/preview", params={"path": f"demo:{name}"}, headers=headers
        )

        assert res.status_code == 200
        assert res.headers["content-type"] == "image/webp"

    async def test_the_preview_route_still_needs_a_login(self, client):
        res = await client.get("/api/medical/imaging/preview", params={"path": "demo:xray.webp"})

        assert res.status_code == 401


class TestTheSamplePanel:
    async def test_it_lists_the_studies_with_a_name_the_preview_route_accepts(self, client, headers):
        studies = (await client.get("/api/medical/imaging/demo", headers=headers)).json()

        assert len(studies) == len(seed_imaging_demo.load_analyses())
        for study in studies:
            assert study["image"].startswith("demo:") and study["description"] and study["model"]
            res = await client.get(
                "/api/medical/imaging/preview", params={"path": study["image"]}, headers=headers
            )
            assert res.status_code == 200

    async def test_it_needs_a_login(self, client):
        assert (await client.get("/api/medical/imaging/demo")).status_code == 401


class TestRecentAnalyses:
    async def test_a_demo_study_has_its_image(self, client, headers, db_session):
        name = seed_imaging_demo.load_analyses()[0]["file"]
        await _event(db_session, f"[image_path:demo:{name}] [model:m] A description.")

        item = (await client.get("/api/medical/imaging/recent", headers=headers)).json()[0]

        assert item["image_path"] == f"demo:{name}"
        assert item["preview_unavailable"] is None
        assert item["description"] == "A description."

    async def test_a_file_that_is_not_on_this_server_says_so(self, client, headers, db_session):
        await _event(
            db_session, "[image_path:/Users/someone/real_data/imaging/samples/ct.png] [model:m] Text."
        )

        item = (await client.get("/api/medical/imaging/recent", headers=headers)).json()[0]

        assert item["image_path"] is None
        assert item["preview_unavailable"] == "file_missing"

    async def test_a_file_that_is_not_an_image_says_so(self, client, headers, db_session):
        await _event(db_session, "[image_path:/tmp/study.dcm] [model:m] Text.")

        item = (await client.get("/api/medical/imaging/recent", headers=headers)).json()[0]

        assert item["preview_unavailable"] == "unsupported_format"

    async def test_an_unknown_demo_name_is_a_missing_file(self, client, headers, db_session):
        await _event(db_session, "[image_path:demo:gone.webp] [model:m] Text.")

        item = (await client.get("/api/medical/imaging/recent", headers=headers)).json()[0]

        assert (item["image_path"], item["preview_unavailable"]) == (None, "file_missing")

    async def test_an_event_with_no_image_at_all_says_so(self, client, headers, db_session):
        await _event(db_session, "Linked sample file: ct.png", title="Chest X-ray")

        item = (await client.get("/api/medical/imaging/recent", headers=headers)).json()[0]

        assert (item["image_path"], item["preview_unavailable"]) == (None, "no_image")

    async def test_a_real_file_inside_the_server_still_previews(self, client, headers, db_session, tmp_path):
        image = tmp_path / "scan.png"
        image.write_bytes(b"\x89PNG")
        await _event(db_session, f"[image_path:{image}] [model:m] Text.")

        item = (await client.get("/api/medical/imaging/recent", headers=headers)).json()[0]

        assert item["image_path"] == str(image)
        assert item["preview_unavailable"] is None

    async def test_it_needs_a_login(self, client):
        assert (await client.get("/api/medical/imaging/recent")).status_code == 401


class TestSeeding:
    async def test_it_adds_one_event_per_study_in_the_format_the_page_parses(self, db_session):
        await _patients(db_session)
        studies = seed_imaging_demo.load_analyses()

        added = await seed_imaging_demo.seed(db_session, today=date(2026, 10, 20))

        assert added == len(studies)
        events = (
            (await db_session.execute(select(TimelineEvent).where(TimelineEvent.type == "imaging")))
            .scalars()
            .all()
        )
        assert {e.detail.split("]")[0] for e in events} == {f"[image_path:demo:{a['file']}" for a in studies}
        assert all(e.ai_generated for e in events)
        assert all(medical_module._IMAGE_PATH_RE.match(e.detail) for e in events)

    async def test_running_it_twice_adds_nothing(self, db_session):
        await _patients(db_session)
        await seed_imaging_demo.seed(db_session)

        assert await seed_imaging_demo.seed(db_session) == 0
        total = await db_session.scalar(select(func.count()).select_from(TimelineEvent))
        assert total == len(seed_imaging_demo.load_analyses())

    async def test_it_leaves_other_imaging_events_alone(self, db_session):
        await _event(db_session, "[image_path:/x/y.png] [model:m] Mine.")
        await _patients(db_session, 0)

        await seed_imaging_demo.seed(db_session)

        kept = (
            (await db_session.execute(select(TimelineEvent).where(TimelineEvent.detail.contains("Mine."))))
            .scalars()
            .all()
        )
        assert len(kept) == 1

    async def test_the_analyses_file_is_valid_json(self):
        assert isinstance(json.loads((seed_imaging_demo.DEMO_DIR / "analyses.json").read_text()), list)
