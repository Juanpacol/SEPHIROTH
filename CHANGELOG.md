# Changelog

All notable changes to this project are documented here. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed
- **BREAKING: migrated the LLM backend from local Ollama to the Google Gemini API** (`gemini-2.5-flash`, AI Studio free tier). `intelligence/llm/ollama_client.py` is replaced by `intelligence/llm/gemini_client.py` (`GeminiClient`), accessed through a lazy singleton factory (`intelligence/llm/factory.py::get_llm_client()`). `OllamaMCPAgent` is renamed `MCPAgent`; `registry.ollama_tools()` is renamed `registry.llm_tools()`. Vision description (`vision_server.py`) now goes through the same shared client instead of a second raw Ollama client. Contract preserved: `ChatResult`, `chat()`, `generate_json()`, `health()` keep the same shapes, so the whole agent stack, timeline extraction, and test doubles (`tests/conftest.py::FakeLLMClient`) needed no behavioral changes.
  - ⚠️ **Privacy:** clinical text and images now leave the machine and are sent to Google's Gemini API. Not HIPAA/GDPR-compliant as-is — see README's privacy notice.
  - No API key configured degrades gracefully (`health()` returns `False`, 503s and lexicon/`unavailable` fallbacks as before) rather than crashing.
  - `GEMINI_API_KEY`, `GEMINI_MODEL` replace `OLLAMA_HOST`/`OLLAMA_MODEL`/`OLLAMA_VISION_MODEL` in `.env`/`docker-compose.yml`.
- Removed the unused `redis` service and dependency (`docker-compose.yml`, `requirements.txt`) — a half-finished cleanup from an earlier change, now committed alongside the Gemini migration.
- RAG corpus expanded from 5 to 23 real clinical guideline documents.
- Lint tooling migrated from black + flake8 to ruff (check + format).

### Added
- **Hybrid RAG retrieval, built and verified against a real, committed embeddings artifact**: `data/rag/RAGPipeline.retrieve()` now fuses keyword-overlap scoring with dense Gemini embeddings (`gemini-embedding-001`) via Reciprocal Rank Fusion (dense weighted 2x over keyword — keyword scoring isn't IDF-weighted and can rank short, generic-word-heavy documents artificially high). New `data/embeddings/` (provider protocol, live `GeminiEmbeddingProvider`, `CachedEmbeddingProvider` over a committed, hashed artifact) and `data/vectors/` (`InMemoryVectorStore`, cosine similarity). Fully backward-compatible: `RAGPipeline()` with no configuration stays exactly keyword-only, and any embedding failure falls back silently. `--mode ci`'s staleness gate now also checks the embeddings artifact's corpus hash.
  - **Measured result** (real artifact, `--mode ci`): Recall@1 rose from 0.7826 to **0.9710**, Recall@3/@5 to **1.0000**, MRR to **1.0000** — thresholds raised accordingly (`intelligence/evaluation/thresholds.json`).
  - The cosine-similarity floor (`RETRIEVAL_MIN_SIMILARITY`) was empirically calibrated at **0.70**, not the originally-planned 0.58 — real embedding scores showed adversarial queries that are topically on-topic (e.g. "homeopathic remedy for septic shock") scoring 0.65-0.70, overlapping with the low end of genuinely-relevant matches. The floor separates those cases from top-1 relevant matches (0.73+); detecting "this recommends a pseudo-scientific treatment" is intentionally left to the Citation Guard, not the retriever.
  - New matching-quality test suites: `tests/test_rag_pipeline.py` (fusion/threshold mechanics, synthetic vectors, no network) and `tests/test_embeddings_matching.py` (13 tests: specific lay-language, compound-query, near-duplicate disambiguation, and adversarial cases against the real committed artifact — skipped only when no artifact is built). Building and running these against real data caught and fixed two live bugs: an RRF tie-break that let a near-exact score tie override a correct embedding-model ranking, and an incorrect test assumption that all adversarial queries must return zero results (three of four are legitimately topically on-topic; only the fully unrelated case must return nothing).
  - New `GuidelineDocument` model (`data/schemas/__init__.py`) persists API-ingested documents via pgvector on Postgres (JSON on SQLite); retrieval scoring itself always runs against the in-memory vector store, not a live DB query.
  - Default `GEMINI_MODEL` changed from `gemini-2.5-flash` to `gemini-flash-latest` — the pinned 2.5 name is no longer available to new Gemini API keys; the alias tracks Google's current recommended flash model instead.
- RAG evaluation harness (`intelligence/evaluation/`) measuring Recall@k, MRR, Citation Precision, and Faithfulness against a 27-case golden dataset — see README § Evaluation.
- GitHub Actions CI (`.github/workflows/ci.yml`): lint (ruff), test + 87% coverage gate, eval regression gate, frontend build, and a security gate (`security`: gitleaks + bandit, blocking; `security-advisory`: pip-audit + npm audit, advisory).
- JWT secret fail-fast: `Settings` refuses to start in `staging`/`production` with a known-insecure or too-short `jwt_secret` (`platform/core/config.py`); new `environment` setting.
- Four Claude Code skills (`.claude/skills/`): `/eval`, `/add-guideline`, `/verify`, `/release-check`.
- Test suite expanded from 23 to 200+ tests (88%+ coverage).

## [0.1.0] — Initial release

- FastAPI backend + Next.js 14 frontend, local-first Ollama inference (`qwen3:8b` + `llava:7b`).
- Multi-agent LangGraph workflow (Evidence, Radiology, Lab, Drug Safety agents + coordinator) over FastMCP tool servers.
- Citation Guard anti-hallucination firewall, explainability trace, rule-based risk engine.
- JWT auth, per-user consultation history, PDF export, auto-generated clinical timeline.
