# SEPHIROTH — Project Context

## What This Is

An **AI-powered clinical decision support platform** for healthcare professionals. Patients upload histories, imaging, and lab data; specialized AI agents (powered by the Google Gemini API) extract findings, retrieve evidence from medical literature, check drug interactions, and generate structured, cited recommendations.

**For research, education, and professional support only.** Not a medical device; all AI recommendations must be reviewed by a qualified healthcare professional before clinical use.

**Privacy:** clinical text and medical images are sent to the Google Gemini API (AI Studio free tier). This is not HIPAA/GDPR-compliant as-is, and the free tier may use submitted data to improve Google's models. Use only with synthetic/de-identified data unless you migrate to Vertex AI with a BAA.

## Tech Stack

- **LLM**: Google Gemini API (`gemini-flash-latest`, a Google-maintained alias for the current recommended flash model), free AI Studio tier — no local model to run. Optional Groq fallback for text/tool-calling when Gemini's quota is exhausted (`GROQ_API_KEY`).
- **Agents**: `Agent` instances (bound to a capability record, `src/sephiroth/runtime/`) orchestrated by a purpose-built async executor, each with MCP tools
- **Tools (MCP servers)**: Clinical NLP, medical imaging analysis, evidence retrieval, drug safety checks — all in `intelligence/mcp/`
- **Backend**: FastAPI + PostgreSQL + pgvector
- **Security**: TOTP MFA (`pyotp`), rate limiting + security headers + login lockout (`slowapi`, `ADR-013`), column-level PHI encryption (`cryptography`/Fernet, `core/crypto.py`, `ADR-014`), least-privilege DB role + RLS (`ADR-012`)
- **Frontend**: Next.js 14 (TypeScript, Tailwind CSS, TanStack Query for server state) — design system from Nexura Care (healthcare dashboard), adapted for the clinical AI copilot domain. Dashboard charts are hand-rolled SVG/CSS, not a charting library (`ADR-019`)
- **Container**: Docker Compose (Postgres + API); optional `boto3` for S3-compatible attachment storage (`platform/core/storage.py`)

## Folders at a Glance

