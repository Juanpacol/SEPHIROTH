# Changelog

All notable changes to this project are documented here. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Phase 0 — SDD foundation and tool-authorization hotfix

#### Security
- **Tool whitelists are now enforced at dispatch, not just at advertisement.** `MCPAgent.run()` previously handed the model `registry.execute` — the raw dispatcher, which checks only that a tool *exists*. An agent's `allowed_tools` merely filtered which schemas the model was *shown*, so a model naming a tool outside its scope (through hallucination, or prompt injection in clinical text) had it executed. `MCPRegistry.scoped_executor()` now binds the whitelist to dispatch and returns `{"error": "Tool not authorized for this agent: ..."}` as a tool *result*, so the model can recover rather than the run dying. Rolled out permissive-first: a full eval run and the whole suite produced zero `tool_authorization_denied` warnings, confirming no agent relied on the hole, before enforcement was switched on. `ENFORCE_TOOL_AUTHORIZATION=false` restores permissive behaviour for diagnosis. Locked by `tests/test_tool_authorization.py` (F-021).

#### Added
- **Spec-Driven Development system** (`docs/specs/`): `SPEC-000-spec-process.md` defines the spec template, the `Draft → Approved → Implemented → Superseded` lifecycle, and the rule that implementation may not begin before a spec is `Approved`. Specs are normative and versioned; `docs/01-architecture/` prose is descriptive and always cites its governing spec.
- **`src/sephiroth/contracts/`** — 23 Pydantic domain models (`RunState`, `ExecutionPlan`, `Claim`, `EvidenceRecord`, `AbstentionDecision`, `ExecutionTrace`, …) plus closed vocabularies for risk, lifecycle, verification status, failure taxonomy and abstention reasons. A leaf package by construction: it imports nothing else from `sephiroth`, so schema export and tests need no provider SDKs (`tests/test_package_layout.py` enforces this). Several models carry real invariants — `ExecutionPlan` rejects duplicate ids, dangling dependencies, self-dependencies and cycles (the expected failure modes of a hallucinated LLM plan); `AbstentionDecision` cannot record a decline without a reason; `Span` allow-lists its attributes so clinical content cannot reach a trace (F-020, F-043).
- **Contract drift gate**: `scripts/export_contracts.py` writes each model's JSON Schema to `docs/specs/contracts/`, and `tests/test_contracts_schema.py` fails CI when code and committed schema disagree. This is what makes the specification binding rather than decorative.
- **`docs/00-migration-charter.md`** — the standing contract for the migration: the four **frozen external contracts** (SSE event shapes, `_persist` state shape, `ConsultResponse`, derived `explanation`), the strangler-fig shim rules and deletion schedule, coverage-gate mechanics, and the phase dependency graph.
- **`tests/test_sse_contract.py`** — the keystone characterization test, and a permanent one. Locks the wire contract the frontend's hand-rolled SSE parser depends on: event ordering, the underscore/hyphen agent-name split between `routing` and `agent_completed`, `result` stripped from `agent_completed` but retained in `final` (citation auditing needs it), the frozen `citation_report` keys, 280-char summary truncation, and `data: {json}\n\n` framing. It also asserts the streamed `explanation` matches the one rebuilt on read, which is what keeps history and PDF export consistent with what the user saw.
- **`tests/test_prompt_contract.py`** — guards a silent-failure mode: `FakeLLMClient` selects a script by substring-matching the system prompt, so rewording a role prompt would make dozens of tests fall through to `default_script` and *still pass while asserting nothing*.
- **Documentation gates**: `scripts/docs_check.py` (stdlib + PyYAML, six checks) verifies spec front-matter, that every acceptance criterion of an `Implemented` spec exists in the test tree, that Mermaid source lives only in `docs/09-diagrams/`, that every `project-state.yaml` component path resolves, that feature references resolve, and that relative links work. Wired as a new parallel `docs` CI job and also run from the suite via `tests/test_docs_gates.py`.
- `docs/project-state.yaml`, `docs/03-features/feature-registry.md` (43 features), and `docs/04-development/{setup,testing}.md`, seeded from a full repository audit.
- `docs/09-diagrams/architecture/D1-high-level.md` — target architecture, explicitly marked `status: target` so aspiration is never mistaken for reality.
- `docs/08-decisions/ADR-001-remove-langgraph.md` — records the decision to replace LangGraph with a purpose-built executor in Phase 3, reversing the transformation plan's original assumption. The graph compiles with no checkpointer and its fan-out requires enumerating destinations at compile time, which a dynamic planner cannot satisfy.
- Registered pytest markers (`spec`, `contract`, `integration`, `legacy`) and `tests/test_coverage_config.py`, which fails if a `src/sephiroth` package is missing from `coverage.run.source` — otherwise new code is silently invisible to the 87% gate.

#### Changed
- The project is now an installable package (`[build-system]` + `[project]` + explicit `packages.find.where = ["src"]`). `pip install -e .` added to the `test`, `eval`, and `docs` CI jobs and to the `Dockerfile`, so `import sephiroth` resolves identically under pytest, uvicorn, `python -m`, and Docker — extending `pythonpath` would have covered only pytest, silently diverging CI from production.

#### Removed
- `docs/INTEGRATION_GUIDE.md` — it documented an `agents/graph/` package that never existed, LlamaIndex which was never used, and three example files not on disk. Replaced by `docs/04-development/setup.md`, verified against the code.
- The vestigial `AgentState` dataclass in `intelligence/agents/__init__.py`, deleted alongside its only referent (the guide above). Superseded by `sephiroth.contracts.RunState`.

#### Fixed
- `README.md` claimed "Gemini 2.5 Flash"; the actual default is `gemini-flash-latest`.
- `CLAUDE.md`'s "Add a New Agent" example used `system_prompt`; the real attribute is `role_prompt`.

### Added
- **Alembic migrations for Postgres** (`migrations/`): `platform/core/db.py::init_db()` now runs `alembic upgrade head` on boot (Postgres only — idempotent, no-op once current) instead of `Base.metadata.create_all()`, which could only ever add missing tables/columns, never handle a real `ALTER`/`DROP`/data migration. SQLite (`tests/conftest.py::db_session`) is unaffected — it still calls `create_all()` directly, the accepted pattern for an ephemeral per-test schema. New `tests/test_alembic_migration.py` fails if a model changes without a matching migration (self-skips without a local Postgres, never blocks CI). Supabase was **stamped** at the baseline revision (`alembic stamp head`) rather than migrated — its schema already matched exactly, so this recorded "already current" without running any DDL against the 14 real patients already there.
- **Optional Groq fallback for the LLM layer** (`intelligence/llm/groq_client.py`, `intelligence/llm/fallback_client.py`): when `GROQ_API_KEY` is set, `get_llm_client()` returns a `FallbackLLMClient` that tries Gemini first for `chat()`/`generate_json()` and falls through to Groq (`llama-3.3-70b-versatile` by default) on any failure — rate limit, daily quota exhaustion, or outage. Mitigates the real free-tier daily-quota constraint discovered while regenerating the eval baseline (see below). Vision and embeddings are Gemini-only (no fallback); unset `GROQ_API_KEY`, behavior is unchanged from a bare `GeminiClient`.

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
