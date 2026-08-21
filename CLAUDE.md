# SEPHIROTH — Project Context

## What This Is

An **AI-powered clinical decision support platform** for healthcare professionals. Patients upload histories, imaging, and lab data; specialized AI agents (powered by the Google Gemini API) extract findings, retrieve evidence from medical literature, check drug interactions, and generate structured, cited recommendations.

⚠️ **For research, education, and professional support only.** Not a medical device; all AI recommendations must be reviewed by a qualified healthcare professional before clinical use.

⚠️ **Privacy:** clinical text and medical images are sent to the Google Gemini API (AI Studio free tier). This is not HIPAA/GDPR-compliant as-is, and the free tier may use submitted data to improve Google's models. Use only with synthetic/de-identified data unless you migrate to Vertex AI with a BAA.

## Tech Stack

- **LLM**: Google Gemini API (`gemini-flash-latest`, a Google-maintained alias for the current recommended flash model), free AI Studio tier — no local model to run. Optional Groq fallback for text/tool-calling when Gemini's quota is exhausted (`GROQ_API_KEY`).
- **Agents**: `Agent` instances (bound to a capability record, `src/sephiroth/runtime/`) orchestrated by a purpose-built async executor, each with MCP tools
- **Tools (MCP servers)**: Clinical NLP, medical imaging analysis, evidence retrieval, drug safety checks — all in `intelligence/mcp/`
- **Backend**: FastAPI + PostgreSQL + pgvector
- **Frontend**: Next.js 14 (TypeScript, Tailwind, Radix) — design system from Nexura Care (healthcare dashboard), adapted for AI copilot domain
- **Container**: Docker Compose (Postgres + API)

## Folders at a Glance

