# Roadmap

Two efforts, deliberately sequential. **A** builds the runtime; **B** measures
it. B cannot start early because there is nothing to measure until the
mechanisms exist.

## A — Architecture (this plan)

| Phase | Delivers | Gate |
|---|---|---|
| **0** | SDD system, domain contracts, characterization tests, tool-authorization hotfix | Suite green, contracts schema-locked, wire contract pinned |
| **1** | `ModelProvider` interface; Gemini/Groq retrofitted; config-driven selection | Existing LLM tests pass unmodified against shims |
| **2** | Tool runtime: capability metadata, permissions, timeout/retry/fallback | Adversarial authorization tests; prompt-summary snapshot unchanged |
| **3a** | Analyzer → Planner → Router → Executor, **reproducing current behaviour exactly** | `test_runtime_parity.py`: deep equality vs the old graph |
| **3b** | Dynamic LLM planner; LangGraph removed | Both planners green; no `langgraph` import remains |
| **4** | Context engine; claim verification; conflict detection; confidence; abstention; safety engine | Citation/risk/PDF suites pass unmodified |
| **5** | Execution traces; span redaction; shim removal; coverage ratchet | Nested traces; no PHI in spans; `intelligence/` shims gone |

**Invariant across every phase:** the clinical application never breaks (R-008).
The three non-negotiable gates are the SSE contract test, the evaluation job,
and the Docker smoke test.

## B — Research (separate plan)

| Stage | Delivers |
|---|---|
| **6** | Benchmark expanded to 200–500 cases across 8 categories, versioned |
| **7** | Baselines A (direct LLM), B (LLM+RAG), C (static multi-agent), D (SEPHIROTH) |
| **8** | Ablations: full system minus routing / verification / recovery / abstention / hybrid retrieval / safety |
| **9** | Model-agnostic matrix: same benchmark across providers |
| **10** | Failure analysis, statistics, thesis chapters |

## Why this order

Each architecture phase unblocks the next:

- **1 before everything** — every agent takes a client as its only constructor
  argument, so an unstable model interface would force rewriting agent code twice.
- **2 before 3** — the executor must hand the model an *authorised* tool
  executor; building it first and securing it later means changing it twice.
- **3 before 4** — verification can only become a pluggable stage once something
  owns final-state assembly. Today that owner is a coordinator node body.
- **5 last** — instrumenting a moving target is waste. By Phase 5 the four seams
  are frozen and tracing is pure decoration.

## What each phase gives the thesis

| Phase | Thesis chapter it feeds |
|---|---|
| 0 | Ch. 5 Implementation — methodology of the migration itself |
| 1 | Ch. 4 Architecture; enables the model-agnosticism experiment (H5) |
| 2–3 | Ch. 4 Architecture; enables the routing-efficiency experiment (H1) |
| 4 | Ch. 4; enables verification (H3) and abstention experiments |
| 5 | Ch. 6 Methodology — traces *are* the measurement instrument |

Phase 5 is the hinge: without execution traces, every metric in
[hypotheses.md](../07-research/hypotheses.md) would have to be measured by hand.
