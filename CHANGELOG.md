# Changelog

All notable changes to this project are documented here. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Phase 5, Part 2 — Recovery engine + lifecycle state machine

#### Added
- **`src/sephiroth/runtime/recovery.py`** (`docs/specs/SPEC-007-recovery.md`, executes `ADR-007`): `classify(exc, component, step_id, attempt) -> Failure` maps an exception to a `FailureCategory` (`MODEL` for `LLMUnavailableError`, `AGENT` for anything else); `decide_recovery(failure, attempt, max_attempts) -> RecoveryActionType` returns `RETRY` for a transient category (`MODEL`/`TOOL`) with attempts remaining, `ABSTAIN` otherwise.
- `src/sephiroth/runtime/executor.py::_run_specialist` now wraps each specialist's turn in a bounded retry loop (`MAX_AGENT_ATTEMPTS=2`, matching `PlanStep.max_attempts`'s default). An exhausted specialist no longer raises past itself — it returns an `AgentResult` with empty content, and the consultation completes using the other specialists' output plus the coordinator's synthesis.
- `RunState.lifecycle`/`.failures`/`.retries`/`.recovery_actions` (typed contracts since Phase 0, never populated) are filled for the first time: each capability moves through `SELECTED → EXECUTING → (COMPLETED | RECOVERING → COMPLETED | FAILED)`.
- Tests: `tests/test_runtime_recovery.py` (unit table for `classify`/`decide_recovery`, no LLM); `tests/test_runtime_executor.py::test_transient_model_failure_retries_then_succeeds` (new); `test_one_specialist_raising_does_not_abort_the_others` rewritten to assert the new behaviour instead of clean propagation.

#### Changed
- **Behaviour change, deliberate**: before this cycle, an unhandled exception from any specialist aborted the entire consultation — this was documented in the old test's own docstring as a tracked gap, not a guarantee. It's now closed: a non-transient (`AGENT`-category) failure abstains immediately; a transient (`MODEL`-category) failure gets one retry before abstaining.

#### Known deviations (`SPEC-007` §4)
- **`FALLBACK` and `REPLAN` are not implemented** (NG-1, NG-2) — one agent per capability today (no alternative to fall back to); no dynamic planner yet to replan against (`SPEC-008`, still pending).
- **The coordinator's own call is not covered by this recovery loop** (NG-3) — it's the final synthesis step with nothing to substitute for it; a coordinator failure still propagates unchanged, exactly as before this spec.
- **`TOOL` category has no real trigger yet** (NG-4) — included in `decide_recovery`'s transient set for symmetry with `MODEL`, but `ToolRuntime.execute` already degrades a timeout to an error result rather than raising, so this branch is currently unreachable dead code.

#### Verification
- `pytest --cov`: 519 passed, 1 skipped, 93.17% total coverage; `recovery.py` and `executor.py` both 100%.
- `intelligence.evaluation.run --mode ci`: PASS, all 6 metrics unchanged from Part 1.
- `docs_check.py`: OK, all AC-007-0{1..5} anchors resolved.
- `export_contracts.py --check`: OK, 24 schemas — no contract shape change (reuses existing `Failure`/`RecoveryAction`/enums).
- `bandit`: 0 High severity/confidence findings.
- Docker build + smoke test verified from a clean `git worktree`.

### Phase 5, Part 1 — Telemetry (trace-based observability)