| Folder | Purpose |
|---|---|
| `platform/api/` | FastAPI routes (routers in `routers/`, main.py with CORS/lifespan) |
| `platform/core/` | Config (`config.py`) + async DB engine/sessions/seed (`db.py`) |
| `platform/auth/` | JWT auth: `security.py` (bcrypt+pyjwt), `deps.py` (`get_current_user`), `router.py` (register/login/me) |
| `platform/frontend/` | Next.js app (pages in `app/`, components in `components/`, design tokens in Tailwind config) |
| `src/sephiroth/models/` | `GeminiClient` (chat/tool-call loop, structured output, vision) + `GroqClient` (text-only fallback) + `FallbackLLMClient` (composes both) + `factory.py` (`get_llm_client()` singleton), all behind the `ModelProvider` protocol |
| `src/sephiroth/tools/` | `ToolRuntime` (relocated MCP registry — capability tags, per-call timeout, dispatch-time whitelist enforcement) |
| `src/sephiroth/runtime/` | `Agent` + 5 capability records + the async executor (fan-out/merge/coordinate, replacing LangGraph — see `docs/08-decisions/ADR-001-remove-langgraph.md`); internal state is a real `RunState` since Phase 4 |
| `src/sephiroth/verification/` | Claim extraction, evidence harvesting, 5-state claim verification (`VerificationStatus`), deterministic confidence scoring — `citation_guard` feeds it as a pre-filter (ADR-006) |
| `src/sephiroth/safety/` | Abstention gating (`answer`/`partial`/`abstain`, ADR-008) + a minimal input prompt-injection heuristic |
| `src/sephiroth/context/` | Per-agent context views, lexical MMR reranking, per-patient consultation memory, character-budget truncation (ADR-011) |
| `src/sephiroth/telemetry/` | `build_trace` projects `RunState` into the persisted `ExecutionTrace`; `traced_span` records real spans for the executor/verifier seams (ADR-009) |
| `intelligence/mcp/` | FastMCP servers (nlp, imaging, rag, drug_safety, vision — vision shares the same Gemini client, model override via `gemini_vision_model`); the registry/dispatcher itself lives in `src/sephiroth/tools/` |
| `intelligence/agents/` | Thin `Agent` wrappers (shim into `src/sephiroth/runtime/`). `citation_guard.py`/`explainability.py`/`risk_engine.py` are Phase-5 shims into `src/sephiroth/verification`/`telemetry`/`safety` respectively — real logic lives there now |
| `intelligence/nlp/` | `timeline_extractor.py` (note → timeline events via structured LLM output). The vendored MedCAT tree (`ner/`, `pipeline/`, `preprocessing/`) was deleted in Phase 5 (`DEBT-001`) — it had zero call sites |
| `data/rag/` | Evidence retrieval with mandatory citations (seeded guideline corpus + PubMed) |
| `data/schemas/` | SQLAlchemy 2.0 models (User, Patient, TimelineEvent, ClinicalNote, Consultation) |
| `tests/` | pytest suite (auth, citation guard, timeline fallback) — SQLite in-memory, no services needed, no API key needed |
| `data/embeddings/` | Gemini embedding providers (live + cached-artifact) powering hybrid RAG retrieval |
| `data/vectors/` | In-memory vector store (cosine similarity) used by `RAGPipeline` |
| `references/` | Cloned open-source projects (don't edit; reference only) |
| `real_data/` | Optional real/synthetic sample data (Synthea patients+notes, DDInter drug interactions, RSNA imaging fixtures) — see `real_data/README.md`; never required for tests/CI |
| `migrations/` | Alembic schema migrations for Postgres (local docker-compose + Supabase). SQLite tests never touch this — see "Database migrations" below |

## Design System (Frontend)

All colors + typography live in `platform/frontend/tailwind.config.ts`. Reuse them; don't invent new colors:

| Token | Value | Usage |
|---|---|---|
| Primary | `#3683F8` | Buttons, active nav, links |
| Ink | `#060606` | Body text |
| Surface | `#EBF3FE` | Page background |
| Border | `#D8D8D8` | Dividers, card edges |
| **Sephiroth gradient** | `#8C92AC` → `#D1D5DB` | Agent badges, AI-insight cards, copilot avatar ring (marks AI-generated content) |
| Font | Manrope (400/500/600/700) | All text |

## How It Works (Architecture)

```
User Query
    ↓
FastAPI endpoint (agents.py, patients.py, etc.)
    ↓
ClinicalCoordinator agent (Agent bound to the coordinator capability)
    ↓
Gemini (tool-calling loop in src/sephiroth/models/gemini.py)
    ↓
├─ RadiologyAgent + imaging_server → MONAI inference + vision description
├─ LabAgent + patient data → lab result interpretation
├─ EvidenceAgent + rag_server → PubMed/guidelines search + citations
├─ DrugSafetyAgent + drug_safety_server → interaction checking
└─ Final answer aggregated, returned with source citations
    ↓
Frontend displays agent badges (Sephiroth gradient), cites sources
```

Each agent is an `Agent` (`src/sephiroth/runtime/agent.py`) bound to an `AgentCapability` record with:
- A **system prompt** (clinical reasoning instructions)
- A list of **allowed MCP tools** (what it can call)
- A `.run(query, context)` method (calls `client.chat(...)`)

MCP tools are FastMCP servers in `intelligence/mcp/`:
- `nlp_server.py` → wraps `intelligence/nlp.ClinicalEntityExtractor` (disease/med/procedure extraction)
- `imaging_server.py` → wraps `intelligence.medical_imaging.MedicalImageAnalyzer` (segmentation, classification)
- `rag_server.py` → wraps `data.rag.RAGPipeline` (evidence search with citations)
- `drug_safety_server.py` → drug interaction checking
- `vision_server.py` → wraps `GeminiClient.describe_image()` (multimodal image description)

`ToolRuntime` (`src/sephiroth/tools/runtime.py`) discovers all servers (`SERVERS` in `src/sephiroth/tools/servers.py`), aggregates their tool schemas into:
1. **`llm_tools()`** — OpenAI-style function-calling schemas, converted to Gemini's `FunctionDeclaration` format inside `GeminiClient`
2. **System prompt summary** (human-readable tool descriptions, prepended to agent's system prompt)

## Key Design Decisions

1. **Cloud LLM via Gemini, not local Ollama.** Migrated from a fully local Ollama setup to the free Google Gemini API — the only free tier covering native multi-round tool-calling, JSON-Schema structured output, and vision in one provider. PHI now leaves the machine; see the privacy notice above.
2. **One shared `GeminiClient`, no host/Docker split.** `sephiroth.models.factory::get_llm_client()` is a lazy singleton used by agents, timeline extraction, and vision alike — one API key, one rate limiter, one retry/backoff path.
3. **One agent per MCP server.** Specialist agents are small and focused; the executor in `src/sephiroth/runtime/` orchestrates them.
4. **Sephiroth gradient = AI signal.** Whenever the UI shows AI-generated content, that gradient appears (badge, card border, etc.). Helps users trust the source.
5. **All answers must cite sources.** EvidenceAgent always returns `(finding, [source_citation1, source_citation2, ...])`. This is baked into the RAG pipeline.
6. **Citation Guard on every answer.** `src/sephiroth/verification/citation_guard.py` (relocated verbatim from `intelligence/agents/citation_guard.py` in Phase 5; that shim was deleted in Phase 6) audits the coordinator's final answer against actual tool output; fabricated citations are stripped (`[unverified — removed]`) and reported in `citation_report` (shown in the UI). Since Phase 4 it's a pre-filter feeding claim-level verification, not the terminal check — see #15.
15. **Claim verification and abstention gate every consultation.** `src/sephiroth/verification/` decomposes the (citation-sanitized) answer into claims and classifies each against retrieved evidence content (5-state `VerificationStatus`, not citation_guard's binary check); `src/sephiroth/safety/abstention.py` gates on the result — an unsupported high-risk claim, a contradiction, or low confidence overrides a plain `answer` with `partial` (caveat banner) or `abstain` (declines, replacing the answer). Confidence is always derived from existing signals, never self-reported by the model.
16. **Each agent sees only the context fields it declares.** `AgentCapability.context_fields` (`src/sephiroth/runtime/registry.py`) names which `RunContext` fields an agent needs; `src/sephiroth/context/views.py::context_for_agent` projects down to just those before the executor calls it. "Memory" is scoped narrowly to a patient's own recent consultations (`src/sephiroth/context/memory.py`, injected by the router into `context["recent_consultations"]`, seen only by the coordinator) — not a generic multi-turn chat session, which doesn't exist in this product yet (see ADR-011).
17. **Every consultation builds a replayable trace, persisted alongside it.** `src/sephiroth/telemetry/build_trace` projects the executor's `RunState` into `ExecutionTrace` (`sephiroth.contracts.trace`) at the end of a run; `traced_span` records real timing spans around each agent turn and the verification pass, redacted via an attribute allow-list (never patient content). Toggled by `settings.enable_tracing` — disabling it must not change anything else about a run's result (ADR-009).
7. **Auth = JWT, two roles.** `User.role` (`"clinician"` | `"patient"`) plus a nullable, unique `patient_id` FK bind a portal login to exactly one `Patient` record. Role is re-read from the DB on every request (`auth/deps.py`), never carried in the JWT, so a role change takes effect immediately. Clinician-only routers (`patients`, `dashboard`, `agents`, `medical`, `rag`) carry a router-level `dependencies=[Depends(require_clinician)]`, so a new route added to any of those files is protected the moment it exists. Consultations are persisted per user (`consultations` table); patients are shared across clinicians (no per-clinician scoping — every clinician sees every patient, unchanged). `JWT_SECRET` must be a strong, non-default value in staging/production — `Settings` fails fast at startup otherwise (see `platform/core/config.py`).
23. **The landing page at `/` and the brand mark.** `app/(marketing)/` is a route group with its own nav/footer (`components/landing/`), escaping `AppShell`'s chrome via the same `isChromelessRoute()` predicate the login/claim pages use. A logged-in visitor never sees it: an inline `<head>` script (`lib/auth-gate.ts`, same pre-paint pattern as `THEME_INIT_SCRIPT`) checks `localStorage` and redirects to `/dashboard` or `/portal` before first paint — deliberately no `middleware.ts`, same reasoning as decision #22. The brand mark (`components/brand/wing-mark.tsx`, `app/icon.svg`) is an original, hand-authored single-wing signature built from stated arithmetic construction rules (one quadratic spine + feather-rib arcs) — nothing traced from any existing character or logo. It renders in `currentColor`/stroke, never the `sephiroth` gradient, which stays reserved as the "this is AI-generated" signal (decision #4) — the landing page's 4 interactive demos (`components/landing/`) are the only place that gradient appears outside the main app, and only on the mock AI-output cards within them.
22. **Frontend role gating is client-side only, on purpose.** `components/auth-guard.tsx` redirects a patient away from clinician routes and vice versa, but there is deliberately no `middleware.ts` — the JWT lives in `localStorage`, invisible to Next middleware, and moving to an `httpOnly` cookie to enable one is an explicit non-goal (CSRF handling, every `authHeaders()` call site, CORS credentials config). Every backend route enforces its own role check independently (Phase A/B/C); the frontend guard's job is UX (don't show a patient the Copilot link), not the security boundary. `lib/auth.ts::homeFor(role)` is the one place "which role goes where" is decided — the login page, the claim page, and the guard all call it rather than each hardcoding `/dashboard` or `/portal`.
21. **Scheduling + exam-results sharing.** `platform/api/routers/scheduling.py` and `results.py` add clinician working hours (`AvailabilityRule`/`AvailabilityException`), appointment booking, and result sharing — all role-scoped per-route (never a blanket router guard, since both a clinician and a patient legitimately call most of these endpoints with different visibility). Slots are computed on the fly (`platform/api/scheduling.py::expand_slots`, a pure function, never materialized) from rules/exceptions/existing bookings; conflict rules (half-open interval overlap, past-date/180-day-horizon rejection, patient/clinician double-booking) are enforced server-side inside `POST /api/scheduling/appointments`. Cancellation is a status change, never a row delete. A shared "exam result" is an existing `TimelineEvent` (`type in ("lab","imaging")`), not a new entity — `ResultShare` only records the act of sharing (message, `viewed_at`); attachments live in Postgres `LargeBinary` (`deferred=True`), capped at 10MB/3-files-per-share, behind a `platform/core/storage.py` seam so a later move to object storage is one class, not a router rewrite.
20. **No patient self-registration — ever.** A patient account is created only by redeeming a clinician-issued, one-time claim code (`PatientInvite`, bcrypt-hashed secret, 72h TTL) at public `POST /api/auth/portal/claim`. `POST /api/auth/register` is clinician-only (gated by `require_clinician_for_registration`, with `settings.allow_bootstrap_registration` — default on — letting the first account exist on a fresh database). The patient portal (`platform/api/routers/portal.py`) derives the patient from the token only (`current_patient_record`) — no handler in that router ever takes a `patient_id` parameter, so there's no id for a caller to tamper with. Portal reads deliberately show a trimmed, non-clinical view (`_portal_view`, not `patients.py::_full`) — no rule-derived `risk_level`/`risk_flags`, and the timeline filters out AI-generated events unless a clinician has explicitly shared one.
8. **Streaming via SSE.** `POST /api/agents/consult/stream` emits `routing` → `agent_completed`(×N) → `final` → `persisted` (carries the consultation id so Export PDF works without a reload); the frontend parses it with fetch+ReadableStream (EventSource can't POST).
9. **Explainability is derived, never stored.** `src/sephiroth/telemetry/explain.py` (relocated verbatim from `intelligence/agents/explainability.py` in Phase 5; that shim was deleted in Phase 6) builds the reasoning trace on read from persisted `agents`/`tool_calls`/`citation_report` — template-based, no LLM call, so improving templates needs no backfill.
10. **Risk flags are computed at read-time.** `src/sephiroth/safety/risk.py` (relocated verbatim from `intelligence/agents/risk_engine.py` in Phase 5, that shim deleted in Phase 6; curated lab rules + the drug-safety interaction table via `find_interactions`) runs inside `_summary()`/`_full()` in `patients.py` — no new columns, no background jobs.
11. **Vision = one MCP tool, same client.** `describe_medical_image` (vision_server.py) does one-shot `GeminiClient.describe_image()`; the RadiologyAgent is prompted to call it first when `image_path` is in context. It reads rendered images (PNG/JPG…), not raw DICOM. Degrades gracefully (`status: "unavailable"`) if the API key is missing or the request fails.
12. **Image preview shares the imaging trust boundary.** `GET /api/medical/imaging/preview` (medical.py) streams back the same local file `describe_medical_image`/`analyze_medical_image` already read, hard-restricted to browser-renderable extensions (png/jpg/jpeg/gif/webp/bmp) so it can't become a general file-download route. Powers the side-by-side viewer on `/imaging`.
13. **Free-tier quota is a real constraint.** `llm_max_tool_rounds` (default 6) and a shared per-client rate limiter (`gemini_rpm_limit`) keep a single consultation (5 agents, each doing several tool-call rounds) inside the AI Studio free tier. See README's Gemini quota section before raising these.
19. **Routing can be model-driven, behind a flag.** `settings.enable_dynamic_planner` (default `False`) switches `_route` in `src/sephiroth/runtime/executor.py` from the static key-presence heuristic (`route_specialists`) to `route_specialists_dynamic`, which asks the model which specialists are relevant via one `generate_json` call. Any failure — exception, non-dict payload, empty/unknown-only agent list — silently degrades back to the static heuristic; the frozen `routing` SSE event's shape never changes, only which names populate `agents` (ADR: none, closes SPEC-003 NG-1 per SPEC-008).
18. **A failing specialist no longer aborts the consultation.** `src/sephiroth/runtime/recovery.py` classifies an exception into a `FailureCategory` (`MODEL` for `LLMUnavailableError`, `AGENT` otherwise) and picks `RETRY` (transient, attempts remain) or `ABSTAIN`; `_run_specialist` retries up to `MAX_AGENT_ATTEMPTS=2`, and on exhaustion the run continues with that specialist's section simply empty instead of raising. `RunState.lifecycle`/`.failures`/`.retries`/`.recovery_actions` (typed since Phase 0) are populated for the first time. `FALLBACK`/`REPLAN` stay unimplemented — no alternate agent per capability, no dynamic planner yet (ADR-007, SPEC-007).
14. **Optional Groq fallback.** `sephiroth.models.factory::get_llm_client()` returns a `FallbackLLMClient` instead of a bare `GeminiClient` when `GROQ_API_KEY` is set: `chat()`/`generate_json()` try Gemini first, then Groq on any `LLMUnavailableError` (rate limit, daily quota exhaustion, outage). Embeddings always stay on Gemini (no Groq equivalent). `describe_image()`/`describe_image_stream()` (vision) fall through to Groq too, but ONLY when `GROQ_VISION_MODEL` is explicitly set — off by default, since Groq's vision model lineup has churned (Llama 4 Scout/Maverick both deprecated in favor of text-only replacements); this is a deliberate best-effort opt-in, not a guaranteed fallback (`GroqClient.describe_image`/`describe_image_stream`, `src/sephiroth/models/groq.py`). Streaming vision can't retry mid-stream once a chunk has reached the caller — `FallbackLLMClient.describe_image_stream` only falls back if the primary fails *before* yielding anything.

## How to Extend

### Add a New Agent

1. Add an `AgentCapability` record to `src/sephiroth/runtime/registry.py` — `id`
   (hyphenated display name), `role_prompt` (clinical reasoning for that
   domain; the system prompt is assembled in `agent.py` from the disclaimer +
   `role_prompt` + tool catalog), and `tools` (allowed MCP tools)
2. Select it from `route_specialists` in `planner.py`
3. Add an entry to `_ACTION_TEMPLATES`/`_NO_TOOL_ACTIONS` in `explainability.py` —
   `explanation` is rebuilt on read, so a missing template also degrades how
   *historical* consultations render

Example (see `docs/04-development/setup.md` for more):
```python
PATHOLOGY = AgentCapability(
    id="pathology",
    role_prompt="You are a pathology specialist...",
    tools=["pathology_analyzer", "specimen_database"],
)
```

### Add a New MCP Tool

1. Create `intelligence/mcp/my_new_server.py` with a FastMCP app
2. Declare tools with `@mcp.tool` decorators, calling your implementation from `intelligence/` or `data/`
3. Register the server in `SERVERS` in `src/sephiroth/tools/servers.py`
4. Add the tool name to the `allowed_tools` of each agent's `AgentCapability` —
   the whitelist is enforced at dispatch by `ToolRuntime.scoped_executor()`, so
   an unlisted tool returns an authorization error instead of running

See existing servers (`nlp_server.py`, `imaging_server.py`) for the pattern.

### Add API Endpoints

1. Create router in `platform/api/routers/my_feature.py`
2. Import and include it in `platform/api/main.py`
3. Follow the pattern in `docs/04-development/setup.md`

### Update Frontend

Pages go in `platform/frontend/app/`. Components in `platform/frontend/components/`. Import design tokens from `tailwind.config.ts`:
```tsx
// Use the Sephiroth gradient on an AI badge
<div className="bg-gradient-to-r from-sephiroth-start to-sephiroth-end text-white px-3 py-1 rounded">
  AI-Generated
</div>
```

## Running Locally

**Important:** `platform/` must NOT be a Python package (no `__init__.py` at its root) —
the name would shadow the stdlib `platform` module. It goes on `PYTHONPATH` instead, and
its subpackages are imported as top-level (`from core.config import settings`,
`uvicorn api.main:app`).

### One-time setup
```bash
python3.11 -m venv .venv                               # system python3 is 3.9 — too old
.venv/bin/pip install -r requirements.txt
cd platform/frontend && npm install && cd ../..
# Get a free key at https://aistudio.google.com/apikey and put it in .env:
echo 'GEMINI_API_KEY=your-key-here' >> .env
```

### Start everything
```bash
# Terminal 1: Postgres
docker compose up -d postgres

# Terminal 2: Backend (runs `alembic upgrade head` + seeds P001/P002 on first boot)
PYTHONPATH=.:platform .venv/bin/uvicorn api.main:app --reload --port 8000

# Terminal 3: Frontend (proxies /api/* to the backend)
cd platform/frontend && npm run dev -- --port 3100
```

**Port gotchas on this machine** (another project's Docker stack squats the default ports):
- `*:8000`, `*:3000`, and `*:5432` are all taken by other containers.
- Backend: always test via `http://127.0.0.1:8000` (IPv4). Frontend: port **3100**.
- Our Postgres maps to host **5433** (set in `.env`, which overrides `core/config.py` defaults).
- **Using Supabase instead of local Postgres?** Set `DATABASE_URL` in `.env` to Supabase's **Session pooler** string (port 5432 — not the 6543 transaction pooler, which needs `asyncpg` prepared statements disabled) and skip `docker compose up -d postgres` entirely. `init_db()` runs the same Alembic migrations + enables `pgvector` automatically on first boot either way. See ARCHITECTURE.md's "Cloud database" note.

Or via Docker:
```bash
GEMINI_API_KEY=your-key JWT_SECRET=$(openssl rand -hex 32) docker-compose up
```

## Database migrations

Schema is Alembic-managed for both local Postgres and Supabase (`migrations/versions/`) — `platform/core/db.py::init_db()` runs `alembic upgrade head` on every boot when the dialect is `postgresql` (idempotent; a no-op once already current). SQLite (`tests/conftest.py::db_session`) never uses migrations — it calls `Base.metadata.create_all()` directly, the accepted pattern for an ephemeral per-test schema.

- **Changed a model in `data/schemas/__init__.py`?** Generate the migration against a fresh local Postgres (never against Supabase — it already has live data):
  ```bash
  docker compose down -v postgres && docker compose up -d postgres   # empty DB
  DATABASE_URL=postgresql+asyncpg://clinical_ai:clinical_ai_password@localhost:5433/clinical_ai_db \
    PYTHONPATH=.:platform .venv/bin/alembic revision --autogenerate -m "describe the change"
  ```
  Review the generated file — autogenerate doesn't detect everything (e.g. it won't add `CREATE EXTENSION` statements or always get custom types like `pgvector.sqlalchemy.Vector` right on the first pass; the baseline migration needed a manual import fixup, see `migrations/versions/dff332c99951_initial_schema.py` for the pattern).
- **`tests/test_alembic_migration.py`** is the drift guard: it fails if a model changed without a matching migration. Self-skips if no local Postgres is reachable at `localhost:5433` (never blocks CI).
- Supabase was **stamped**, not migrated, at the baseline revision (`alembic stamp head`) — its schema already matched the models exactly (it was created by the old `create_all` path before this migration system existed), so `stamp` just recorded "already current" without running any DDL against the 14 real patients already there. It has since been genuinely migrated forward through every later revision by `init_db()`'s normal `alembic upgrade head` on boot (currently at `742cbbb2465b`, confirmed 2026-08-20) — the "never run upgrade head without checking additive-first" caution above applied only to that one baseline gap, not to Supabase in general.

## Testing

- `PYTHONPATH=.:platform .venv/bin/pytest` — unit suite (auth roundtrip, citation guard, timeline fallback, risk engine); SQLite in-memory, no services required, **no GEMINI_API_KEY required** (the LLM layer degrades gracefully and the whole agent stack is exercised through a scripted fake — see `tests/conftest.py::FakeLLMClient`)
- `examples/tools_example.py` — exercises all MCP tools directly, no LLM needed (fast smoke test)
- `examples/agents_example.py` — full multi-agent consultation through Gemini (requires `GEMINI_API_KEY`, burns free-tier quota)
- API: register/login via `/api/auth/*`, then `curl -X POST http://127.0.0.1:8000/api/agents/consult -H "Authorization: Bearer $TOKEN" ...` (agent endpoints require auth)
- Frontend: `/login` → register/sign in, `/copilot` → streaming chat with live agent chips + Citation Guard panel, `/patients/[id]` → profile + "Add clinical note" (auto-timeline).

## Important Notes

- **No secrets in code.** API keys, DB passwords, etc. go in `.env` (never commit).
- **`GEMINI_API_KEY` unset degrades gracefully, doesn't crash.** `/health` reports the LLM as unreachable, agent endpoints return 503, timeline extraction falls back to a deterministic lexicon, and vision returns `status: "unavailable"` — see `GeminiClient.health()`.
- **Gemini can rate-limit (429) or block content via safety filters.** `GeminiClient` retries 429s with backoff up to `gemini_max_retries`; a SAFETY `finish_reason` surfaces as an explanatory answer rather than an empty one. Watch for both in logs if a consultation looks stuck or truncated.
- **Vendored code in references/ is read-only.** We don't edit MONAI/MedCAT source; we wrap their classes in our own agents/MCP servers.
- **Medical accuracy is non-negotiable.** Every agent prompt references clinical guidelines. All recommendations cite sources. The disclaimer is on every page.

## Architecture migration (in progress)

SEPHIROTH is being restructured from a clinical application into a
model-agnostic agentic runtime, using Spec-Driven Development and a strangler-fig
migration into `src/sephiroth/`. Before changing anything under `intelligence/`,
`data/`, or `src/sephiroth/`, read:

- `docs/00-migration-charter.md` — **the frozen external contracts** (SSE events,
  persistence shape, derived explanation), the shim rules, and the phase order.
  Breaking a §2 contract breaks the frontend.
- `docs/specs/SPEC-000-spec-process.md` — the spec template and lifecycle.
  Implementation starts only after a spec reaches `Approved`.
- `docs/project-state.yaml` — what is actually implemented versus planned.

The loop is: spec → failing tests → implementation → spec marked `Implemented`.

## References

- `ARCHITECTURE.md` — detailed system design
- `docs/04-development/setup.md` — how to extend each module
- `docs/04-development/testing.md` — test conventions and the gates that matter
- `CONTRIBUTING.md` — development guidelines
- Open-source projects: [MONAI](https://docs.monai.io/), [MedCAT](https://github.com/CogStack/MedCAT), [Gemini API](https://ai.google.dev/gemini-api/docs)
