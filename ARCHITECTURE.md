# SEPHIROTH — Architecture

## Overview

Clinical decision-support platform. LLM reasoning runs on Google Gemini API (AI Studio free tier); clinical capabilities are FastMCP tool servers; specialist agents run through a purpose-built async executor (`src/sephiroth/runtime/`, replaced LangGraph — [ADR-001](docs/08-decisions/ADR-001-remove-langgraph.md)); answers ground in tool output + citations.

**Privacy:** clinical text/images go to Google's Gemini API. Not HIPAA/GDPR-compliant as-is — see README privacy notice before using real patient data.

## Directory Structure

```
clinical-ai-copilot/
├── platform/                  # Backend + frontend (NOT a Python package — see note below)
│   ├── api/                   # FastAPI app: main.py + routers/ + workflows/ (engine) + services/,
│   │                          #   plus top-level helpers: fast_path.py (0-LLM lookup), scheduling.py,
│   │                          #   audit.py, pdf_export.py, timeparse.py
│   ├── core/                  # Settings, crypto.py (PHI encryption), storage.py (attachments)
│   ├── auth/                  # JWT auth, TOTP MFA, password reset, login lockout
│   └── frontend/              # Next.js 14 app (Nexura-derived design system)
│
├── src/sephiroth/              # Model-agnostic runtime (strangler-fig target — see CLAUDE.md migration note)
│   ├── models/                #   GeminiClient, GroqClient, FallbackLLMClient, factory.get_llm_client()
│   ├── tools/                 #   ToolRuntime — MCP registry, capability tags, dispatch whitelist
│   ├── runtime/                #   Agent, capability records, async executor (fan-out/merge/coordinate)
│   ├── verification/          #   claim extraction + 5-state verification, citation_guard
│   ├── safety/                #   abstention gating (answer/partial/abstain), prompt-injection heuristic
│   ├── context/               #   per-agent context views, MMR rerank, per-patient memory
│   ├── telemetry/             #   build_trace, traced_span → persisted ExecutionTrace
│   ├── clinical/              #   deterministic clinical helpers: vitals, results, templates, guideline_intent
│   ├── contracts/             #   shared typed schemas (claims, evidence, state, trace, ...) — leaf package
│   └── workflows/              #   shared event/policy types for the durable automation engine
│                               #   (engine itself lives in platform/api/workflows/)
│
├── intelligence/
│   ├── mcp/                   # FastMCP servers (nlp, imaging, rag, drug_safety, vision, patient_comms)
│   ├── agents/                # 3 thin Agent subclasses over the runtime registry
│   ├── nlp/                   # timeline_extractor.py — note → timeline events
│   └── evaluation/            # RAG eval harness — Recall@k, MRR, Citation Precision, Faithfulness
│
├── data/
│   ├── rag/                   # Retrieval pipeline, queries pgvector directly — no in-memory fallback
│   ├── schemas/                # SQLAlchemy models (Patient, ClinicalNote, ...)
│   └── embeddings/             # Gemini/Ollama embedding providers
│
├── migrations/                 # Alembic schema migrations (Postgres + Supabase)
├── scripts/                    # Maintenance/CI scripts (commit-msg validation, PHI backfill, docs check, ...)
├── docs/                       # Migration charter, specs, ADRs, project-state.yaml
└── references/                 # Cloned upstream repos (read-only)
```

> **Python note:** `platform/` cannot be a package — the name would shadow the stdlib
> `platform` module. It's added to `PYTHONPATH`; children import as top-level packages
> (`from core.config import settings`, `uvicorn api.main:app`).

## LLM Layer

