# SEPHIROTH

**Clinical AI Intelligence Platform** — an **AI decision-support platform** for healthcare professionals. Specialized AI agents — powered by the Google Gemini API — extract clinical entities, analyze medical images, screen drug interactions, and retrieve cited evidence from clinical guidelines and PubMed. Beyond the AI copilot, the platform also covers scheduling, alerts and approvals, exam-result sharing, and a patient portal.

> **Research, education and professional support only.** Not a medical device. All AI output requires review by a qualified healthcare professional.

> **Privacy notice:** clinical text and medical images are sent to the Google Gemini API (AI Studio free tier). This is **not HIPAA/GDPR-compliant as-is**, and the free tier may use submitted data to improve Google's models. Use only with synthetic or de-identified data, or migrate to Vertex AI with a Business Associate Agreement before using real patient data.

**Jump to:** [Highlights](#highlights) · [Quick Start](#quick-start) · [How It Works](#architecture) · [Evaluation Results](#evaluation) · [Project Structure](#project-structure) · [Sample Data](#sample-data) · [Docker](#docker)

## Highlights

**AI reasoning**
- **Cloud LLM via Google Gemini** — `gemini-flash-latest` with native tool calling and JSON-Schema structured output; free tier, no local GPU required
- **Vision-enabled image reasoning** — the same Gemini model describes medical images multimodally; the Radiology agent reasons over the description
- **MCP tool layer** — clinical capabilities exposed as FastMCP servers (NLP, imaging, vision, evidence, drug safety, patient-message drafting)
- **Single-specialist routing, not a multi-agent fan-out** — an intent router sends each consultation to exactly one specialist (Radiology, Evidence, or Drug Safety); a pure lookup (guideline search, drug interaction check) short-circuits before any model call at all
- **Live streaming consultations** — SSE stream shows each agent and tool call as it completes

**Trust & safety**
- **Citation Guard** — every citation in an answer is verified against actual tool output; fabricated references are stripped and reported (an anti-hallucination firewall)
- **Explainability panel** — a deterministic reasoning trace under every answer: which agent did what, with which tool, and how many citations survived the guard
- **Rule-based clinical dashboard** — deterministic risk flags (abnormal labs, dangerous drug combinations) on every patient; each dashboard alert explains itself (the rule, the value, the threshold), shows its recent trend, and says whether it is new or recurring — with no fabricated confidence score

**Clinical workflow**
- **Broader than chat** — scheduling and appointments, an alert and approval queue, exam-result sharing with a patient portal, and a follow-up flow that drafts (never sends without review) a patient-facing message
- **Auto-generated Intelligent Timeline** — paste a clinical note **or upload a PDF** and Gemini extracts structured timeline events (diagnoses, med changes, labs, imaging)
- **PDF consultation export** — download any consultation as a shareable clinical report (query, answer, citations, reasoning trace, disclaimer)

**Access & security**
- **Auth + per-user history** — JWT login/registration, TOTP MFA (two-factor login codes), password reset, and login lockout after repeated failed attempts; every consultation is persisted to Postgres under the requesting clinician
- **Security hardening** — least-privilege database role + row-level security, API rate limiting + security headers, column-level encryption of patient data at rest, and a reviewable access audit log
- **Structured logging** — request ids, per-LLM-call latency, and an audit line per persisted consultation

## Quick Start

### Prerequisites
- A free Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey)
- Python 3.10+ (3.11 recommended)
- Node.js 18+

### 1. Set your API key
```bash
cp .env.example .env
# edit .env and set GEMINI_API_KEY=your-key-here
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

# One-time: populate the RAG corpus (guideline_documents) — not done on
# app boot (SPEC-030 NG-1, no live ingestion endpoint). Safe to re-run.
PYTHONPATH=.:platform .venv/bin/python -m data.rag.seed_pgvector
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

# Full consultation, streamed as SSE (calls Gemini — burns free-tier quota)
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
PYTHONPATH=.:platform .venv/bin/pytest --cov   # no services needed (SQLite in-memory), no GEMINI_API_KEY needed
```

## Architecture

A consultation takes one of two paths, cheapest first:

