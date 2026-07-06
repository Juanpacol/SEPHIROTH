# SEPHIROTH — Project Context

## What This Is

A **local-first, AI-powered clinical decision support platform** for healthcare professionals. Patients upload histories, imaging, and lab data; specialized AI agents (powered by Ollama running locally) extract findings, retrieve evidence from medical literature, check drug interactions, and generate structured, cited recommendations. 

⚠️ **For research, education, and professional support only.** Not a medical device; all AI recommendations must be reviewed by a qualified healthcare professional before clinical use.

## Tech Stack

- **LLM**: 100% local Ollama (`qwen3:8b`), no cloud API dependency
- **Agents**: `OllamaMCPAgent` subclasses orchestrated via LangGraph, each with MCP tools
- **Tools (MCP servers)**: Clinical NLP, medical imaging analysis, evidence retrieval, drug safety checks — all in `intelligence/mcp/`
- **Backend**: FastAPI + PostgreSQL + pgvector + Redis
- **Frontend**: Next.js 14 (TypeScript, Tailwind, Radix) — design system from Nexura Care (healthcare dashboard), adapted for AI copilot domain
- **Container**: Docker Compose (Postgres + Redis + API); Ollama runs natively on host (Metal GPU passthrough)

## Folders at a Glance

| Folder | Purpose |
|---|---|
| `platform/api/` | FastAPI routes (routers in `routers/`, main.py with CORS/lifespan) |
| `platform/core/` | Config (`config.py`) + async DB engine/sessions/seed (`db.py`) |
| `platform/auth/` | JWT auth: `security.py` (bcrypt+pyjwt), `deps.py` (`get_current_user`), `router.py` (register/login/me) |
| `platform/frontend/` | Next.js app (pages in `app/`, components in `components/`, design tokens in Tailwind config) |
| `intelligence/llm/` | Ollama client wrapper, chat/tool-call loop |
| `intelligence/mcp/` | FastMCP servers (registry.py + nlp, imaging, rag, drug_safety, and vision servers — vision uses the multimodal `ollama_vision_model`, default llava:7b) |
| `intelligence/agents/` | Agent base class + 5 specialists + LangGraph workflow (`workflow.py`, blocking + SSE streaming) + Citation Guard (`citation_guard.py`) + explainability trace (`explainability.py`) + rule-based risk engine (`risk_engine.py`) |
| `intelligence/medical-imaging/` | MONAI transforms + networks (cloned from ref-monai-medical-imaging) |
| `intelligence/nlp/` | MedCAT NER + pipeline (cloned) + `timeline_extractor.py` (note → timeline events via structured LLM output) |
| `data/rag/` | Evidence retrieval with mandatory citations (seeded guideline corpus + PubMed) |
| `data/schemas/` | SQLAlchemy 2.0 models (User, Patient, TimelineEvent, ClinicalNote, Consultation) |
| `tests/` | pytest suite (auth, citation guard, timeline fallback) — SQLite in-memory, no services needed |
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
ClinicalCoordinator agent (OllamaMCPAgent subclass)
    ↓
Ollama qwen3:8b (tool-calling loop in intelligence/llm/ollama_client.py)
    ↓
├─ RadiologyAgent + imaging_server → MONAI inference
├─ LabAgent + patient data → lab result interpretation
├─ EvidenceAgent + rag_server → PubMed/guidelines search + citations
├─ DrugSafetyAgent + drug_safety_server → interaction checking
└─ Final answer aggregated, returned with source citations
    ↓