- **Runtime:** Google Gemini API (AI Studio free tier) — no local model, no GPU, just an API key.
- **Model:** `gemini-flash-latest` (alias for current recommended flash model — native tool calling, JSON-Schema structured output, vision), configurable via `GEMINI_MODEL`.
- **Thinking mode off** (`thinking_budget=0`) — saves latency and free-tier quota; agents rely on tools, not hidden reasoning.
- `GeminiClient.chat()` (`src/sephiroth/models/gemini.py`) loops: send request → execute any `functionCall`s via `ToolRuntime` → append `functionResponse` parts → repeat until plain answer (max `llm_max_tool_rounds`, default 6).
- Shared token-bucket rate limiter (`gemini_rpm_limit`) + 429 retry/backoff. Optional Groq fallback (`GROQ_API_KEY`) via `FallbackLLMClient` when Gemini errors out — text/tool-calling only by default; vision fallback opt-in (`GROQ_VISION_MODEL`).

## MCP Tool Layer

Each clinical capability is a **FastMCP server** (`intelligence/mcp/*_server.py`). `ToolRuntime` (`src/sephiroth/tools/runtime.py`) discovers all servers (`SERVERS` in `src/sephiroth/tools/servers.py`) and exposes them two ways:

1. **Structured:** `llm_tools()` — OpenAI-style function schemas, converted to Gemini's `FunctionDeclaration` format.
2. **Prompted:** natural-language tool catalog appended to each agent's system prompt.

Execution is in-process via FastMCP's in-memory client — no subprocesses/sockets. Heavy deps (MedCAT, MONAI/torch) import lazily and degrade gracefully: NLP falls back to a deterministic lexicon; imaging returns `model_not_configured` until weights are set.

## Agent & Execution Layer

A consultation takes the cheapest matching path first:

1. **`platform/api/fast_path.py`** — pure lookup (guideline search, drug interaction)? Tool result returned verbatim with its own citation. 0 LLM calls, ~4s.
2. **`src/sephiroth/runtime/executor.py`** — otherwise: `intent_router` picks exactly one specialist (`ADR-016`); its answer is final. 1 LLM call.
3. Citation guard (deterministic) → claim verification (1 LLM call) → abstention gate (deterministic) → trace.

| Agent | Tools | Runs when |
|---|---|---|
| EvidenceAgent | search_clinical_guidelines, search_pubmed | Default / always eligible |
| RadiologyAgent | describe_medical_image, analyze_medical_image | `context.image_path` present |
| DrugSafetyAgent | check_drug_interactions | `context.medications` present |

Lab-value interpretation is covered by `src/sephiroth/safety/risk.py`'s deterministic rules (outside the chat path), with `EvidenceAgent` as the default fallback for anything `intent_router` can't confidently place.

Each agent is an `Agent` (`src/sephiroth/runtime/agent.py`) bound to an `AgentCapability` record: system prompt + allowed-tool whitelist + `.run(query, context)`.

## Verification, Safety & Telemetry

- **`src/sephiroth/verification/`** — decomposes the answer into claims, classifies each against retrieved evidence (5-state `VerificationStatus`); `citation_guard` pre-filters fabricated citations before this runs.
- **`src/sephiroth/safety/`** — abstention gate (`answer`/`partial`/`abstain`) on unsupported high-risk claims, contradictions, or low confidence; confidence is always derived, never self-reported.
- **`src/sephiroth/context/`** — scopes each agent to only its declared `context_fields`; per-patient consultation memory reaches only the answering agent.
- **`src/sephiroth/telemetry/`** — `build_trace` projects the executor's `RunState` into a persisted `ExecutionTrace` (real token/cost accounting); toggling it must not change a run's result.
- **`src/sephiroth/clinical/`** — deterministic, non-LLM clinical helpers (vitals, result formatting, templates, guideline intent) used by routers directly, outside the agent/verification path.

## Security Hardening

`ADR-012`-`ADR-014`: least-privilege DB role + row-level security for the app's Postgres connection (`migrations/roles.sql`); `slowapi` rate limiting, security headers, and login lockout; column-level PHI encryption at rest (Fernet, `core/crypto.py`). `audit.py` surfaces the resulting access log for clinician review.

## Automation & Workflow Layer

