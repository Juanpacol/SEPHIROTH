# SEPHIROTH — Project Context

## What This Is

An **AI-powered clinical decision support platform** for healthcare professionals. Patients upload histories, imaging, and lab data; specialized AI agents (powered by the Google Gemini API) extract findings, retrieve evidence from medical literature, check drug interactions, and generate structured, cited recommendations.

⚠️ **For research, education, and professional support only.** Not a medical device; all AI recommendations must be reviewed by a qualified healthcare professional before clinical use.

⚠️ **Privacy:** clinical text and medical images are sent to the Google Gemini API (AI Studio free tier). This is not HIPAA/GDPR-compliant as-is, and the free tier may use submitted data to improve Google's models. Use only with synthetic/de-identified data unless you migrate to Vertex AI with a BAA.

## Tech Stack

- **LLM**: Google Gemini API (`gemini-2.5-flash`), free AI Studio tier — no local model to run
- **Agents**: `MCPAgent` subclasses orchestrated via LangGraph, each with MCP tools
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
| `intelligence/llm/` | `GeminiClient` (chat/tool-call loop, structured output, vision) + `factory.py` (`get_llm_client()` singleton) |
| `intelligence/mcp/` | FastMCP servers (registry.py + nlp, imaging, rag, drug_safety, and vision servers — vision shares the same Gemini client, model override via `gemini_vision_model`) |
| `intelligence/agents/` | Agent base class + 5 specialists + LangGraph workflow (`workflow.py`, blocking + SSE streaming) + Citation Guard (`citation_guard.py`) + explainability trace (`explainability.py`) + rule-based risk engine (`risk_engine.py`) |
| `intelligence/medical-imaging/` | MONAI transforms + networks (cloned from ref-monai-medical-imaging) |
| `intelligence/nlp/` | MedCAT NER + pipeline (cloned) + `timeline_extractor.py` (note → timeline events via structured LLM output) |
| `data/rag/` | Evidence retrieval with mandatory citations (seeded guideline corpus + PubMed) |
| `data/schemas/` | SQLAlchemy 2.0 models (User, Patient, TimelineEvent, ClinicalNote, Consultation) |
| `tests/` | pytest suite (auth, citation guard, timeline fallback) — SQLite in-memory, no services needed, no API key needed |
| `data/embeddings/` | Vector embedding utilities |
| `data/vectors/` | pgvector operations |
| `references/` | Cloned open-source projects (don't edit; reference only) |

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
ClinicalCoordinator agent (MCPAgent subclass)
    ↓
Gemini (tool-calling loop in intelligence/llm/gemini_client.py)
    ↓
├─ RadiologyAgent + imaging_server → MONAI inference + vision description
├─ LabAgent + patient data → lab result interpretation
├─ EvidenceAgent + rag_server → PubMed/guidelines search + citations
├─ DrugSafetyAgent + drug_safety_server → interaction checking
└─ Final answer aggregated, returned with source citations
    ↓
Frontend displays agent badges (Sephiroth gradient), cites sources
```

Each agent is an `MCPAgent` subclass with:
- A **system prompt** (clinical reasoning instructions)
- A list of **allowed MCP tools** (what it can call)
- A `.run(query, context)` method (calls `client.chat(...)`)

MCP tools are FastMCP servers in `intelligence/mcp/`:
- `nlp_server.py` → wraps `intelligence/nlp.ClinicalEntityExtractor` (disease/med/procedure extraction)
- `imaging_server.py` → wraps `intelligence.medical_imaging.MedicalImageAnalyzer` (segmentation, classification)
- `rag_server.py` → wraps `data.rag.RAGPipeline` (evidence search with citations)
- `drug_safety_server.py` → drug interaction checking
- `vision_server.py` → wraps `GeminiClient.describe_image()` (multimodal image description)

Registry (`intelligence/mcp/registry.py`) discovers all servers, aggregates their tool schemas into:
1. **`llm_tools()`** — OpenAI-style function-calling schemas, converted to Gemini's `FunctionDeclaration` format inside `GeminiClient`
2. **System prompt summary** (human-readable tool descriptions, prepended to agent's system prompt)

## Key Design Decisions

1. **Cloud LLM via Gemini, not local Ollama.** Migrated from a fully local Ollama setup to the free Google Gemini API — the only free tier covering native multi-round tool-calling, JSON-Schema structured output, and vision in one provider. PHI now leaves the machine; see the privacy notice above.
2. **One shared `GeminiClient`, no host/Docker split.** `intelligence/llm/factory.py::get_llm_client()` is a lazy singleton used by agents, timeline extraction, and vision alike — one API key, one rate limiter, one retry/backoff path.
3. **One agent per MCP server.** Specialist agents are small and focused; LangGraph orchestrates them.
4. **Sephiroth gradient = AI signal.** Whenever the UI shows AI-generated content, that gradient appears (badge, card border, etc.). Helps users trust the source.
5. **All answers must cite sources.** EvidenceAgent always returns `(finding, [source_citation1, source_citation2, ...])`. This is baked into the RAG pipeline.
6. **Citation Guard on every answer.** `intelligence/agents/citation_guard.py` audits the coordinator's final answer against actual tool output; fabricated citations are stripped (`[unverified — removed]`) and reported in `citation_report` (shown in the UI).
7. **Auth = JWT, single clinician role.** Consultations are persisted per user (`consultations` table); patients are shared. Protected routes use `Depends(get_current_user)`. `JWT_SECRET` must be a strong, non-default value in staging/production — `Settings` fails fast at startup otherwise (see `platform/core/config.py`).
8. **Streaming via SSE.** `POST /api/agents/consult/stream` emits `routing` → `agent_completed`(×N) → `final` → `persisted` (carries the consultation id so Export PDF works without a reload); the frontend parses it with fetch+ReadableStream (EventSource can't POST).
9. **Explainability is derived, never stored.** `intelligence/agents/explainability.py` builds the reasoning trace on read from persisted `agents`/`tool_calls`/`citation_report` — template-based, no LLM call, so improving templates needs no backfill.
10. **Risk flags are computed at read-time.** `intelligence/agents/risk_engine.py` (curated lab rules + the drug-safety interaction table via `find_interactions`) runs inside `_summary()`/`_full()` in `patients.py` — no new columns, no background jobs.
11. **Vision = one MCP tool, same client.** `describe_medical_image` (vision_server.py) does one-shot `GeminiClient.describe_image()`; the RadiologyAgent is prompted to call it first when `image_path` is in context. It reads rendered images (PNG/JPG…), not raw DICOM. Degrades gracefully (`status: "unavailable"`) if the API key is missing or the request fails.
12. **Image preview shares the imaging trust boundary.** `GET /api/medical/imaging/preview` (medical.py) streams back the same local file `describe_medical_image`/`analyze_medical_image` already read, hard-restricted to browser-renderable extensions (png/jpg/jpeg/gif/webp/bmp) so it can't become a general file-download route. Powers the side-by-side viewer on `/imaging`.
13. **Free-tier quota is a real constraint.** `llm_max_tool_rounds` (default 6) and a shared per-client rate limiter (`gemini_rpm_limit`) keep a single consultation (5 agents, each doing several tool-call rounds) inside the AI Studio free tier. See README's Gemini quota section before raising these.

## How to Extend

### Add a New Agent

1. Create a subclass of `MCPAgent` in `intelligence/agents/__init__.py`
2. Write a system prompt (clinical reasoning for that domain)
3. List its allowed MCP tools
4. Wire it into the LangGraph workflow in `intelligence/agents/workflow.py`

Example (see `docs/INTEGRATION_GUIDE.md` for more):
```python
class PathologyAgent(MCPAgent):
    system_prompt = "You are a pathology specialist..."
    allowed_tools = ["pathology_analyzer", "specimen_database"]
```

### Add a New MCP Tool

1. Create `intelligence/mcp/my_new_server.py` with a FastMCP app
2. Declare tools with `@mcp.tool` decorators, calling your implementation from `intelligence/` or `data/`
3. `registry.py` auto-discovers it on startup

See existing servers (`nlp_server.py`, `imaging_server.py`) for the pattern.

### Add API Endpoints

1. Create router in `platform/api/routers/my_feature.py`
2. Import and include it in `platform/api/main.py`
3. Follow the pattern in `docs/INTEGRATION_GUIDE.md`

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

# Terminal 2: Backend (creates tables + seeds P001/P002 on first boot)
PYTHONPATH=.:platform .venv/bin/uvicorn api.main:app --reload --port 8000

# Terminal 3: Frontend (proxies /api/* to the backend)
cd platform/frontend && npm run dev -- --port 3100
```

**Port gotchas on this machine** (another project's Docker stack squats the default ports):
- `*:8000`, `*:3000`, and `*:5432` are all taken by other containers.
- Backend: always test via `http://127.0.0.1:8000` (IPv4). Frontend: port **3100**.
- Our Postgres maps to host **5433** (set in `.env`, which overrides `core/config.py` defaults).

Or via Docker:
```bash
GEMINI_API_KEY=your-key JWT_SECRET=$(openssl rand -hex 32) docker-compose up
```

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

## References

- `ARCHITECTURE.md` — detailed system design
- `docs/INTEGRATION_GUIDE.md` — how to extend each module
- `CONTRIBUTING.md` — development guidelines
- Open-source projects: [MONAI](https://docs.monai.io/), [MedCAT](https://github.com/CogStack/MedCAT), [LangGraph](https://langchain-ai.github.io/langgraph/), [Gemini API](https://ai.google.dev/gemini-api/docs)
