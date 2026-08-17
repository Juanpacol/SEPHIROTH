# Glossary

Terms with a **narrower** meaning in SEPHIROTH than in general usage. A spec may
narrow a term further in its own §5.

## Runtime

| Term | Meaning here |
|---|---|
| **Runtime** | The execution layer between an application and the models. Domain-agnostic; the clinical parts live in its configuration. |
| **Agent** | A capability declaration plus a role prompt plus a tool scope. Data, not a class — after Phase 3. |
| **Capability** | A named skill an agent declares (`medication_interaction`). Routing matches required capabilities against declared ones. |
| **Plan** | A DAG of steps. The static planner emits a degenerate plan (no dependencies, one iteration); the dynamic planner emits a real one. |
| **Router** | Resolves required capabilities to concrete agents. Distinct from the planner, which decides *what* must happen. |
| **Executor** | Runs a plan: schedules waves, merges results deterministically, isolates failures. |
| **Wave** | A set of plan steps with satisfied dependencies, runnable concurrently. |
| **Lifecycle** | The states an agent passes through (`REGISTERED` → … → `COMPLETED`), including the failure branch. |

## Evidence and verification

| Term | Meaning here |
|---|---|
| **Evidence record** | One retrieved passage, normalised across retrieval strategies, immutable once written. |
| **Claim** | One independently verifiable assertion extracted from an answer. Not a sentence — a sentence may hold several. |
| **Verification status** | `SUPPORTED` / `PARTIALLY_SUPPORTED` / `UNSUPPORTED` / `CONTRADICTED` / `UNKNOWN`. |
| **Citation guard** | The existing check that a citation *label* corresponds to real tool output. Weaker than claim verification: it checks provenance, not content. |
| **Contradiction** | A conflict between two claims, or between a claim and its evidence. |
| **Grounding** | The property that a claim is supported by evidence actually retrieved during *this* run. |

## Safety

| Term | Meaning here |
|---|---|
| **Abstention** | Deliberately declining to answer confidently, with a recorded reason. An output, not a failure. |
| **Safety engine** | Evaluates the *model's output* for risk. Distinct from the risk engine. |
| **Risk engine** | Evaluates *patient data* against clinical thresholds. Predates the safety engine and is unrelated to output safety. |
| **Tool scope** | The set of tools an agent may invoke, enforced at dispatch. |
| **HITL** | Human-in-the-loop: a high-risk result routed for review before release. |

## Observability and evaluation

| Term | Meaning here |
|---|---|
| **Execution trace** | The complete, replayable record of one run. The unit of evaluation. |
| **Span** | One instrumented interval within a trace. Attributes are allow-listed; clinical content never enters one. |
| **Failure taxonomy** | The closed set of failure categories, so failures aggregate by component. |
| **Ablation** | Running the system with one component disabled, to isolate its contribution. |
| **Baseline** | A deliberately simpler architecture (direct LLM, LLM+RAG, static multi-agent) run on the same benchmark. |

## Process

| Term | Meaning here |
|---|---|
| **Spec** | A normative, versioned document in `docs/specs/`. Frozen at `Approved`. |
| **Guide** | Descriptive prose in `docs/01-architecture/`. Always mutable, always cites its spec. |
| **Acceptance criterion (AC)** | A normative statement written so a test can assert it. If it cannot be asserted, it is a Behaviour, not an AC. |
| **Strangler fig** | Migrating by growing a new tree beside the old one and shrinking the old one to re-export shims, rather than rewriting. |
| **Shim** | A module whose entire body re-exports from its replacement. If it contains an `if`, it is not a shim. |
| **Frozen contract** | An externally-observable interface that cannot change without a coordinated change on the other side. |