A durable, tick-based workflow engine, separate from the per-request consultation path above. `platform/api/workflows/engine.py` advances workflow state machines (`registry.py`/`definitions.py`) on each tick, driven by `internal.py`'s unauthenticated shared-secret endpoint (meant for a cron/scheduler, never a browser). Concrete workflows: `alert_escalation.py`, `appointment_reminder.py`, `patient_followup.py` (drafts via the `patient_comms` MCP tool). `channels.py`/`subscriptions.py` handle delivery; `memory.py` is the engine's own operational memory. User-facing routers: `alerts.py`, `approvals.py` (human approval gate before an automated action fires), `followups.py`, `automation_memory.py` (observability dashboard), `notifications.py`, `encounters.py`, `result_reviews.py`.

## API Layer

FastAPI routers under `platform/api/routers/`:

- `POST /api/agents/consult(/stream)` — full consultation (fast path → executor → SSE)
- `POST /api/agents/ask` — single specialist directly
- `GET /api/patients`, `/{id}`, `/{id}/timeline` — patient data, Postgres-backed
- `POST /api/medical/nlp/extract`, `/imaging/analyze`, `/drugs/check` — direct tool access
- `GET /api/rag/search`, `/api/rag/pubmed` — evidence lookup
- `GET /api/dashboard/bootstrap` — combined first-paint payload (`stats` + today's agenda + `action_items`)
- `GET /api/dashboard/action-items` — cross-patient triage list; each item carries `rule_code`/`factors`
  (why it fired), a recent trend, and recurrence (new vs. long-active) — `SPEC-031`
- `GET /api/dashboard/rule-summary` — patients per active clinical problem, exact counts over every
  patient, feeding the "what dominates today" chart (`SPEC-031` 1.1.0)
- `scheduling.py`, `results.py` — appointment booking, exam-result sharing (role-scoped per route)
- `alerts.py`, `approvals.py`, `followups.py`, `automation_memory.py`, `notifications.py`,
  `encounters.py`, `result_reviews.py` — automation/workflow surfaces, see above
- `audit.py` (clinician-only) — PHI access log review
- `internal.py` — unauthenticated workflow-tick entrypoint, shared-secret header, not browser-facing
- Auth: JWT, roles `clinician`/`patient`, no patient self-registration (claim-code redemption only),
  TOTP MFA + password reset + login lockout

## Frontend

Next.js 14 (App Router) + TypeScript + Tailwind + TanStack Query. Dev server proxies `/api/*` to FastAPI. Design tokens in `platform/frontend/tailwind.config.ts`:

- Nexura-derived palette: primary `#3683F8`, ink `#060606`, surface `#EBF3FE`, border `#D8D8D8`, font Manrope
- **Sephiroth gradient** (`#8C92AC → #D1D5DB`): exclusively marks AI-generated content
- Dashboard charts (`components/dashboard/`) are hand-rolled SVG/CSS on these same tokens, not a
  charting library (`ADR-019`)

Pages: `/` (marketing, chromeless), `/dashboard`, `/copilot` (chat + agent badges + citation guard
panel), `/patients`, `/patients/[id]` (timeline), `/imaging`, `/evidence`, `/schedule`, `/alerts`,
`/approvals`, `/results`, `/encounters/[id]`, `/portal` (patient view).

## Deployment

`docker-compose up` starts Postgres (pgvector) + API. API talks to Gemini over the internet — no host GPU or local model server. `JWT_SECRET` and `GEMINI_API_KEY` required (compose fails fast if `JWT_SECRET` unset).

**Cloud database (optional):** `DATABASE_URL` can point to managed Postgres (e.g. Supabase, native pgvector). `platform/core/db.py::init_db()` runs `alembic upgrade head` + enables `pgvector` on every boot when dialect is `postgresql`. Use Supabase's **Session pooler** (port 5432), not the Transaction pooler (6543 — disables prepared statements asyncpg needs). Local `docker-compose` Postgres remains the dev default.

## Migration State

Project is mid-migration from a clinical app into a model-agnostic agentic runtime (strangler-fig into `src/sephiroth/`). Implemented-vs-planned status: `docs/project-state.yaml`. Frozen external contracts (SSE events, persistence shape): `docs/00-migration-charter.md`. Formal decisions: `docs/08-decisions/`.
