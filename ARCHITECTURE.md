# SEPHIROTH — Architecture

## Overview

A local-first clinical decision-support platform. All LLM inference runs on the user's machine through Ollama; clinical capabilities are packaged as MCP tool servers; specialist agents are orchestrated with LangGraph and always ground their answers in tool output and citations.

## Directory Structure

```
clinical-ai-copilot/
├── platform/                 # Backend + frontend (NOT a Python package — see note below)
│   ├── api/                  # FastAPI app: main.py + routers/ (agents, patients, medical, rag, dashboard)
│   ├── core/                 # Settings (Ollama host/model, DB URLs, feature flags)
│   ├── auth/                 # Authentication layer (planned)
│   └── frontend/             # Next.js 14 app (Nexura-derived design system)
│
├── intelligence/
│   ├── llm/                  # OllamaClient — chat + tool-call loop against /api/chat
│   ├── mcp/                  # FastMCP servers + registry (the Ollama⇄MCP bridge)
│   │   ├── registry.py       #   discovers tools, emits Ollama schemas + prompt summaries
│   │   ├── nlp_server.py     #   entity extraction, note summarization
│   │   ├── imaging_server.py #   DICOM/NIfTI inspection, MONAI analysis
│   │   ├── rag_server.py     #   guideline search + PubMed (always cited)
│   │   └── drug_safety_server.py  # interaction screening
│   ├── agents/               # OllamaMCPAgent base + 5 agents + LangGraph workflow
│   ├── medical-imaging/      # MONAI reference code (transforms, networks)
│   ├── nlp/                  # MedCAT reference code (ner, pipeline, preprocessing)
│   └── evaluation/           # Model evaluation (planned)
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

- **Runtime:** Ollama, natively on the host (Metal GPU on Apple Silicon; Docker on macOS has no GPU passthrough).
- **Model:** `qwen3:8b` — native tool calling, lowest dropped-tool-call rate among local models, fits 16 GB unified memory.
- **Thinking mode is off** (`think=False`) — it multiplies latency ~4× and the agents rely on tools rather than long hidden reasoning. A single-agent tool query answers in ~10–15 s; a full multi-agent consultation in ~1 minute.
- `OllamaClient.chat()` loops: send request → execute any `tool_calls` through the MCP registry → append `tool` role results → repeat until a plain answer (max 8 rounds).

## MCP Tool Layer

Each clinical capability is a **FastMCP server** (`intelligence/mcp/*_server.py`). The registry (`registry.py`) discovers all tools once and exposes them two ways:

1. **Structured:** Ollama's native `tools` parameter (function-calling contract).
2. **Prompted:** a natural-language tool catalog appended to each agent's system prompt, so the model reasons about *when* to use each tool.

Execution is in-process via FastMCP's in-memory client — no subprocesses or sockets. Heavy dependencies (MedCAT, MONAI/torch) are imported lazily and degrade gracefully: NLP falls back to a deterministic lexicon, imaging returns a structured `model_not_configured` response until weights are set in `.env`.

## Agent Layer

`OllamaMCPAgent` (in `intelligence/agents/base.py`) = system prompt + MCP tool whitelist + `run(query, context)`. Every prompt embeds the medical disclaimer and the no-fabricated-citations rule.

| Agent | Tools | Role |
|---|---|---|
| EvidenceAgent | search_clinical_guidelines, search_pubmed | Cited evidence — always runs |
| RadiologyAgent | inspect_medical_image, analyze_medical_image | Runs when `context.image_path` present |
| LabAgent | (context only) | Runs when `context.lab_results` present |
| DrugSafetyAgent | check_drug_interactions | Runs when `context.medications` present |
| ClinicalCoordinator | extract_medical_entities, summarize_clinical_note | Synthesizes everything |

The LangGraph workflow (`intelligence/agents/workflow.py`) fans out conditionally from START to the relevant specialists **in parallel**, then merges their outputs (dict/list reducers on the shared state) into the coordinator, which produces the final structured, cited answer.

## API Layer

FastAPI routers under `platform/api/routers/`:

- `POST /api/agents/consult` — full multi-agent workflow
- `POST /api/agents/ask` — single specialist directly
- `GET /api/patients`, `/api/patients/{id}`, `/{id}/timeline` — patient data (in-memory demo store; swap for SQLAlchemy when Postgres is provisioned)
- `POST /api/medical/nlp/extract`, `/imaging/analyze`, `/drugs/check` — direct tool access
- `GET /api/rag/search`, `/api/rag/pubmed` — evidence lookup
- `GET /api/dashboard/stats` — KPIs + agent/system status

## Frontend

Next.js 14 (App Router) + TypeScript + Tailwind + React Query + Recharts. Dev server proxies `/api/*` to FastAPI (no CORS pain). Design tokens in `platform/frontend/tailwind.config.ts`:

- Nexura-derived palette: primary `#3683F8`, ink `#060606`, surface `#EBF3FE`, border `#D8D8D8`, font Manrope
- **Sephiroth/Platino gradient** (`#8C92AC → #D1D5DB`): exclusively marks AI-generated content (agent badges, AI card borders, avatar ring)

Pages: `/dashboard`, `/copilot` (chat with agent badges + tool traces), `/patients`, `/patients/[id]` (Intelligent Timeline), `/imaging`, `/evidence`, `/agents`.

## Deployment

`docker-compose up` starts Postgres (pgvector) + Redis + API. Ollama stays on the host; the API container reaches it via `host.docker.internal:11434`.
