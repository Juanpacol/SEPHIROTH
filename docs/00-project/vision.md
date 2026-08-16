# Vision

## The one-sentence definition

> **SEPHIROTH is an evidence-grounded, model-agnostic multi-agent AI runtime for
> clinical decision support. It plans and routes tasks across specialised
> agents, retrieves and verifies evidence through MCP tools, detects
> contradictions and unsupported claims, applies safety policies and abstention,
> and exposes complete execution traces for reproducible evaluation.**

## The thesis

LLM-based multi-agent systems should not rely on the underlying model to produce
reliable behaviour. They need an **execution layer** that explicitly controls
planning, agent selection, context, tool access, evidence grounding,
verification, failure recovery, safety, and observability.

SEPHIROTH is a proposal for that layer, plus an evaluation of whether it
actually helps.

## What changes

The system began as a clinical application with agents inside it. It becomes a
runtime with a clinical application on top.

```
Before:  Clinical app → Coordinator → fixed agents → tools → answer
After:   Application  → Runtime (plan · route · execute · recover)
                      → Context · Verification · Safety · Observability
```

That reframing is the whole point. A fixed graph of four specialists answers
questions about diabetes. A runtime that plans, routes by capability, verifies
claims, and abstains is a general mechanism whose clinical configuration happens
to answer questions about diabetes.

## Guiding principle

> The runtime is the product. The clinical system is the case study. The
> experiments are the research contribution. The documentation is the project's
> knowledge system.

## The rule that keeps it honest

**Every component must improve orchestration, context, evidence grounding,
verification, safety, observability, or evaluation.** A component that does none
of those adds complexity without a measurable benefit, and complexity without
measurable benefit is precisely what the thesis argues against.

This cuts both ways: it is also the reason LangGraph is being removed
([ADR-001](../08-decisions/ADR-001-remove-langgraph.md)) rather than kept out of
inertia.