Frontend displays agent badges (Sephiroth gradient), cites sources
```

Each agent is an `OllamaMCPAgent` subclass with:
- A **system prompt** (clinical reasoning instructions)
- A list of **allowed MCP tools** (what it can call)
- A `.run(query, context)` method (calls `ollama_client.chat(...)`)

MCP tools are FastMCP servers in `intelligence/mcp/`:
- `nlp_server.py` → wraps `intelligence/nlp.ClinicalEntityExtractor` (disease/med/procedure extraction)
- `imaging_server.py` → wraps `intelligence.medical_imaging.MedicalImageAnalyzer` (segmentation, classification)
- `rag_server.py` → wraps `data.rag.RAGPipeline` (evidence search with citations)
- `drug_safety_server.py` → drug interaction checking

Registry (`intelligence/mcp/registry.py`) discovers all servers, aggregates their tool schemas into:
1. **Ollama format** (structured function-calling contract, passed to `/api/chat`)
2. **System prompt summary** (human-readable tool descriptions, prepended to agent's system prompt)

## Key Design Decisions

1. **No Claude/OpenAI API calls.** Ollama model runs locally on the user's M5 Mac. All reasoning, tool-calling, RAG stays on-device.
2. **Ollama on host, not in container.** Metal GPU passthrough requires native runtime. Backend talks to it via `OLLAMA_HOST=http://host.docker.internal:11434`.
3. **One agent per MCP server.** Specialist agents are small and focused; LangGraph orchestrates them.
4. **Sephiroth gradient = AI signal.** Whenever the UI shows AI-generated content, that gradient appears (badge, card border, etc.). Helps users trust the source.
5. **All answers must cite sources.** EvidenceAgent always returns `(finding, [source_citation1, source_citation2, ...])`. This is baked into the RAG pipeline.
6. **Citation Guard on every answer.** `intelligence/agents/citation_guard.py` audits the coordinator's final answer against actual tool output; fabricated citations are stripped (`[unverified — removed]`) and reported in `citation_report` (shown in the UI).
7. **Auth = JWT, single clinician role.** Consultations are persisted per user (`consultations` table); patients are shared. Protected routes use `Depends(get_current_user)`.
8. **Streaming via SSE.** `POST /api/agents/consult/stream` emits `routing` → `agent_completed`(×N) → `final` → `persisted` (carries the consultation id so Export PDF works without a reload); the frontend parses it with fetch+ReadableStream (EventSource can't POST).
9. **Explainability is derived, never stored.** `intelligence/agents/explainability.py` builds the reasoning trace on read from persisted `agents`/`tool_calls`/`citation_report` — template-based, no LLM call, so improving templates needs no backfill.
10. **Risk flags are computed at read-time.** `intelligence/agents/risk_engine.py` (curated lab rules + the drug-safety interaction table via `find_interactions`) runs inside `_summary()`/`_full()` in `patients.py` — no new columns, no background jobs.
11. **Vision = one MCP tool.** `describe_medical_image` (vision_server.py) does one-shot `generate()` against `ollama_vision_model` (llava:7b); the RadiologyAgent is prompted to call it first when `image_path` is in context. It reads rendered images (PNG/JPG…), not raw DICOM.
12. **Image preview shares the imaging trust boundary.** `GET /api/medical/imaging/preview` (medical.py) streams back the same local file `describe_medical_image`/`analyze_medical_image` already read — same single-user, local-first trust model — but is hard-restricted to browser-renderable extensions (png/jpg/jpeg/gif/webp/bmp) so it can't become a general file-download route. Powers the side-by-side viewer on `/imaging`.

## How to Extend

### Add a New Agent

1. Create a subclass of `OllamaMCPAgent` in `intelligence/agents/__init__.py`
2. Write a system prompt (clinical reasoning for that domain)
3. List its allowed MCP tools
4. Wire it into the LangGraph workflow in `intelligence/agents/workflow.py`

Example (see `docs/INTEGRATION_GUIDE.md` for more):
```python
class PathologyAgent(OllamaMCPAgent):
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
OLLAMA_HOST=127.0.0.1:11435 ollama pull qwen3:8b       # on the host, not Docker (port: see gotchas)
OLLAMA_HOST=127.0.0.1:11435 ollama pull llava:7b       # vision model for describe_medical_image
```

### Start everything
```bash
# Terminal 1: native Ollama (Metal GPU)
OLLAMA_HOST=127.0.0.1:11435 ollama serve

# Terminal 2: Postgres
docker compose up -d postgres

# Terminal 3: Backend (creates tables + seeds P001/P002 on first boot)
PYTHONPATH=.:platform .venv/bin/uvicorn api.main:app --reload --port 8000

# Terminal 4: Frontend (proxies /api/* to the backend)
cd platform/frontend && npm run dev -- --port 3100
```

**Port gotchas on this machine** (another project's Docker stack squats the default ports):
- `*:8000`, `*:3000`, `*:5432`, and `*:11434` are all taken by other containers.
- Backend: always test via `http://127.0.0.1:8000` (IPv4). Frontend: port **3100**.
- Our Postgres maps to host **5433**; native Ollama runs on **11435** (set in `.env`, which overrides `core/config.py` defaults).
- If inference is mysteriously slow, check you're NOT talking to a containerized Ollama on 11434 — Docker on macOS has no Metal GPU, so it runs models on CPU (~3× slower).

Or via Docker (Ollama still runs natively on the host):
```bash
docker-compose up
```

## Testing

- `PYTHONPATH=.:platform .venv/bin/pytest` — unit suite (auth roundtrip, citation guard, timeline fallback, risk engine); SQLite in-memory, no services required
- `examples/tools_example.py` — exercises all MCP tools directly, no LLM needed (fast smoke test)
- `examples/agents_example.py` — full multi-agent consultation through qwen3:8b
- API: register/login via `/api/auth/*`, then `curl -X POST http://127.0.0.1:8000/api/agents/consult -H "Authorization: Bearer $TOKEN" ...` (agent endpoints require auth)
- Frontend: `/login` → register/sign in, `/copilot` → streaming chat with live agent chips + Citation Guard panel, `/patients/[id]` → profile + "Add clinical note" (auto-timeline).

## Important Notes

- **No secrets in code.** API keys, DB passwords, etc. go in `.env` (never commit).
- **Ollama model must be pulled on the host first** (`ollama pull qwen3:8b`); the container environment variable just tells the API where to find it.
- **Vendored code in references/ is read-only.** We don't edit MONAI/MedCAT source; we wrap their classes in our own agents/MCP servers.
- **Medical accuracy is non-negotiable.** Every agent prompt references clinical guidelines. All recommendations cite sources. The disclaimer is on every page.

## References

- `ARCHITECTURE.md` — detailed system design
- `docs/INTEGRATION_GUIDE.md` — how to extend each module
- `CONTRIBUTING.md` — development guidelines
- Open-source projects: [MONAI](https://docs.monai.io/), [MedCAT](https://github.com/CogStack/MedCAT), [LangGraph](https://langchain-ai.github.io/langgraph/), [LlamaIndex](https://docs.llamaindex.ai/)