```
Next.js frontend (3100)
        │  /api/* proxy
        ▼
FastAPI backend (8000)
        │
        ▼
platform/api/fast_path.py — pure lookup? (guideline search, drug interaction)
   ├─ YES → tool result returned verbatim with its own citation.  0 LLM calls, ~4s
   └─ NO ↓
src/sephiroth/runtime/executor.py
        │
        ▼
intent_router picks ONE specialist (Radiology, Evidence, or Drug Safety) → it answers directly.  1 LLM call
        │
        ▼
citation guard (deterministic) → claim verification (1 LLM call) → abstention gate (deterministic) → trace
        │
        ▼
Gemini (native tool calling, cloud API) — model set by `GEMINI_MODEL`, default `gemini-flash-latest`
```

There is no coordinator turn and no parallel fan-out: every consultation is routed to exactly one specialist, whose answer is the final answer (see `CLAUDE.md`, decision #24). Each specialist is an `Agent`: a role prompt + a whitelist of MCP tools. The MCP registry feeds tool schemas to Gemini's structured function-calling contract **and** summarizes them in the agent's system prompt. The whitelist is enforced at dispatch, so an agent cannot invoke a tool outside its declared scope.

See [ARCHITECTURE.md](ARCHITECTURE.md), [CLAUDE.md](CLAUDE.md), and [docs/](docs/) for details. The architecture is being migrated to a model-agnostic runtime — see [docs/00-migration-charter.md](docs/00-migration-charter.md).

## Evaluation

How well does the evidence-retrieval pipeline actually find the right guideline and avoid making things up? We test it against a fixed set of 33 questions over a 76-document corpus of real clinical guidelines (ADA, USPSTF, KDIGO, ACC/AHA, GINA, IDSA, WHO, MedlinePlus, and more):

- **18 "golden" questions** — one representative case per clinical category (trimmed from 101 on 2026-09-20 to cut near-duplicate phrasings; see `docs/dev-log/2026-09-20.md`)
- **6 colloquial paraphrases** — the same questions asked the way a real person would (pinned in [`tests/test_embeddings_matching.py`](tests/test_embeddings_matching.py))
- **9 adversarial questions** — 5 are out-of-scope, 4 have a plausible-but-wrong answer the system should reject

| Metric | Value | Threshold | What it measures |
|---|---|---|---|
| Recall@1 | **0.93** | 0.87 | Correct guideline is the top retrieval hit |
| Recall@3 | **0.99** | 0.94 | Correct guideline is in the top 3 |
| Recall@5 | **1.00** | 0.95 | Correct guideline is in the top 5 |
| MRR | **0.98** | 0.90 | Mean reciprocal rank of the correct guideline |
| Citation Precision | **0.72** | 0.60 | Fraction of citations in answers that are traceable to actual tool output (via [Citation Guard](src/sephiroth/verification/citation_guard.py)) |
| Faithfulness (LLM judge) | **0.78** | 0.25 | Fraction of answer claims a judge model rates as supported by the retrieved evidence |
| Faithfulness (heuristic proxy, informational) | 0.33 | — | Deterministic token-overlap stand-in; runs in CI, not gated |

Recall@k and MRR are computed offline (`--mode ci`, no API key needed); Citation Precision and Faithfulness come from a live local-model run (`--mode full --record`). Retrieval combines keyword + dense-embedding search (pgvector, Reciprocal Rank Fusion) so colloquial questions ("blood thinners for AFib") still match the right guideline. Groq is an optional fallback when Gemini's free-tier quota runs out.

Full methodology (how each number is produced, retrieval internals, Groq fallback config, honest limitations): [`docs/04-development/evaluation.md`](docs/04-development/evaluation.md). Raw run data: [`intelligence/evaluation/results/latest.json`](intelligence/evaluation/results/latest.json).

```bash
PYTHONPATH=.:platform .venv/bin/python -m intelligence.evaluation.run --mode ci
```

## Project Structure

```
clinical-ai-copilot/
├── platform/          # FastAPI backend (api/, core/, auth/) + Next.js frontend
│                      # (copilot chat, dashboard, patients, scheduling,
│                      # alerts/approvals, results sharing, patient portal)
│                      # — api/workflows/ holds the durable automation engine
│                      # behind alerts, reminders, and patient follow-up
├── intelligence/      # mcp/ (6 FastMCP servers: nlp, imaging, rag, drug_safety,
│                      # vision, patient_comms), agents/ (thin shim into
│                      # src/sephiroth/), evaluation/ (RAG eval harness — see below)
├── src/sephiroth/     # the runtime: models/ (providers), tools/ (MCP dispatch),
│                      # runtime/ (agents, executor), verification/, safety/,
│                      # context/, telemetry/, clinical/ (deterministic helpers),
│                      # contracts/ (shared typed schemas), workflows/ (automation
│                      # event/policy types) — see CLAUDE.md for the full map
├── data/              # rag/ (evidence retrieval, pgvector), schemas/ (SQLAlchemy models)
├── migrations/        # Alembic schema migrations (local Postgres and Supabase)
├── examples/          # Runnable examples per module
├── scripts/           # Maintenance/CI scripts (commit-msg validation, PHI backfill, docs check, ...)
├── docs/              # Spec-Driven Development: specs, decision records,
│                      # architecture notes, dev-log, project-state.yaml
├── real_data/         # Optional real/synthetic sample data — see Sample Data below
├── tests/             # pytest suite (SQLite in-memory; no external services required)
└── references/        # Cloned open-source projects (read-only reference; not committed — see .gitignore)
```

`references/` holds read-only clones used for API reference while building the MONAI/MedCAT/LangGraph wrappers in `intelligence/`. Not committed (see `.gitignore`) and not required to run or test the app — clone them only if you're extending those integrations:

```bash
mkdir -p references
git clone --depth 1 https://github.com/Project-MONAI/MONAI.git references/ref-monai-medical-imaging
git clone --depth 1 https://github.com/CogStack/MedCAT.git references/ref-medcat-nlp
git clone --depth 1 https://github.com/langchain-ai/langgraph.git references/ref-langgraph-agents
```

## Sample Data

`real_data/` has optional, real/synthetic sample data for a more realistic demo: 12 real synthetic patient histories (Synthea, Apache 2.0), 6 clinical notes, 193 real drug-interaction severity pairs (DDInter 2.0, CC BY-NC), and a script for fetching real chest X-rays (RSNA, academic use only — never committed). **None of this is needed to run the app or the tests** — see [`real_data/README.md`](real_data/README.md) for what's in each source, its exact license, and how to refresh it.

Schema is Alembic-managed (`migrations/`) for both local Postgres and any cloud Postgres (e.g. Supabase) — see CLAUDE.md's "Database migrations" section before changing a model in `data/schemas/`.

## Docker

```bash
GEMINI_API_KEY=your-key JWT_SECRET=$(openssl rand -hex 32) docker-compose up   # Postgres + API
```

The API reaches Gemini over the internet — no host GPU or local model server required. `JWT_SECRET` is a required environment variable; compose refuses to start without it. Containers are named `sephiroth-*` (`docker ps`) regardless of the checkout folder's name.

Need to tweak a port or point at a locally-running LLM because of other containers on your machine? Create a `docker-compose.override.yml` (gitignored — Compose merges it automatically, never commit it).

## Built On

| Project | Role | License |
|---|---|---|
| [Google Gemini API](https://ai.google.dev/gemini-api/docs) | Cloud LLM (reasoning, tool calling, vision) | [Terms](https://ai.google.dev/gemini-api/terms) |
| [FastMCP](https://github.com/jlowin/fastmcp) | MCP tool servers | Apache 2.0 |
| [MONAI](https://github.com/Project-MONAI/MONAI) | Medical imaging | Apache 2.0 |
| [MedCAT](https://github.com/CogStack/MedCAT) | Clinical NLP | Apache 2.0 |
| [FastAPI](https://github.com/fastapi/fastapi) | Backend framework | MIT |
| [Next.js](https://github.com/vercel/next.js) | Frontend framework | MIT |

Dashboard design adapted from the [Nexura Care](https://www.behance.net/gallery/246611721/Nexura-Care-Dashboard-Healthcare-Platform-(UIUX)) concept by Mohammed Agami.

## Disclaimer

This system provides **evidence-grounded decision support**, not diagnoses. It is intended for research, education, and as an aid to qualified healthcare professionals, who retain full clinical responsibility. It sends clinical data to a third-party cloud API (Google Gemini) — see the privacy notice above before using real patient data.
