# SEPHIROTH — Architecture

## Overview

A clinical decision-support platform whose LLM reasoning runs on the Google Gemini API (AI Studio free tier); clinical capabilities are packaged as MCP tool servers; specialist agents are orchestrated with LangGraph and always ground their answers in tool output and citations.

⚠️ **Privacy:** clinical text and images are sent to Google's Gemini API. Not HIPAA/GDPR-compliant as-is — see README's privacy notice before using real patient data.

## Directory Structure

```
clinical-ai-copilot/
├── platform/                 # Backend + frontend (NOT a Python package — see note below)
│   ├── api/                  # FastAPI app: main.py + routers/ (agents, patients, medical, rag, dashboard)
│   ├── core/                 # Settings (Gemini model/key, DB URLs, feature flags)
│   ├── auth/                 # JWT auth: register/login, bcrypt hashing, get_current_user dependency
│   └── frontend/             # Next.js 14 app (Nexura-derived design system)
│
├── intelligence/
│   ├── llm/                  # GeminiClient — chat + tool-call loop, structured output, vision
│   │   └── factory.py        #   get_llm_client() lazy singleton, shared by agents/timeline/vision
│   ├── mcp/                  # FastMCP servers + registry (the Gemini⇄MCP bridge)
│   │   ├── registry.py       #   discovers tools, emits function-calling schemas + prompt summaries
│   │   ├── nlp_server.py     #   entity extraction, note summarization
│   │   ├── imaging_server.py #   DICOM/NIfTI inspection, MONAI analysis
│   │   ├── rag_server.py     #   guideline search + PubMed (always cited)
│   │   ├── drug_safety_server.py  # interaction screening
│   │   └── vision_server.py  #   multimodal image description via GeminiClient.describe_image()
│   ├── agents/               # MCPAgent base + 5 agents + LangGraph workflow
│   ├── medical-imaging/      # MONAI reference code (transforms, networks)
│   ├── nlp/                  # MedCAT reference code (ner, pipeline, preprocessing)
│   └── evaluation/           # RAG eval harness — Recall@k, MRR, Citation Precision, Faithfulness (see README § Evaluation)
│
├── data/
│   ├── rag/                  # Retrieval pipeline + seeded guideline corpus
│   ├── schemas/              # SQLAlchemy models (Patient, ClinicalNote, ...)
│   ├── embeddings/, vectors/ # pgvector integration (planned)
│
├── examples/                 # tools_example.py (no LLM), agents_example.py (full workflow)
├── docs/                     # Integration guide
└── references/               # Cloned upstream repos (read-only)
```

> **Python note:** `platform/` cannot be a package — the name would shadow the stdlib
> `platform` module. It is added to `PYTHONPATH`, and its children are imported as
> top-level packages: `from core.config import settings`, `uvicorn api.main:app`.

## LLM Layer

- **Runtime:** Google Gemini API (AI Studio free tier) — no local model, no GPU, just an API key.
- **Model:** `gemini-flash-latest` — a Google-maintained alias for the current recommended flash model (native tool calling, JSON-Schema structured output, and multimodal vision), configurable via `GEMINI_MODEL`. Pinned version names (e.g. `gemini-2.5-flash`) get deprecated for new API keys over time; the alias avoids that churn.
- **Thinking mode is off** (`thinking_budget=0`) — it multiplies latency and burns free-tier quota; the agents rely on tools rather than long hidden reasoning.
- `GeminiClient.chat()` loops: send request → execute any `functionCall`s through the MCP registry → append the corresponding `functionResponse` parts → repeat until a plain answer (max `llm_max_tool_rounds`, default 6 — lower than a local model's slack because free-tier quota is finite).
- A shared token-bucket rate limiter (`gemini_rpm_limit`) and retry/backoff on 429s keep a full multi-agent consultation (5 agents, several tool-call rounds each) inside the free tier's requests-per-minute budget.

## MCP Tool Layer

Each clinical capability is a **FastMCP server** (`intelligence/mcp/*_server.py`). The registry (`registry.py`) discovers all tools once and exposes them two ways:

1. **Structured:** `registry.llm_tools()` — OpenAI-style function schemas, converted to Gemini's `FunctionDeclaration` format inside `GeminiClient` (via `parameters_json_schema`, which accepts JSON Schema directly, including `$defs`/`$ref`/`additionalProperties`).
2. **Prompted:** a natural-language tool catalog appended to each agent's system prompt, so the model reasons about *when* to use each tool.

Execution is in-process via FastMCP's in-memory client — no subprocesses or sockets. Heavy dependencies (MedCAT, MONAI/torch) are imported lazily and degrade gracefully: NLP falls back to a deterministic lexicon, imaging returns a structured `model_not_configured` response until weights are set in `.env`.

## Agent Layer

`MCPAgent` (in `intelligence/agents/base.py`) = system prompt + MCP tool whitelist + `run(query, context)`. Every prompt embeds the medical disclaimer and the no-fabricated-citations rule.

| Agent | Tools | Role |
|---|---|---|
| EvidenceAgent | search_clinical_guidelines, search_pubmed | Cited evidence — always runs |
| RadiologyAgent | describe_medical_image, inspect_medical_image, analyze_medical_image | Runs when `context.image_path` present |
| LabAgent | (context only) | Runs when `context.lab_results` present |
| DrugSafetyAgent | check_drug_interactions | Runs when `context.medications` present |
| ClinicalCoordinator | extract_medical_entities, summarize_clinical_note | Synthesizes everything |

The LangGraph workflow (`intelligence/agents/workflow.py`) fans out conditionally from START to the relevant specialists **in parallel**, then merges their outputs (dict/list reducers on the shared state) into the coordinator, which produces the final structured, cited answer.

## API Layer

FastAPI routers under `platform/api/routers/`:

- `POST /api/agents/consult` — full multi-agent workflow
- `POST /api/agents/ask` — single specialist directly
- `GET /api/patients`, `/api/patients/{id}`, `/{id}/timeline` — patient data, backed by Postgres
- `POST /api/medical/nlp/extract`, `/imaging/analyze`, `/drugs/check` — direct tool access
- `GET /api/rag/search`, `/api/rag/pubmed` — evidence lookup
- `GET /api/dashboard/stats` — KPIs + agent/system status

## Frontend

Next.js 14 (App Router) + TypeScript + Tailwind + React Query + Recharts. Dev server proxies `/api/*` to FastAPI (no CORS pain). Design tokens in `platform/frontend/tailwind.config.ts`:

- Nexura-derived palette: primary `#3683F8`, ink `#060606`, surface `#EBF3FE`, border `#D8D8D8`, font Manrope
- **Sephiroth/Platino gradient** (`#8C92AC → #D1D5DB`): exclusively marks AI-generated content (agent badges, AI card borders, avatar ring)

Pages: `/dashboard`, `/copilot` (chat with agent badges + tool traces), `/patients`, `/patients/[id]` (Intelligent Timeline), `/imaging`, `/evidence`, `/agents`.

## Deployment

`docker-compose up` starts Postgres (pgvector) + API. The API talks to Gemini over the internet — no host GPU or local model server required. `JWT_SECRET` and `GEMINI_API_KEY` are required environment variables (compose fails fast if `JWT_SECRET` is unset).
