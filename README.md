# SEPHIROTH

![CI](https://github.com/Juanpacol/SEPHIROTH/actions/workflows/ci.yml/badge.svg)
![coverage](https://img.shields.io/badge/coverage-88%25-brightgreen)

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
PYTHONPATH=.:platform .venv/bin/pytest --cov   # no services needed (SQLite in-memory)
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

## Evaluation

The Evidence Agent's RAG pipeline is measured against a 27-question golden dataset (15 direct/"golden" clinical questions, 8 colloquial paraphrases, 4 adversarial questions with no supporting guideline at all) over a 23-document corpus of clinical guideline excerpts (ADA, USPSTF, KDIGO, ACC/AHA, GINA, IDSA, WHO, and more).

| Metric | Value | Threshold | What it measures |
|---|---|---|---|
| Recall@1 | **0.78** | 0.75 | Correct guideline is the top retrieval hit |
| Recall@3 | **0.99** | 0.95 | Correct guideline is in the top 3 |
| Recall@5 | **0.99** | 0.95 | Correct guideline is in the top 5 |
| MRR | **0.88** | 0.85 | Mean reciprocal rank of the correct guideline |
| Citation Precision | **0.64** | 0.60 | Fraction of citations in answers that are traceable to actual tool output (via [Citation Guard](intelligence/agents/citation_guard.py)) |
| Faithfulness (LLM judge) | **0.28** | 0.25 | Fraction of answer claims a judge model rates as supported by the retrieved evidence |
| Faithfulness (heuristic proxy, informational) | 0.57 | — | Deterministic token-overlap stand-in; runs in CI, not gated |

*(Full numbers, per-case breakdown, and run metadata: [`intelligence/evaluation/results/latest.json`](intelligence/evaluation/results/latest.json).)*

**How it works — two modes, one committed baseline:**
- **`--mode ci`** (offline, deterministic, <5s): Recall@k and MRR are recomputed live against `RAGPipeline.retrieve()` and the golden dataset; Citation Precision is recomputed by replaying the Citation Guard over committed transcripts. This is what runs on every PR — no Ollama required.
- **`--mode full`** (local, needs Ollama): runs the real Evidence Agent end-to-end, records fresh transcripts, and scores Faithfulness with an LLM judge (per-claim: "is this supported by the retrieved evidence?"). Writes `results/latest.json`.
- The committed results embed a SHA-256 hash of the dataset and transcripts. If either changes without a fresh `--mode full --record` run, CI fails on a **stale baseline** rather than silently trusting outdated numbers.

```bash
PYTHONPATH=.:platform .venv/bin/python -m intelligence.evaluation.run --mode ci
PYTHONPATH=.:platform .venv/bin/python -m intelligence.evaluation.run --mode full --record --skip-pubmed
```

**Honest limitations:**
- The committed baseline was generated with `llama3.2:latest` as a stand-in — `qwen3:8b` (the production model) wasn't pulled locally at eval time. Recall@k/MRR are retrieval-only and already reflect production behavior; Citation Precision and Faithfulness should improve once regenerated against `qwen3:8b`.
- Retrieval is keyword/token-overlap scoring (`data/rag/RAGPipeline.retrieve`), not embeddings — Recall@1 on paraphrased queries is the weakest number here and is the concrete, measured case for the pgvector/embeddings upgrade already planned in `data/embeddings/` and `data/vectors/`.
- The LLM judge is the same model family as the generator on the committed baseline (a self-judging limitation); an independent judge model would be a stronger signal.

## Project Structure

```
clinical-ai-copilot/
├── platform/          # FastAPI backend (api/, core/, auth/) + Next.js frontend
├── intelligence/      # llm/ (Ollama client), mcp/ (FastMCP servers), agents/ (LangGraph),
│                      # evaluation/ (RAG eval harness — see Evaluation above)
├── data/              # rag/ (evidence retrieval), schemas/ (SQLAlchemy models)
├── examples/          # Runnable examples per module
├── docs/              # Integration guide
└── references/        # Cloned open-source projects (read-only reference; not committed — see .gitignore)
```

`references/` holds read-only clones used for API reference while building the MONAI/MedCAT/LangGraph wrappers in `intelligence/`. Not committed (see `.gitignore`) and not required to run or test the app — clone them only if you're extending those integrations:

```bash
mkdir -p references
git clone --depth 1 https://github.com/Project-MONAI/MONAI.git references/ref-monai-medical-imaging
git clone --depth 1 https://github.com/CogStack/MedCAT.git references/ref-medcat-nlp
git clone --depth 1 https://github.com/langchain-ai/langgraph.git references/ref-langgraph-agents
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
