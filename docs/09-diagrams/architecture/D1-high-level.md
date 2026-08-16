---
id: D1
title: High-Level Architecture
status: target
phase_authored: 0
phase_last_updated: 0
specs: [SPEC-001, SPEC-002, SPEC-003, SPEC-004, SPEC-005]
---

# D1 — High-Level Architecture

> **Status: target.** This is the architecture Phases 0–5 build toward, not
> what runs today. Boxes marked ▢ do not exist yet; see
> [project-state.yaml](../../project-state.yaml) for what is actually
> implemented, and [the migration charter](../../00-migration-charter.md) for
> the phase order.

The organising idea: **the runtime is the product, the clinical application is
its first consumer.** Everything inside the runtime box is domain-agnostic; the
clinical specifics live in the agents and tools it is configured with.

```mermaid
flowchart TB
    subgraph CLIENT["Client"]
        UI["Next.js frontend<br/><i>platform/frontend</i>"]
    end

    subgraph APP["Application — platform/"]
        API["FastAPI routers<br/><i>platform/api</i>"]
        AUTH["JWT auth<br/><i>platform/auth</i>"]
        DB[("Postgres + pgvector<br/><i>data/schemas</i>")]
    end

    subgraph RT["SEPHIROTH runtime — src/sephiroth/ (model-agnostic)"]
        direction TB
        ANALYZE["▢ Task Analyzer"]
        PLAN["▢ Planner"]
        ROUTE["▢ Capability Router"]
        EXEC["▢ Executor"]
        REG["▢ Agent Registry"]
        RECOVER["▢ Recovery Engine"]
        CTX["▢ Context Engine<br/>retrieval · memory · budgeting"]
        VERIFY["▢ Verification<br/>claims · conflicts · confidence"]
        SAFE["▢ Safety &amp; Abstention"]
        TOOLS["▢ Tool Runtime<br/>capability + permission checks"]
        OBS["▢ Observability<br/>ExecutionTrace"]
    end

    subgraph MODELS["▢ ModelProvider abstraction"]
        GEM["Gemini"]
        GROQ["Groq"]
        OTHER["OpenAI · Anthropic · local"]
    end

    subgraph MCP["MCP tool servers — existing"]
        T1["imaging"]
        T2["drug safety"]
        T3["guidelines / RAG"]
        T4["clinical NLP"]
        T5["vision"]
    end

    UI --> API
    API --> AUTH
    API --> DB
    API --> ANALYZE

    ANALYZE --> PLAN
    PLAN --> ROUTE
    ROUTE --> REG
    ROUTE --> EXEC
    EXEC --> CTX
    EXEC --> TOOLS
    EXEC --> VERIFY
    EXEC -.failure.-> RECOVER
    RECOVER -.replan.-> PLAN
    RECOVER -.retry.-> EXEC
    VERIFY --> SAFE
    SAFE -.abstain.-> API
    SAFE --> API

    EXEC --> MODELS
    CTX --> MODELS
    VERIFY --> MODELS

    TOOLS --> MCP
    CTX --> T3

    EXEC -.spans.-> OBS
    VERIFY -.spans.-> OBS
    TOOLS -.spans.-> OBS
    OBS --> DB
```

## What this changes

| | Today | Target |
|---|---|---|
| Routing | static key-presence check | capability match against a registry |
| Orchestration | fixed compiled graph, depth 2 | plan-driven executor, replanning possible |
| Provider | `GeminiClient` imported by name | `ModelProvider` selected by config |
| Tool access | whitelist filters advertised schemas | capability + permission checked at dispatch |
| Verification | citation labels audited post-hoc | claims verified against evidence, in-loop |
| Failure | exception propagates | classified, then retried / replanned / abstained |
| Observability | ad-hoc log lines | structured, nested, replayable trace |

## Reading the arrows

Solid arrows are the request path. Dotted arrows are exceptional or ambient:
failure handling, and span emission. The Recovery Engine is deliberately drawn
feeding *back* into the planner — replanning after failure is the capability
that distinguishes a runtime from a pipeline.