| Folder | Purpose |
|---|---|
| `platform/api/` | FastAPI app: `main.py` (CORS/lifespan), routers in `routers/`, plus top-level helpers used by them — `fast_path.py` (0-LLM lookup tier), `scheduling.py` (`expand_slots`), `audit.py` (PHI access logging), `pdf_export.py`, `timeparse.py`, `services/` (encounter drafting/result services), `workflows/` (automation engine, see below) |
| `platform/core/` | Config (`config.py`) + async DB engine/sessions/seed (`db.py`) |
| `platform/auth/` | JWT auth: `security.py` (bcrypt+pyjwt), `deps.py` (`get_current_user`), `router.py` (register/login/me) |
| `platform/frontend/` | Next.js app: pages in `app/` (copilot chat, dashboard, patients, scheduling, alerts, approvals, results, patient portal, marketing site), reusable components in `components/`, design tokens in `tailwind.config.ts`. `components/dashboard/` holds the hand-rolled SVG dashboard visuals — risk distribution bar, value-vs-threshold range bar, trend line, "what dominates today" chart (`SPEC-031`, `ADR-019`) |
| `src/sephiroth/models/` | `GeminiClient` (chat/tool-call loop, structured output, vision) + `GroqClient` (text-only fallback) + `FallbackLLMClient` (composes both) + `factory.py` (`get_llm_client()` singleton), all behind the `ModelProvider` protocol |
| `src/sephiroth/tools/` | `ToolRuntime` (relocated MCP registry — capability tags, per-call timeout, dispatch-time whitelist enforcement) |
| `src/sephiroth/runtime/` | `Agent` + capability records + `intent_router` + the async executor (route → run one specialist → verify → decide, `ADR-016`) |
| `src/sephiroth/verification/` | Claim extraction, evidence harvesting, 5-state claim verification (`VerificationStatus`), deterministic confidence scoring — `citation_guard` feeds it as a pre-filter |
| `src/sephiroth/safety/` | Abstention gating (`answer`/`partial`/`abstain`, ADR-008) + a minimal input prompt-injection heuristic |
| `src/sephiroth/context/` | Per-agent context views, lexical MMR reranking, per-patient consultation memory, character-budget truncation (ADR-011) |
| `src/sephiroth/telemetry/` | `build_trace` projects `RunState` into the persisted `ExecutionTrace`; `traced_span` records real spans for the executor/verifier seams (ADR-009) |
| `src/sephiroth/clinical/` | Deterministic clinical helpers outside the agent/LLM path: `vitals.py`, `results.py`, `templates.py`, `guideline_intent.py` |
| `src/sephiroth/contracts/` | Shared typed schemas used across the runtime: `capability.py`, `claims.py`, `context.py`, `enums.py`, `evidence.py`, `plan.py`, `results.py`, `safety.py`, `state.py`, `task.py`, `trace.py` — a leaf package, no imports back into `runtime`/`verification`/etc. |
| `src/sephiroth/workflows/` | `events.py` + `policy.py` — the shared event/policy types for the durable workflow engine (Phase 7-14, `SPEC-009`-`SPEC-016`); the engine implementation itself lives in `platform/api/workflows/` |
| `platform/api/workflows/` | Durable tick-based automation engine: `engine.py` + `handlers.py` + `registry.py`/`definitions.py` + `instantiate.py`, plus concrete workflows (`alert_escalation.py`, `appointment_reminder.py`, `patient_followup.py`) and `channels.py`/`subscriptions.py`/`memory.py` for delivery and operational memory. Driven by the unauthenticated `internal.py` router (shared-secret header) |
| `intelligence/mcp/` | FastMCP servers: nlp, imaging, rag, drug_safety, vision, patient_comms (drafts follow-up messages, not a chat-agent tool). Registry/dispatcher lives in `src/sephiroth/tools/` |
| `intelligence/agents/` | Three thin `Agent` subclasses (`RadiologyAgent`, `DrugSafetyAgent`, `EvidenceAgent`) wrapping the shared client, so `routers/agents.py`'s `/ask` route can instantiate them by name |
| `intelligence/nlp/` | `timeline_extractor.py` — note → timeline events via structured LLM output |
| `data/rag/` | Evidence retrieval with mandatory citations, stored in pgvector (`guideline_documents`, `ADR-017`) — async, no in-memory fallback. `seed_pgvector.py` populates it |
| `data/schemas/` | SQLAlchemy 2.0 models (User, Patient, TimelineEvent, ClinicalNote, Consultation) |
| `tests/` | pytest suite (auth, citation guard, timeline fallback) — SQLite in-memory, no API key needed; RAG-touching tests need local Postgres (self-skip without it) |
| `data/embeddings/` | Gemini/Ollama embedding providers (live + cached-artifact) — query-side embedding only since Phase 15; document-side embeddings are computed once at seed time |
| `references/` | Cloned open-source projects (don't edit; reference only) |
| `real_data/` | Optional real/synthetic sample data (Synthea patients+notes, DDInter drug interactions, RSNA imaging fixtures) — see `real_data/README.md`; never required for tests/CI |
| `migrations/` | Alembic schema migrations for Postgres (local docker-compose + Supabase). SQLite tests never touch this — see "Database migrations" below |
| `scripts/` | One-off/maintenance scripts: `validate_commit_msg.py` (commit hook + CI), `encrypt_existing_phi.py`, `backfill_result_reviews.py`, `docs_check.py`, `export_contracts.py`, `generate_changelog.py`, `simulate_daily.py` |

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

A consultation takes one of two paths, cheapest first:

```
User Query
    ↓
platform/api/fast_path.py — pure lookup? (guideline search, drug interaction)
    ├─ YES → tool result returned verbatim with its own citation.  0 LLM calls, ~4s
    └─ NO ↓
src/sephiroth/runtime/executor.py
    ↓
intent_router picks ONE specialist → it answers directly.  1 LLM call
    ↓
citation guard (deterministic) → claim verification (1 LLM call)
    → abstention gate (deterministic) → trace
    ↓
Frontend displays agent badges (Sephiroth gradient), cites sources
```

The three specialists:

- RadiologyAgent + imaging_server → MONAI inference + vision description
- EvidenceAgent + rag_server → PubMed/guidelines search + citations
- DrugSafetyAgent + drug_safety_server → interaction checking

`LabAgent`/`ClinicalCoordinator` and the multi-agent fan-out (`enable_single_agent_mode`/`enable_dynamic_planner`) were removed in Phase 14 (`SPEC-029`, `ADR-016`) — see decision #24.

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

Short version of each decision. Full rationale, if you need it, lives in `docs/08-decisions/` (ADRs) — linked where one exists.

### Agents, routing & recovery

- **Gemini over local Ollama.** Only free tier with tool-calling + structured output + vision in one provider. PHI leaves the machine — see the privacy notice above.
- **One shared `GeminiClient`.** `models.factory::get_llm_client()` is a lazy singleton — one API key, one rate limiter, one retry path for agents, timeline extraction, and vision alike.
- **One agent per MCP server.** Keeps each specialist small and focused.
- **One specialist answers, no coordinator turn** (`ADR-016`). `runtime/intent_router.py` routes every consultation to exactly one specialist, whose answer is final. Three tiers, cheapest first: keyword rules → context signals → one `generate_json` classification, defaulting to `evidence`.
- **A failing specialist doesn't abort the run** (`ADR-007`). `runtime/recovery.py` retries up to twice, then continues with that section left empty instead of raising.
- **Optional Groq fallback.** Set `GROQ_API_KEY` to fall back to Groq on Gemini errors for chat/tool-calling. Embeddings always stay on Gemini; vision fallback is opt-in via `GROQ_VISION_MODEL`.
- **Free-tier quota is a real constraint.** `llm_max_tool_rounds` (default 6) and `gemini_rpm_limit` keep a consultation inside the AI Studio free tier.

### Verification, citations & safety

- **Citation Guard on every answer.** `verification/citation_guard.py` strips fabricated citations before claim-level verification runs.
- **Claim extraction + verification in one model call.** `verification/combined.py::extract_and_verify`, toggled by `enable_combined_verification` (default True) — faster than the legacy two-call path, same guarantees.
- **Claim verification + abstention gate every consultation.** `verification/` classifies claims into a 5-state `VerificationStatus`; `safety/abstention.py` downgrades the answer to `partial` or `abstain` on an unsupported high-risk claim, a contradiction, or low confidence. Confidence is always derived, never self-reported by the model.
- **A perception tool's own output can ground a claim** (`ADR-018`). `VerificationStatus.OBSERVED` applies when a claim's only evidence is vision/imaging tool output, weighted lower than independently retrieved evidence.
- **Every answer must cite sources** — baked into the EvidenceAgent/RAG pipeline.
- **Each agent sees only the context fields it declares** (`ADR-011`). Per-patient consultation memory reaches only the agent writing the final answer.
- **Every consultation builds a persisted, replayable trace** (`ADR-009`), with real token/cost accounting, toggled by `enable_tracing`.
- **Explainability is derived on read, never stored.** `telemetry/explain.py` builds the reasoning trace from persisted data — template-based, no LLM call.
- **Risk flags are computed at read-time.** `safety/risk.py` drives both the patient profile and the dashboard (`ADR-019`) — deterministic rules only, never a fabricated confidence score.
- **Vision is one MCP tool.** `vision_server.py` does a one-shot image description; degrades gracefully if the API key is missing.
- **Image preview shares the same trust boundary as the imaging tools** — restricted to browser-safe file extensions.

### Auth, roles & security

- **Auth = JWT, two roles, MFA, lockout, reset.** Role is re-read from the DB on every request, never trusted from the token. Clinician-only routers enforce `require_clinician` at the router level. `platform/auth/router.py` also has TOTP MFA (`pyotp`), password reset, and lockout after 5 failed attempts.
- **Security hardening: DB role, rate limiting, PHI encryption** (`ADR-012`, `ADR-013`, `ADR-014`). Least-privilege Postgres role + row-level security, `slowapi` rate limiting, Fernet column encryption (`core/crypto.py`). `audit.py` exposes the resulting access log.
- **No patient self-registration — ever.** Patient accounts exist only by redeeming a clinician-issued, one-time claim code.
- **Frontend role gating is UX only, not the security boundary.** Every backend route enforces its own role check independently.

### Clinical workflow features

- **Scheduling + exam-result sharing** (`routers/scheduling.py`, `results.py`) — role-scoped per route, conflicts checked server-side, attachments capped at 10MB / 3 files per share.
- **Durable workflow engine drives alerts, reminders, and follow-up** — outside the chat path. `platform/api/workflows/` ticks forward alert escalation, appointment reminders, and patient follow-up as state machines, driven by the unauthenticated `internal.py` endpoint. User-facing surfaces: `alerts.py`, `approvals.py`, `followups.py`, `automation_memory.py`, `notifications.py`, `encounters.py`, `result_reviews.py`.
- **Streaming via SSE.** `/api/agents/consult/stream` emits `routing → agent_completed(×N) → final → persisted`.

### Frontend & branding

- **Sephiroth gradient = AI signal.** Shown wherever the UI displays AI-generated content.
- **Landing page + brand mark.** `/` is a chromeless marketing route; a logged-in visitor is redirected before first paint. The brand mark is original artwork and never uses the AI-signal gradient.

### Process

- **Commit messages must match `SF<NNN> <body, ≤50 words> [<type>]`.** Enforced by a `commit-msg` hook and a required CI job, both calling `scripts/validate_commit_msg.py`. See `CONTRIBUTING.md`.

## How to Extend

### Add a New Agent

1. Add an `AgentCapability` record to `src/sephiroth/runtime/registry.py` — `id`
   (hyphenated display name), `role_prompt` (clinical reasoning for that
   domain; the system prompt is assembled in `agent.py` from the disclaimer +
   `role_prompt` + tool catalog), and `tools` (allowed MCP tools)
2. Give `intent_router.py` a way to route to it (a keyword rule, a context
   signal, or rely on its LLM tier, which already enumerates `AGENTS`) —
   there is no separate planner since Phase 14 (`SPEC-029`)
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
- Supabase runs the same `alembic upgrade head` as local Postgres on every boot — no special-casing.

## Testing

- `PYTHONPATH=.:platform .venv/bin/pytest` — unit suite (auth roundtrip, citation guard, timeline fallback, risk engine); SQLite in-memory, **no GEMINI_API_KEY required** (the LLM layer degrades gracefully and the whole agent stack is exercised through a scripted fake — see `tests/conftest.py::FakeLLMClient`). One exception since Phase 15 (`SPEC-030`): RAG-touching tests query real pgvector (`docker compose up -d postgres`, then `python -m data.rag.seed_pgvector`) and self-skip without it — `tests/conftest.py::_redirect_rag_db_to_local_postgres` always points that traffic at the local docker-compose instance, never at whatever `DATABASE_URL` a developer's `.env` happens to hold.
- API: register/login via `/api/auth/*`, then `curl -X POST http://127.0.0.1:8000/api/agents/consult -H "Authorization: Bearer $TOKEN" ...` (agent endpoints require auth)
- Frontend: `/login` → register/sign in, `/copilot` → streaming chat with live agent chips + Citation Guard panel, `/patients/[id]` → profile + "Add clinical note" (auto-timeline).

## Important Notes

- **No secrets in code.** API keys, DB passwords, etc. go in `.env` (never commit).
- **`GEMINI_API_KEY` unset degrades gracefully, doesn't crash.** `/health` reports the LLM as unreachable, agent endpoints return 503, timeline extraction falls back to a deterministic lexicon, and vision returns `status: "unavailable"` — see `GeminiClient.health()`.
- **Gemini can rate-limit (429) or block content via safety filters.** `GeminiClient` retries 429s with backoff up to `gemini_max_retries`; a SAFETY `finish_reason` surfaces as an explanatory answer rather than an empty one. Watch for both in logs if a consultation looks stuck or truncated.
- **Vendored code in references/ is read-only.** We don't edit MONAI/MedCAT source; we wrap their classes in our own agents/MCP servers.
- **Medical accuracy is non-negotiable.** Every agent prompt references clinical guidelines. All recommendations cite sources. The disclaimer is on every page.

## Architecture migration (in progress)

SEPHIROTH was restructured from a clinical application into a model-agnostic
agentic runtime via a strangler-fig migration into `src/sephiroth/`, phases
0 through 16. The formal Spec-Driven Development process that governed those
phases (`docs/specs/SPEC-NNN-*.md`, spec → failing tests → implementation →
spec marked `Implemented`) was retired once the project moved to solo
development — see `CONTRIBUTING.md`. Before changing anything under
`intelligence/`, `data/`, or `src/sephiroth/`, read:

- `docs/00-migration-charter.md` — **the frozen external contracts** (SSE events,
  persistence shape, derived explanation), still enforced regardless of how a
  change gets planned. Breaking a §2 contract breaks the frontend.
- `docs/project-state.yaml` — what is actually implemented versus planned.

Current phase: 16 (`SPEC-031` — dashboard alert explainability — was the last spec written before the process was retired; `ADR-019` is the latest decision record). See `docs/project-state.yaml` for the authoritative phase-by-phase status.

## References

- `ARCHITECTURE.md` — detailed system design
- `docs/04-development/setup.md` — how to extend each module
- `docs/04-development/testing.md` — test conventions and the gates that matter
- `docs/00-project/requirements-catalog.md` — requirements catalog (Spanish)
- `CONTRIBUTING.md` — development guidelines
- Open-source projects: [MONAI](https://docs.monai.io/), [MedCAT](https://github.com/CogStack/MedCAT), [Gemini API](https://ai.google.dev/gemini-api/docs)
