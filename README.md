# SEPHIROTH

**Clinical AI Intelligence Platform** — a **local-first AI decision-support platform** for healthcare professionals. Specialized AI agents — powered entirely by a local Ollama model — extract clinical entities, analyze medical images, screen drug interactions, and retrieve cited evidence from clinical guidelines and PubMed.

> ⚠️ **Research, education and professional support only.** Not a medical device. All AI output requires review by a qualified healthcare professional.

## Highlights

- 🧠 **100% local inference** — Ollama (`qwen3:8b`) with native tool calling; no cloud LLM APIs, no PHI leaves the machine
- 👁️ **Vision-enabled image reasoning** — a local multimodal model (`llava:7b`) describes medical images; the Radiology agent reasons over the description
- 🔧 **MCP tool layer** — clinical capabilities exposed as FastMCP servers (NLP, imaging, vision, evidence, drug safety)
- 🤖 **Multi-agent workflow** — 4 specialists + a coordinator orchestrated with LangGraph, fanning out in parallel
- 📡 **Live streaming consultations** — SSE stream shows each agent and tool call as it completes
- 🛡️ **Citation Guard** — every citation in an answer is verified against actual tool output; fabricated references are stripped and reported (an anti-hallucination firewall)
- 🧭 **Explainability panel** — a deterministic reasoning trace under every answer: which agent did what, with which tool, and how many citations survived the guard
- ⚠️ **Risk scoring & alerts** — rule-based flags (abnormal labs, dangerous drug combos) on every patient, plus a High-Risk Patients KPI
- 🗓️ **Auto-generated Intelligent Timeline** — paste a clinical note **or upload a PDF** and the local model extracts structured timeline events (diagnoses, med changes, labs, imaging)
- 📄 **PDF consultation export** — download any consultation as a shareable clinical report (query, answer, citations, reasoning trace, disclaimer)
- 🔐 **Auth + per-user history** — JWT login/registration; every consultation is persisted to Postgres under the requesting clinician
- 📋 **Structured logging** — request ids, per-LLM-call latency, and an audit line per persisted consultation
- 🎨 **Modern dashboard** — Next.js 14 + Tailwind, design system derived from the Nexura Care reference

## Quick Start

### Prerequisites
- [Ollama](https://ollama.com) installed and running natively (not in Docker)
- Python 3.10+ (3.11 recommended)
- Node.js 18+

### 1. Pull the models (one-time)
```bash
ollama pull qwen3:8b     # reasoning + tool calling
ollama pull llava:7b     # vision (medical image description)
```

### 2. Database + Backend
```bash
docker compose up -d postgres        # Postgres 15 + pgvector (host port 5433)

python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt

# `platform/` is added to PYTHONPATH because it cannot be a Python package
# (the name would shadow the stdlib `platform` module).
# First boot creates the tables and seeds two demo patients.
PYTHONPATH=.:platform .venv/bin/uvicorn api.main:app --reload --port 8000
```

### 3. Frontend
```bash
cd platform/frontend
npm install
npm run dev -- --port 3100
```

Open http://localhost:3100 — the Next.js dev server proxies `/api/*` to the backend.

> **Port note:** if something (e.g. Docker Desktop) already binds 8000/3000, the backend still answers on `http://127.0.0.1:8000` (IPv4) and the frontend runs on 3100 as shown above.

### Try it
```bash
# Evidence search with citations (public)
curl "http://127.0.0.1:8000/api/rag/search?q=first-line+treatment+for+hypertension"

# Register + login (agent endpoints require auth)
curl -X POST http://127.0.0.1:8000/api/auth/register -H "Content-Type: application/json" \
  -d '{"email": "doc@hospital.org", "name": "Dr. Smith", "password": "atleast8chars"}'
TOKEN=<access_token from the response>

# Full multi-agent consultation, streamed as SSE (local LLM)
curl -N -X POST http://127.0.0.1:8000/api/agents/consult/stream \
  -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" \
  -d '{"query": "Medication safety concerns for this patient?", "patient_id": "P002",
       "context": {"medications": ["warfarin", "aspirin"], "lab_results": {"inr": "2.4"}}}'

# Paste a clinical note → AI-extracted timeline events
curl -X POST http://127.0.0.1:8000/api/patients/P001/notes \
  -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" \
  -d '{"content": "2026-05-02: HbA1c 7.4%. Started atorvastatin 40mg for hyperlipidemia."}'
```

### Run the tests
```bash
PYTHONPATH=.:platform .venv/bin/pytest   # no services needed (SQLite in-memory)
```

## Architecture

```
Next.js frontend (3100)
        │  /api/* proxy
        ▼
FastAPI backend (8000)
        │
        ▼
LangGraph workflow ──► ClinicalCoordinator
   │ parallel fan-out
   ├─► EvidenceAgent ────► rag_server (guidelines + PubMed, cited)
   ├─► RadiologyAgent ───► imaging_server (MONAI)
   ├─► LabAgent ─────────► patient context
   └─► DrugSafetyAgent ──► drug_safety_server
        │
        ▼
Ollama qwen3:8b (native tool calling, host Metal GPU)
```

Each specialist is an `OllamaMCPAgent`: a system prompt + a whitelist of MCP tools. The MCP registry feeds tool schemas to Ollama's structured `tools` parameter **and** summarizes them in the agent's system prompt.

See [ARCHITECTURE.md](ARCHITECTURE.md) and [CLAUDE.md](CLAUDE.md) for details.

## Project Structure

```
clinical-ai-copilot/
├── platform/          # FastAPI backend (api/, core/, auth/) + Next.js frontend
├── intelligence/      # llm/ (Ollama client), mcp/ (FastMCP servers), agents/ (LangGraph)
├── data/              # rag/ (evidence retrieval), schemas/ (SQLAlchemy models)
├── examples/          # Runnable examples per module
├── docs/              # Integration guide
└── references/        # Cloned open-source projects (read-only reference)
```

## Docker

```bash
docker-compose up   # Postgres + Redis + API
```

Ollama stays on the host (Docker on macOS has no Metal GPU passthrough); the API container reaches it via `host.docker.internal:11434`.

## Built On

| Project | Role | License |
|---|---|---|
| [Ollama](https://ollama.com) | Local LLM runtime | MIT |
| [FastMCP](https://github.com/jlowin/fastmcp) | MCP tool servers | Apache 2.0 |
| [LangGraph](https://github.com/langchain-ai/langgraph) | Agent orchestration | MIT |
| [MONAI](https://github.com/Project-MONAI/MONAI) | Medical imaging | Apache 2.0 |
| [MedCAT](https://github.com/CogStack/MedCAT) | Clinical NLP | Apache 2.0 |
| [FastAPI](https://github.com/fastapi/fastapi) | Backend framework | MIT |
| [Next.js](https://github.com/vercel/next.js) | Frontend framework | MIT |

Dashboard design adapted from the [Nexura Care](https://www.behance.net/gallery/246611721/Nexura-Care-Dashboard-Healthcare-Platform-(UIUX)) concept by Mohammed Agami.

## Disclaimer

This system provides **evidence-grounded decision support**, not diagnoses. It is intended for research, education, and as an aid to qualified healthcare professionals, who retain full clinical responsibility.
