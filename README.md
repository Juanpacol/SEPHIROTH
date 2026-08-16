# SEPHIROTH

![CI](https://github.com/Juanpacol/SEPHIROTH/actions/workflows/ci.yml/badge.svg)
![coverage](https://img.shields.io/badge/coverage-87%25-brightgreen)

**Clinical AI Intelligence Platform** — an **AI decision-support platform** for healthcare professionals. Specialized AI agents — powered by the Google Gemini API — extract clinical entities, analyze medical images, screen drug interactions, and retrieve cited evidence from clinical guidelines and PubMed.

> ⚠️ **Research, education and professional support only.** Not a medical device. All AI output requires review by a qualified healthcare professional.

> ⚠️ **Privacy notice:** clinical text and medical images are sent to the Google Gemini API (AI Studio free tier). This is **not HIPAA/GDPR-compliant as-is**, and the free tier may use submitted data to improve Google's models. Use only with synthetic or de-identified data, or migrate to Vertex AI with a Business Associate Agreement before using real patient data.

## Highlights

- 🧠 **Cloud LLM via Google Gemini** — `gemini-flash-latest` with native tool calling and JSON-Schema structured output; free tier, no local GPU required
- 👁️ **Vision-enabled image reasoning** — the same Gemini model describes medical images multimodally; the Radiology agent reasons over the description
- 🔧 **MCP tool layer** — clinical capabilities exposed as FastMCP servers (NLP, imaging, vision, evidence, drug safety)
- 🤖 **Multi-agent workflow** — 4 specialists + a coordinator orchestrated with LangGraph, fanning out in parallel
- 📡 **Live streaming consultations** — SSE stream shows each agent and tool call as it completes
- 🛡️ **Citation Guard** — every citation in an answer is verified against actual tool output; fabricated references are stripped and reported (an anti-hallucination firewall)
- 🧭 **Explainability panel** — a deterministic reasoning trace under every answer: which agent did what, with which tool, and how many citations survived the guard
- ⚠️ **Risk scoring & alerts** — rule-based flags (abnormal labs, dangerous drug combos) on every patient, plus a High-Risk Patients KPI
- 🗓️ **Auto-generated Intelligent Timeline** — paste a clinical note **or upload a PDF** and Gemini extracts structured timeline events (diagnoses, med changes, labs, imaging)
- 📄 **PDF consultation export** — download any consultation as a shareable clinical report (query, answer, citations, reasoning trace, disclaimer)
- 🔐 **Auth + per-user history** — JWT login/registration; every consultation is persisted to Postgres under the requesting clinician
- 📋 **Structured logging** — request ids, per-LLM-call latency, and an audit line per persisted consultation
- 🎨 **Modern dashboard** — Next.js 14 + Tailwind, design system derived from the Nexura Care reference

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

# Full multi-agent consultation, streamed as SSE (calls Gemini — burns free-tier quota)
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
   ├─► RadiologyAgent ───► imaging_server (MONAI) + vision_server (Gemini)
   ├─► LabAgent ─────────► patient context
   └─► DrugSafetyAgent ──► drug_safety_server
        │
        ▼
Gemini (native tool calling, cloud API) — model set by `GEMINI_MODEL`, default `gemini-flash-latest`
```

Each specialist is an `MCPAgent`: a role prompt + a whitelist of MCP tools. The MCP registry feeds tool schemas to Gemini's structured function-calling contract **and** summarizes them in the agent's system prompt. The whitelist is enforced at dispatch, so an agent cannot invoke a tool outside its declared scope.

See [ARCHITECTURE.md](ARCHITECTURE.md), [CLAUDE.md](CLAUDE.md), and [docs/](docs/) for details. The architecture is being migrated to a model-agnostic runtime — see [docs/00-migration-charter.md](docs/00-migration-charter.md).

## Evaluation

The Evidence Agent's RAG pipeline is measured against a 27-question golden dataset (15 direct/"golden" clinical questions, 8 colloquial paraphrases, 4 adversarial questions with no supporting guideline at all) over a 23-document corpus of clinical guideline excerpts (ADA, USPSTF, KDIGO, ACC/AHA, GINA, IDSA, WHO, and more).

| Metric | Value | Threshold | What it measures |
|---|---|---|---|
| Recall@1 | **0.97** | 0.90 | Correct guideline is the top retrieval hit |
| Recall@3 | **1.00** | 0.95 | Correct guideline is in the top 3 |
| Recall@5 | **1.00** | 0.95 | Correct guideline is in the top 5 |
| MRR | **1.00** | 0.93 | Mean reciprocal rank of the correct guideline |
| Citation Precision | **0.64** | 0.60 | Fraction of citations in answers that are traceable to actual tool output (via [Citation Guard](intelligence/agents/citation_guard.py)) |
| Faithfulness (LLM judge) | **0.28** | 0.25 | Fraction of answer claims a judge model rates as supported by the retrieved evidence |
| Faithfulness (heuristic proxy, informational) | 0.57 | — | Deterministic token-overlap stand-in; runs in CI, not gated |

Recall@1/@3/@5 and MRR are **live, verified numbers** from the hybrid retriever described below, run via `--mode ci` against the committed embeddings artifact (reproducible offline, no API key needed). Citation Precision and Faithfulness are still from the pre-Gemini baseline (see limitations) — regenerating them requires a live `--mode full --record` run, which needs enough Gemini API quota to complete an agent run per golden case.

*(Full numbers, per-case breakdown, and run metadata: [`intelligence/evaluation/results/latest.json`](intelligence/evaluation/results/latest.json).)*

**How it works — two modes, one committed baseline:**
- **`--mode ci`** (offline, deterministic, <5s): Recall@k and MRR are recomputed live against `RAGPipeline.retrieve()` and the golden dataset; Citation Precision is recomputed by replaying the Citation Guard over committed transcripts. This is what runs on every PR — **no Gemini API key required**.
- **`--mode full`** (calls the Gemini API, burns free-tier quota): runs the real Evidence Agent end-to-end, records fresh transcripts, and scores Faithfulness with an LLM judge (per-claim: "is this supported by the retrieved evidence?"). Writes `results/latest.json`.
- The committed results embed a SHA-256 hash of the dataset and transcripts. If either changes without a fresh `--mode full --record` run, CI fails on a **stale baseline** rather than silently trusting outdated numbers.

```bash
PYTHONPATH=.:platform .venv/bin/python -m intelligence.evaluation.run --mode ci
PYTHONPATH=.:platform .venv/bin/python -m intelligence.evaluation.run --mode full --record --skip-pubmed
```

### Hybrid retrieval (dense embeddings + keyword)

`data/rag/RAGPipeline.retrieve()` fuses keyword-overlap scoring with dense Gemini embeddings (`gemini-embedding-001`) via Reciprocal Rank Fusion, closing the biggest gap in the metrics above: keyword-only Recall@1 misses colloquial paraphrases ("my kid has an ear infection" → *Acute Otitis Media*, "blood thinners for AFib" → *anticoagulation*) that share little vocabulary with the guideline text.

- **Fully backward-compatible.** `RAGPipeline()` alone still works with zero configuration and stays keyword-only. Dense retrieval only activates when an embedding provider is wired in (`GEMINI_API_KEY` set + a built artifact, see below).
- **Deterministic and offline in CI.** A committed, hashed artifact (`data/embeddings/artifacts/seed_embeddings.json.gz`) supplies the vectors for `--mode ci` and the whole test suite — no network, no API key needed. Build/refresh it once with a real key: `python -m data.embeddings.build_artifact`.
- **Adversarial-safe by design, empirically calibrated.** A cosine-similarity floor (`RETRIEVAL_MIN_SIMILARITY`, default **0.70**) drops low-confidence dense hits. This was tuned against real Gemini embedding scores, not guessed: some adversarial queries (e.g. "homeopathic remedy for septic shock") are topically *on-topic* and score in the 0.65-0.70 range even though the requested treatment is unsupported — the floor only needs to (and does) separate those from genuinely relevant top-1 matches, which score 0.73+. It does **not** attempt to detect "this is pseudo-scientific" from embeddings alone; that judgment belongs to the Citation Guard, which checks whether the LLM's specific claims are grounded in what a retrieved document actually says.
- **Dense-weighted fusion.** Reciprocal Rank Fusion weights the dense signal 2x over keyword (`DENSE_WEIGHT`/`KEYWORD_WEIGHT` in `data/rag/__init__.py`) — keyword scoring here isn't IDF-weighted, so short documents sharing only generic words with the query can rank artificially high, and an equal-weight fusion let that noise (or a near-exact RRF tie) occasionally outrank a correct embedding-model result. Confirmed and fixed while building the matching-quality test suite below.
- **Matching-quality test suite** (`tests/test_embeddings_matching.py`, `tests/test_rag_pipeline.py`) pins specific, previously-diagnosed match/no-match pairs — lay-language paraphrases, a compound multi-document query, near-duplicate topic disambiguation (`ada-2024-ckd` vs. `ada-2024-hypertension-dm`), and adversarial abstention — so a regression in one specific case fails by name, not just as a dip in an aggregate metric. All 13 real-artifact tests pass against the committed artifact; the fusion/threshold mechanics are additionally covered with synthetic vectors so they run in every CI run regardless of whether the artifact exists.

**Honest limitations:**
- Citation Precision and Faithfulness in the table above are still from the pre-Gemini baseline (generated with `llama3.2:latest` as a stand-in). Regenerating them against `gemini-flash-latest` via `--mode full --record` requires enough free-tier quota to run an agent consultation per golden case — this repo's own key hit its **daily** free-tier request quota partway through a regeneration attempt (a real, worth-knowing constraint: some Gemini model aliases carry very low free-tier daily caps, independent of the per-minute rate limit `gemini_rpm_limit` already handles). Retry on a fresh day or with a paid tier.
- The LLM judge is the same model family as the generator on the committed baseline (a self-judging limitation); an independent judge model would be a stronger signal.

### Free-tier quota management (Gemini + Groq fallback)

Neither Gemini's nor Groq's free tiers are unlimited — Gemini caps requests **per minute and per day**, and newer model aliases (like `gemini-flash-latest`, which resolves to whatever Google's current flash model is) can carry much stricter daily caps than older, established models. This repo's own key hit a 20-request/day cap on the resolved model while regenerating the eval baseline above.

To make that failure mode non-fatal, `intelligence/llm/factory.py::get_llm_client()` optionally wraps Gemini with a **Groq fallback** for text/tool-calling (`intelligence/llm/fallback_client.py`):

- Set `GROQ_API_KEY` (free key at [console.groq.com/keys](https://console.groq.com/keys)) to enable it — unset, behavior is identical to a bare Gemini client.
- `chat()` and `generate_json()` try Gemini first; on any failure (rate limit, daily quota exhaustion, outage) they fall through to Groq (`llama-3.3-70b-versatile` by default, configurable via `GROQ_MODEL`) — same `ChatResult` contract, so agents and timeline extraction need no changes.
- **Vision and embeddings always stay on Gemini.** Groq has no comparable multimodal or embeddings endpoint, so `describe_medical_image` and the RAG embedding provider never fall back — they degrade to their existing `unavailable`/keyword-only paths instead.
- Set `LLM_ENABLE_FALLBACK=false` to disable fallback even with a Groq key configured (e.g. to test Gemini-only behavior deliberately).

```bash
# .env
GROQ_API_KEY=your-groq-key
GROQ_MODEL=llama-3.3-70b-versatile   # default
```

## Project Structure

```
clinical-ai-copilot/
├── platform/          # FastAPI backend (api/, core/, auth/) + Next.js frontend
├── intelligence/      # llm/ (Gemini client), mcp/ (FastMCP servers), agents/ (LangGraph),
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

## Sample Data

`real_data/` has optional, real/synthetic sample data for a more realistic demo: 12 real synthetic patient histories (Synthea, Apache 2.0), 6 clinical notes, 193 real drug-interaction severity pairs (DDInter 2.0, CC BY-NC), and a script for fetching real chest X-rays (RSNA, academic use only — never committed). **None of this is needed to run the app or the tests** — see [`real_data/README.md`](real_data/README.md) for what's in each source, its exact license, and how to refresh it.

Schema is Alembic-managed (`migrations/`) for both local Postgres and any cloud Postgres (e.g. Supabase) — see CLAUDE.md's "Database migrations" section before changing a model in `data/schemas/`.

## Docker

```bash
GEMINI_API_KEY=your-key JWT_SECRET=$(openssl rand -hex 32) docker-compose up   # Postgres + API
```

The API reaches Gemini over the internet — no host GPU or local model server required. `JWT_SECRET` is a required environment variable; compose refuses to start without it.

## Built On

| Project | Role | License |
|---|---|---|
| [Google Gemini API](https://ai.google.dev/gemini-api/docs) | Cloud LLM (reasoning, tool calling, vision) | [Terms](https://ai.google.dev/gemini-api/terms) |
| [FastMCP](https://github.com/jlowin/fastmcp) | MCP tool servers | Apache 2.0 |
| [LangGraph](https://github.com/langchain-ai/langgraph) | Agent orchestration | MIT |
| [MONAI](https://github.com/Project-MONAI/MONAI) | Medical imaging | Apache 2.0 |
| [MedCAT](https://github.com/CogStack/MedCAT) | Clinical NLP | Apache 2.0 |
| [FastAPI](https://github.com/fastapi/fastapi) | Backend framework | MIT |
| [Next.js](https://github.com/vercel/next.js) | Frontend framework | MIT |

Dashboard design adapted from the [Nexura Care](https://www.behance.net/gallery/246611721/Nexura-Care-Dashboard-Healthcare-Platform-(UIUX)) concept by Mohammed Agami.

## Disclaimer

This system provides **evidence-grounded decision support**, not diagnoses. It is intended for research, education, and as an aid to qualified healthcare professionals, who retain full clinical responsibility. It sends clinical data to a third-party cloud API (Google Gemini) — see the privacy notice above before using real patient data.
