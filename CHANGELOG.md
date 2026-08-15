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
- **Hybrid RAG retrieval**: `data/rag/RAGPipeline.retrieve()` now fuses keyword-overlap scoring with dense Gemini embeddings (`gemini-embedding-001`) via Reciprocal Rank Fusion, targeting the paraphrase-recall gap in the eval harness. New `data/embeddings/` (provider protocol, live `GeminiEmbeddingProvider`, `CachedEmbeddingProvider` over a committed, hashed artifact) and `data/vectors/` (`InMemoryVectorStore`, cosine similarity). Fully backward-compatible: `RAGPipeline()` with no configuration stays exactly keyword-only, and any embedding failure falls back silently. A cosine-similarity floor (`RETRIEVAL_MIN_SIMILARITY`) keeps adversarial/off-topic queries returning zero results. `--mode ci`'s staleness gate now also checks the embeddings artifact's corpus hash.
  - New matching-quality test suites: `tests/test_rag_pipeline.py` (fusion/threshold mechanics, synthetic vectors, no network) and `tests/test_embeddings_matching.py` (specific lay-language, compound-query, and adversarial-abstention cases against the real committed artifact — skipped until the artifact is built with a live API key via `python -m data.embeddings.build_artifact`).
  - New `GuidelineDocument` model (`data/schemas/__init__.py`) persists API-ingested documents via pgvector on Postgres (JSON on SQLite); retrieval scoring itself always runs against the in-memory vector store, not a live DB query.
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
