# ADR-003 — A formal `ModelProvider` interface

**Status:** Accepted · **Date:** 2026-08-16 · **Phase:** decided 0, executed 1

## Context

Two provider classes exist, `GeminiClient` and `GroqClient`. They share method
names — `chat`, `generate_json`, `describe_image`, `health` — **by convention
only**. There is no Protocol, no ABC, nothing that fails when they diverge.
`get_llm_client()` is an `if settings.groq_api_key` branch, and agents annotate
their constructor parameter as `GeminiClient` by name.

## Problem

Model-agnosticism is a *research hypothesis* (H5), not just an engineering
preference. If the runtime's benefits turn out to be Gemini-specific prompt
engineering, the contribution collapses. That cannot be tested without the
ability to swap providers.

## Decision

Define `ModelProvider` as a `@runtime_checkable` Protocol, retrofit Gemini,
Groq and the fallback composer to satisfy it structurally, and replace the
factory's branch with config-driven selection.

Capabilities are **declared**, not discovered by exception: `supports_vision`,
`supports_tools`. Groq raising `LLMUnavailableError` from `describe_image`
becomes a declared limitation instead of a surprise.

## Rationale

- The interface is already empirically fixed by *four* implementations —
  including `FakeLLMClient` in the test suite. Writing it down is recording
  reality, not inventing an abstraction.
- Structural typing (Protocol, no inheritance) mirrors the existing
  `EmbeddingProvider` pattern in `data/embeddings/base.py`, which works well.
- Parameter **names** are load-bearing: every `chat()` call site passes keywords.
  Freezing them in the Protocol makes that guarantee mechanical.

## Consequences

Adding a provider becomes a file, not a refactor. H5 becomes runnable in Phase 1
rather than at the end — deliberately, since a negative H5 should change course
early.

The cost is one indirection layer and the risk of the shim's global-state trap,
which is why `tests/test_llm_shims.py` asserts module identity.

## Alternatives rejected

**Keep duck typing** — works until it doesn't, and fails at runtime in
production rather than at import in CI.
**LiteLLM or similar** — solves provider routing but re-introduces exactly the
framework coupling this project is removing, and its abstraction is not ours to
specify.
