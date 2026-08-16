# Scope

## In scope

An **agentic runtime**: the execution layer that sits between an application and
one or more LLMs, and that controls planning, agent selection, context, tool
access, evidence grounding, verification, recovery, safety, and observability.

The clinical decision-support application is the **first consumer** of that
runtime and the vehicle for validating it. It is not the contribution.

## Out of scope

- Being a medical device, or producing diagnoses.
- Training or fine-tuning models.
- Beating state-of-the-art on any single NLP benchmark.
- Clinical deployment with real patient data. All data is synthetic or public.

## Requirements

Each requirement is one falsifiable claim the finished system must support.
They are the left-hand column of [the traceability matrix](../traceability.md)
and the source of the research hypotheses.

| ID | Requirement | Rationale |
|---|---|---|
| **R-001** | Every factual claim in an answer must be traceable to retrieved evidence | An unsourced clinical claim is unusable regardless of how correct it is |
| **R-002** | The system must decline to answer rather than answer unsafely | Silence is a valid output; a confident wrong answer is not |
| **R-003** | The runtime must operate across LLM providers without behavioural rewrite | Otherwise the contribution is prompt engineering for one vendor |
| **R-004** | Agent selection must follow declared capabilities, not hardcoded conditionals | Hardcoded routing cannot generalise beyond the domain it was written for |
| **R-005** | Failures must be classified and acted on, not propagated | A runtime that dies on a tool timeout is a pipeline |
| **R-006** | Every request must produce a replayable execution trace | Unobservable behaviour cannot be evaluated or reproduced |
| **R-007** | Tools must be reachable only by agents authorised for them | Capability confinement is a safety property, not a convenience |
| **R-008** | The existing clinical application must keep working throughout the migration | A rewrite that breaks the case study destroys the evidence |

## Success criteria

The work succeeds if each requirement can be **demonstrated experimentally**,
not merely implemented. R-008 is the exception: it is demonstrated continuously
by the existing test suite staying green, which is why the migration is
strangler-fig rather than a rewrite.

## Boundaries of this plan

Phases 0–5 build the architecture. Evaluation, baselines, ablations and the
written thesis are deliberately a **separate effort**, begun once there is
something worth measuring. See [roadmap.md](roadmap.md).