#### Added
- **`src/sephiroth/telemetry/`** (`docs/specs/SPEC-006-telemetry.md`, executes `ADR-009`): `build_trace(state) -> ExecutionTrace` projects a fully-populated `RunState` into the persisted, replayable trace contract that's existed since Phase 0 but had nothing emitting into it until now. `traced_span(state, kind, name, **attrs)` records real spans for two of `ADR-009`'s four named seams — `Executor.step` (one per specialist/coordinator turn) and `Verifier.check` (the claim-verification/abstention pass) — timed with `time.monotonic()`, redacted via the pre-existing attribute allow-list (dropped, not raised, on a disallowed key — instrumentation must never break a run).
- `RunState` gains one additive field, `spans: list[Span] = []`.
- New setting `enable_tracing` (default `True`, `platform/core/config.py`) — when `False`, `traced_span` is a pure no-op; a run must produce an identical result with tracing on vs. off apart from the trace itself (ADR-009's H6 requirement, now covered by a real test).
- Five new nullable `Consultation` columns: `trace` (JSON) plus the four indexed scalars `ADR-009` names — `trace_id`, `risk_level`, `abstained`, `supported_claim_ratio`. New migration `233988357f83`.
- `ConsultResponse`, the SSE `final` event, and `/history` all gain `trace` as an additive, optional field.
- Tests: `tests/test_telemetry_{span,build_trace}.py`, plus a new H6 parity test in `tests/test_runtime_executor.py`.

#### Known deviations (`SPEC-006` §4, §10)
- **`ModelProvider.chat` and `ToolRuntime.execute` are not independently instrumented this cycle** (NG-1) — `ToolRuntime` is a shared singleton with no per-request state, and threading one through would change `ToolExecutor`'s `Callable` signature that `FakeLLMClient` and every `scoped_executor()` call site already depend on; `Agent.run()` makes exactly one `chat()` call per turn today, so the `Executor.step` span already bounds it as tightly as a nested span would.
- **Token/cost accounting is a placeholder** (NG-2) — `ChatResult`/`AgentResult` don't carry usage metadata from the model clients yet.
- **No pluggable Tracer/OTel backend** (NG-3) — premature with a single consumer (the new Postgres columns); `opentelemetry-api` is already present as a transitive dependency but not wired to anything.
- **Friction found during implementation**: `VerificationReport.supported_claim_ratio` is a Pydantic `@property`, not a `computed_field` — it doesn't appear in `model_dump()`'s output. `_persist` recomputes it directly from the already-serialized `verification_report`'s claim statuses instead of reading a field that would have silently always been `None`.

### DEBT-010 — remove `intelligence/agents/{base,workflow}.py` shims

#### Changed
- **Closed `DEBT-010`**: `intelligence/agents/{base,workflow}.py` (Phase 3 re-export shims) are deleted, one phase later than the migration charter originally scheduled (Phase 4's approved scope was Context Engine + Verification & Safety, not shim cleanup). All call sites — `platform/api/routers/agents.py`, `tests/{test_workflow,test_sse_contract}.py`, `examples/agents_example.py` — retargeted directly onto `sephiroth.runtime`.
- `tests/test_agent_registry.py::test_workflow_shim_run_consultation_is_the_real_executor` deleted (nothing left to check identity against). `tests/test_workflow.py` kept permanently as the executor's characterization test, with its docstring updated to reflect that it no longer runs through a shim.
- `docs/specs/SPEC-003-agent-runtime.md` bumped to v1.1.0, retiring the acceptance criteria that verified the deleted shim's parity/identity.
- Docs hygiene: `docs/08-decisions/ADR-007-explicit-recovery.md`'s status line incorrectly said "executed phase 3" — the recovery engine was never built (confirmed: no `src/sephiroth/runtime/recovery.py` exists); corrected with an explicit note. `docs/project-state.yaml`'s `gaps` list re-tagged: recovery engine and the dynamic planner move to phase 5 (phase 4 is done, and there's no phase 6); the confidence/context-engine tuning gaps move to no fixed phase, since they require a live `GEMINI_API_KEY` run the assistant cannot perform, not a build cycle.

### Phase 4a — Context Engine

#### Added
- **`src/sephiroth/context/`** (`docs/specs/SPEC-005-context-engine.md`, `ADR-011`): per-agent context views (`views.py::context_for_agent`, projecting `RunContext` down to only the fields an `AgentCapability.context_fields` declares — additive `[]` default means "every field"), lexical MMR reranking over `RAGPipeline`'s fused results (`rerank.py::mmr_rerank`, token-overlap similarity so it works identically with or without an embedding provider configured — no new dependency), per-patient consultation memory (`memory.py::recent_consultation_summaries`, called from the API router so the executor stays free of any DB dependency, injected into `context["recent_consultations"]` and seen only by the coordinator), and character-budget truncation (`budget.py::truncate`, bounding the previously-unbounded concatenation of up to 4 specialist answers feeding the coordinator prompt).
- **`sephiroth.contracts.context.RunContext`** — new contract typing the context dict (`medications`, `lab_results`, `image_path`, `conditions`, `history`, `recent_consultations`); `AgentCapability` gains `context_fields: list[str] = []` (additive, MINOR schema bump).
- New setting `max_context_chars` (default 4000, `platform/core/config.py`).
- Tests: `tests/test_context_{views,rerank,memory,budget}.py`, plus an end-to-end integration test in `test_api_agents.py` confirming `recent_consultations` reaches the coordinator but not the evidence specialist.

#### Changed
- **`src/sephiroth/runtime/executor.py`** now builds a `RunContext` once per consultation and calls `context_for_agent` before every specialist/coordinator call — switched straight to enforcing (not staged as a separate permissive-logging commit) because the full pre-existing test suite, including the three frozen contract files, served as the verification that no agent depended on a field outside its declared scope. See `ADR-011` for why this adapts the migration charter's two-commit rollout requirement to an environment with no live-model access.
- **`data/rag/__init__.py::RAGPipeline.retrieve`** reranks and content-truncates its results before returning (`_finalize`) — the first time `data/` has imported from `src/sephiroth/`, noted in `SPEC-005` §10 as a new (not prohibited) import direction.
- `tests/test_rag_pipeline.py::test_retrieve_ranks_more_relevant_document_first` relaxed to check only that the single most relevant document ranks first — MMR trades relevance-order for diversity among the rest.

#### Known deviations (`SPEC-005` §4, §11; `ADR-011`)
- **Memory is scoped to per-patient consultation recall, not a generic multi-turn/session abstraction** — there is no validated product need for conversational memory today (confirmed by direct inspection: no `session_id` anywhere, the frontend never replays prior turns). Building one speculatively was rejected as premature complexity.
- **`max_context_chars` and MMR's `lambda_mult` are untuned placeholders**, same status as Phase 4b's confidence/abstention constants.

### Abstention threshold tuning — wiring (no data-driven calibration yet)

#### Added
- **`intelligence/evaluation/abstention_replay.py`**: replays `src/sephiroth/verification`/`safety` over committed eval transcripts (same pattern as `faithfulness.py::judge_llm` — requires a live model, so it only runs in `--mode full --record` and is read from the committed `results/latest.json` snapshot in `--mode ci`). `compute_abstention_metrics` is a pure, deterministic function computing `abstention_recall`/`abstention_precision` against the golden dataset's 4 `adversarial-negative` (`expects_abstention`) cases — the only branch of `decide()` (`INSUFFICIENT_EVIDENCE`) the dataset currently exercises; there are no cases yet for `CONFLICTING_EVIDENCE` or `UNSUPPORTED_HIGH_RISK_CLAIM`.
- `src/sephiroth/runtime/executor.py::_to_tool_calls` renamed to public `to_tool_calls` and exported, so the eval harness can reuse the same transcript→`ToolCall` conversion the executor uses live, without duplicating it.
- `tests/test_abstention_replay.py`.

#### Known deviation
- **`abstention_recall` is deliberately not added to `thresholds.json`** despite this session's plan calling for gating it at 1.0 — the committed `results/latest.json` snapshot has no abstention data yet (regenerating it requires a live Gemini key this session doesn't have), and gating on an absent value would hard-fail every CI run immediately. Left reported-but-ungated, matching the existing precedent of `citation_recall`/`fabrication_rate_on_adversarial`. Real calibration is a follow-up once the user runs `--mode full --record` with their own key.

### Phase 4b — Verification & Safety

#### Added
- **`src/sephiroth/verification/`** (`docs/specs/SPEC-004-verification-safety.md`): claim-level content verification, replacing the assumption that citation-provenance checking alone was sufficient. `claims.py::extract_claims` decomposes a coordinator answer into `Claim`s via one `generate_json` call; `evidence.py::harvest_evidence` normalizes tool results into `EvidenceRecord`s (real passage content from `search_clinical_guidelines`, metadata-only from `search_pubmed` — a documented limitation, not a bug); `verify.py::verify_claims` judges every claim against evidence in a single batched `generate_json` call (not one per claim — ADR-006's dominant-cost concern), with a deterministic token-overlap rule that downgrades a `supported` verdict lacking real overlap with its cited evidence to `partially_supported` (never trust the judge alone); `confidence.py::compute_confidence` is a pure, deterministic function of `supported_claim_ratio`, citation-fabrication rate, and capped tool failures — never LLM self-reported (ADR-008).
- **`src/sephiroth/safety/`**: `abstention.py::decide` gates every consultation into `answer`/`partial`/`abstain`, with `has_unsupported_high_risk_claim` (and any contradiction, or a policy-restriction flag) overriding any confidence threshold — a high-confidence-looking answer asserting one unsupported high-risk claim must still abstain. `output_safety.py::check_input` is a minimal, deliberately narrow prompt-injection heuristic on the input query (F-041); PHI redaction, output-side toxicity/jailbreak classifiers, and rate limiting are explicitly deferred (SPEC-004 NG-2) — the product exists to show a clinician their own patient's clinical content back to them, so redacting it would break the product.
- Two new `Consultation` columns, `verification_report`/`abstention` (JSON, default `{}`), mirroring the existing `citation_report` pattern; new Alembic migration `eef6397408fa` (hand-corrected from autogenerate's default `NOT NULL` with no default, which would have failed against any pre-existing row, to `server_default='{}'`).
- `ConsultResponse`, the SSE `final` event, and `/history` all gain `verification_report`/`abstention` as additive, optional fields — the five frozen SSE events keep identical shape/casing otherwise.
- Tests: `tests/test_verification_{claims,evidence,verify,confidence}.py`, `tests/test_safety_{abstention,output_safety}.py`, plus new RunState/abstention-path cases in `tests/test_runtime_executor.py`.

#### Changed
- **`src/sephiroth/runtime/executor.py` adopts `RunState` as its real internal state**, resolving the deferral documented in `SPEC-003` §10. The one friction point flagged there — `ToolCall.tool` vs. the frozen wire's `name` — is resolved by a single projection function (`_tool_call_wire`) at the SSE-yield/return boundary; nothing else in the wire shape changes.
- `citation_guard.py` is unchanged but recomposed: it now runs as a fast pre-filter feeding the new verifier (its `fabrication_rate` is one input to `compute_confidence`), not the terminal check, per ADR-006's own framing.
- `tests/test_sse_contract.py` and `tests/test_api_agents.py` gained additive-only assertions for the two new keys; no existing assertion changed.

#### Known deviations (documented in `docs/specs/SPEC-004-verification-safety.md` §4, §10, and `docs/00-migration-charter.md`'s shim schedule)
- **`intelligence/agents/citation_guard.py` is *not* shimmed this phase**, unlike the charter's original Phase-4 shim schedule for `{citation_guard,explainability,risk_engine}.py`. It stays real, unmodified implementation, composed ahead of the new verifier — shimming/deleting it is deferred until the new verifier has demonstrably absorbed its role in production evals.
- Confidence weights and abstention thresholds (`FABRICATION_WEIGHT`, `TOOL_FAILURE_WEIGHT`, `ABSTAIN_THRESHOLD`, `PARTIAL_THRESHOLD`) are explicit placeholders — ADR-008 calls tuning them "itself an experiment," not something to guess once and freeze.
- Context Engine (Phase 4a — reranking, memory, compression, token budgeting) is out of scope; this phase covers Verification & Safety (4b) only.

### DEBT-009 — remove `intelligence/mcp/registry.py` shim

#### Changed
- **Closed `DEBT-009`**: `intelligence/mcp/registry.py` (the Phase 2 re-export shim over `sephiroth.tools`) is deleted, one phase later than the migration charter originally scheduled (Phase 3's approved scope covered Agent Runtime + `DEBT-008` and didn't include this). All call sites — `platform/api/routers/{medical,rag,patients}.py`, `tests/{test_mcp,test_tool_authorization}.py`, `examples/{tools_example,imaging_example}.py` — retargeted directly onto `sephiroth.tools.get_tool_runtime`/`ToolRuntime`.
- `intelligence/mcp/__init__.py`'s PEP 562 `__getattr__` (added in Phase 2 to break a circular import between `intelligence.mcp` and `sephiroth.tools`) removed — no longer needed once nothing requests `MCPRegistry`/`get_registry` from that package; it now just imports the five FastMCP server submodules.
- `tests/test_mcp_shims.py` deleted (nothing left to test); `docs/specs/SPEC-002-tool-runtime.md` bumped to v1.2.0, retiring the two acceptance criteria that verified the deleted shim's identity and the legacy test modules passing unmodified against it.

### Phase 3 — Agent Runtime + DEBT-008 closure

#### Added
- **`src/sephiroth/runtime/`** — the purpose-built executor replacing the LangGraph-compiled graph (`ADR-001`, `docs/specs/SPEC-003-agent-runtime.md`): `registry.py` (5 `AgentCapability` records — radiology, laboratory, drug-safety, evidence, coordinator — with `role_prompt` copied byte-for-byte from the pre-Phase-3 hardcoded classes), `agent.py` (`Agent`, constructed from a capability + `ModelProvider` instead of subclassing), `analyzer.py`/`planner.py` (`route_specialists` relocated verbatim), `router.py` (capability lookup), and `executor.py` (`run_consultation`/`stream_consultation`: fan-out with `asyncio.gather`/`asyncio.as_completed`, merge, coordinate — same shape as the old graph, same 5 frozen SSE events, unchanged casing/field names).
- **`role_prompt: str = ""`** added to `sephiroth.contracts.capability.AgentCapability` (additive, MINOR schema bump) so the agent registry can hold what used to be five hardcoded class attributes as data.
- `tests/test_agent_registry.py`, `tests/test_runtime_executor.py`, `tests/test_no_langgraph.py`.
- `docs/specs/SPEC-003-agent-runtime.md` (`Implemented`, v1.0.0).

#### Changed
- `intelligence/agents/{workflow,base}.py` are now re-export shims over `src/sephiroth/runtime/`; deleted in Phase 4. `intelligence/agents/__init__.py`'s five agent classes (`RadiologyAgent`, etc.) are now thin `Agent` subclass wrappers constructed from the registry's capability records, not independent classes with their own hardcoded prompts.
- `tests/test_prompt_contract.py` rewritten to read `role_prompt`/`id` from `sephiroth.runtime.registry.AGENTS` (an `AgentCapability` instance attribute) instead of `agent_cls.role_prompt`/`agent_cls.name` as class attributes, which no longer exist now that `Agent.name` is an instance property.
- **`langgraph` removed from `requirements.txt` and the dependency tree entirely**, in this same phase rather than a deferred "3b" — see `ADR-001`'s revised Migration section. The three frozen parity test files (`test_workflow.py`, `test_sse_contract.py`, `test_api_agents.py`) passing unmodified against the new executor serves as the parity proof; no side-by-side comparison harness was built.
- **Closed `DEBT-008`**: `intelligence/llm/*` (the Phase 1 shim, originally scheduled for Phase 2 deletion, deferred because Phase 2's approved scope didn't include it) is deleted in this phase — one phase later than scheduled, not further, per the migration charter's rule that a shim surviving two phases becomes permanent. All ~16 call sites (`intelligence/agents/{workflow,base}.py`, `intelligence/mcp/vision_server.py`, `intelligence/nlp/timeline_extractor.py`, `intelligence/evaluation/run.py`, `real_data/notes/generate_notes.py`, `platform/api/routers/{agents,dashboard,patients}.py`, `examples/{agents_example,real_data_example}.py`) retargeted to `sephiroth.models`. `tests/test_llm_shims.py` deleted (nothing left to test). `docs/specs/SPEC-001-model-provider.md` bumped to v1.2.0, retiring the acceptance criterion that verified the deleted shim's import identity.

#### Known deviations (documented in `docs/specs/SPEC-003-agent-runtime.md` §10)
- **`sephiroth.contracts.RunState`/`ToolCall`/`AgentResult` not adopted as the executor's internal state.** Those strict (`extra="forbid"`) contracts already existed from Phase 0, but `ToolCall`'s fields (`id, tool, agent, arguments, result, ok, latency_ms, timestamp`) don't match the frozen wire shape (`agent, name, arguments, result`) — adopting them now would mean building instances only to immediately flatten them back for the wire. The executor's internal state stays a plain dict shaped like the pre-Phase-3 `WorkflowState`; `RunState` gets adopted in the phase that actually accumulates evidence/claims/safety data.
- **New debt opened, `DEBT-009`**: `intelligence/mcp/registry.py` (the Phase 2 shim) was scheduled for Phase 3 deletion per the charter but fell outside this phase's approved scope (Agent Runtime + DEBT-008). Tracked for Phase 4, same pattern as `DEBT-008`.

### Phase 2 — Tool Runtime

#### Security
- **Closed DEBT-004**: `platform/api/routers/medical.py` (6 endpoints) and `rag.py` (2 endpoints) called `registry.execute(...)` directly from FastAPI routes with zero authentication — anyone could trigger image analysis, entity extraction, drug-interaction checks, or a real PubMed network call, at will. Every endpoint in both routers now requires `Depends(get_current_user)`, matching every other endpoint that touches clinical data or tools.

#### Added
- **`sephiroth.tools.ToolRuntime`** — the MCP dispatcher relocated from `intelligence/mcp/registry.py::MCPRegistry`. `scoped_executor()`'s dispatch-time whitelist enforcement (Phase 0) is unchanged; `execute()` now bounds every call to `tool_call_timeout_seconds` (new setting, default 30s) so a hang in `search_pubmed` (network) or `describe_medical_image` (a model call) degrades to an error result instead of blocking a consultation indefinitely.
- **`tags_for(tool_name)`** — capability tags for each of the 8 tools (`TOOL_CAPABILITIES` in `sephiroth/tools/servers.py`), for the Phase 3 router to consume. A hand-authored literal dict, not a YAML loader — that generality belongs to the Phase 3 agent registry.
- `tests/test_tool_runtime.py`, `tests/test_mcp_shims.py`.

#### Changed
- `intelligence/mcp/registry.py` is now a re-export shim over `sephiroth.tools`; deleted in Phase 3. Only `registry.py` is shimmed — the five FastMCP servers remain real implementation.
- `intelligence/mcp/__init__.py` resolves `MCPRegistry`/`get_registry` lazily via `__getattr__` (PEP 562) rather than importing them eagerly. `sephiroth.tools.servers` imports the five server objects back from this package, and the shim imports `sephiroth.tools` — an eager import created a genuine bidirectional circular dependency between the two packages, caught immediately by running the new tests. The shim module itself stays a pure two-line re-export.
- `tests/test_medical_router.py` and the RAG search test in `tests/test_api_patients_rag.py` updated to register/authenticate first, mirroring the pattern already used by `test_api_agents.py`.

#### Known deviation from the migration charter
- `docs/00-migration-charter.md`'s original shim schedule had `intelligence/llm/*` (created Phase 1) deleted in Phase 2. This phase's approved scope was Tool Runtime only; deleting the LLM shims would have meant rewriting imports across ~16 unrelated files. Deferred to Phase 3 and tracked as `DEBT-008` — must not slip further, per the charter's own rule that a shim surviving two phases becomes permanent.

### Phase 1 — ModelProvider abstraction

#### Fixed
- **`.gitignore`'s `models/` rule silently excluded all of `src/sephiroth/models/`** from the Phase 1 commit — the rule (meant for future model-weight downloads) matched any directory named `models` at any depth. `git add -A` skipped all seven files; the pushed commit contained only the shim changes that import from them, so a fresh checkout was broken. Every verification that session passed anyway because git leaves ignored/untracked files on disk across branch switches. Anchored the rule to the repo root (`/models/`) and added the missing files as a follow-up commit, verified this time from a clean `git worktree`, not the working directory.

#### Added
- **`sephiroth.models.ModelProvider`** — a `@runtime_checkable` Protocol every LLM backend now satisfies structurally: `model`/`supports_vision`/`supports_tools` attributes, `chat`/`generate_json`/`describe_image`/`health` methods. `chat`'s parameters after `messages` are keyword-only and `generate_json`'s first two stay positional-or-keyword in order — matching how every call site in the repo already invokes them (`faithfulness.py` positionally, `timeline_extractor.py` by keyword). `GeminiClient`, `GroqClient`, `FallbackLLMClient`, and the test double `FakeLLMClient` all satisfy it (F-022).
- **`llm_provider` setting** (`"gemini"` default, `"groq"`): `get_llm_client()` now picks its primary from config instead of inferring it from which API key happens to be set. `llm_provider="groq"` returns a bare `GroqClient` — not a client wrapping the other way around, since Groq has no vision endpoint (F-023).
- **Shared rate limiting and backoff** (`sephiroth.models._throttle`): `RateLimiter` (the exact sliding-window logic that lived only in `GeminiClient`) and `backoff_delay` (the exact `min(2**attempt, cap) + jitter` formula, parameterized by `cap` since Gemini used 30 and Groq used 10). `GeminiClient.describe_image` no longer duplicates its own retry loop — it now reuses `_generate` with an explicit `model` override.
- Three new settings, all defaulting to the pre-Phase-1 behavior: `groq_timeout_seconds=60`, `groq_max_output_tokens=2048`, `groq_rpm_limit=0` (disables throttling — Groq had none before).
- `tests/test_model_provider_protocol.py`, `tests/test_throttle.py`, `tests/test_llm_shims.py`.

#### Changed
- `intelligence/llm/{__init__,gemini_client,groq_client,fallback_client,factory}.py` are now re-export shims over `src/sephiroth/models/`; deleted in Phase 2 per the migration charter's shim schedule. All four pre-existing LLM test modules pass with zero behavioral change against the shims.
- `tests/conftest.py::patch_llm_factory`, `tests/test_llm_factory.py`, `tests/test_api_agents.py`, and `tests/test_api_patients_rag.py` retarget their `factory_module` import from `intelligence.llm.factory` to `sephiroth.models.factory` — a two-line import change in each, not a behavioral one. Necessary because these tests patch the factory's module-level `_client`/`settings` globals directly, and `get_llm_client()` reads those globals from wherever it is *defined* (now `sephiroth.models.factory`), not wherever it was imported from; patching the shim's copy of the binding would have silently done nothing. Documented as a v1.1.0 correction to `SPEC-001` §10.
- `docs/specs/SPEC-001-model-provider.md` → `Implemented` (v1.1.0).

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
