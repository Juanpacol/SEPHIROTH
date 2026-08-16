---
id: SPEC-001
title: Model Provider
phase: 1
version: 1.1.0
status: Implemented
authors: [jbotero]
created: 2026-08-16
updated: 2026-08-16
supersedes: []
superseded_by: null
depends_on: [SPEC-000]
adrs: [ADR-003, ADR-010]
features: [F-022, F-023]
diagrams: [D1]
---

# SPEC-001 — Model Provider

## 1. Summary

A formal `ModelProvider` interface, three implementations behind it, and
config-driven provider selection. Makes model-agnosticism (H5) testable instead
of aspirational.

## 2. Motivation

`intelligence/llm/gemini_client.py` and `groq_client.py` share method names by
convention only — no Protocol, no ABC. `intelligence/agents/base.py:29`
annotates its constructor parameter as `GeminiClient` by name, and
`intelligence/llm/factory.py` selects a provider with `if settings.groq_api_key`
rather than by configuration. There is no way to run the benchmark on a third
provider without editing agent code.

## 3. Goals

- **G-1** One structural interface every provider satisfies, including the test double.
- **G-2** Provider chosen by configuration, not by which API key happens to be set.
- **G-3** Capability differences declared, not discovered by exception.
- **G-4** Zero behavioural change for the default configuration.

## 4. Non-Goals

- **NG-1** No new providers implemented here; the interface must merely admit them.
- **NG-2** Embeddings are out of scope — `data/embeddings/` already has its own provider Protocol.
- **NG-3** No change to `describe_image` fallback behaviour (it stays primary-only).
- **NG-4** No agent, routing, or tool changes; those are SPEC-002 and SPEC-003.

## 5. Definitions

- **Provider** — one concrete model backend (Gemini, Groq, …).
- **Capability** — a declared boolean property of a provider, e.g. `supports_vision`.

## 6. Contracts

### 6.1 Types

Module: `src/sephiroth/models/base.py`

```python
@dataclass
class ChatResult:
    content: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    rounds: int = 0


class LLMUnavailableError(RuntimeError):
    """The only exception that triggers provider fallback."""
```

| Field | Type | Req | Default | Invariant |
|---|---|---|---|---|
| `content` | `str` | yes | — | may be empty; never `None` |
| `tool_calls` | `list[dict]` | no | `[]` | each entry has exactly `name`, `arguments`, `result` |
| `rounds` | `int` | no | `0` | `>= 0`; equals tool-loop iterations consumed |

### 6.2 Interfaces

```python
@runtime_checkable
class ModelProvider(Protocol):
    model: str
    supports_vision: bool
    supports_tools: bool

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        system_prompt: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_executor: ToolExecutor | None = None,
        think: bool | None = False,
    ) -> ChatResult: ...

    async def generate_json(
        self, prompt: str, schema: dict[str, Any], *, system_prompt: str | None = None
    ) -> Any: ...

    async def describe_image(
        self, image_bytes: bytes, mime_type: str, prompt: str, max_output_tokens: int = 512
    ) -> str: ...

    async def health(self) -> bool: ...
```

**Parameter names are load-bearing.** Every `chat()` call site passes keywords,
so `chat` marks them keyword-only. `generate_json` is called positionally in
`intelligence/evaluation/faithfulness.py:92` and by keyword in
`intelligence/nlp/timeline_extractor.py:90`, so its first two parameters stay
positional-or-keyword **in this order**.

### 6.3 State machine

`N/A` — providers are stateless between calls apart from rate-limiter windows.

### 6.4 Errors

| Exception | Raised when | Triggers fallback |
|---|---|---|
| `LLMUnavailableError` | no API key, rate limit exhausted, 5xx, unsupported capability | **yes** |
| `GroqToolUseFailedError` | Groq rejects a tool schema | no — provider-internal, must not escape `GroqClient` |

### 6.5 Configuration

| Setting | Type | Default | Note |
|---|---|---|---|
| `llm_provider` | `Literal["gemini","groq"]` | `"gemini"` | new |
| `llm_enable_fallback` | `bool` | `True` | existing |
| `groq_timeout_seconds` | `int` | `60` | new; matches Gemini's default |
| `groq_max_output_tokens` | `int` | `2048` | new; was borrowing the Gemini value |
| `groq_rpm_limit` | `int` | `0` | new; `0` disables throttling, preserving today's behaviour |

## 7. Behaviour

- **B-1** Every provider MUST satisfy `isinstance(p, ModelProvider)`.
- **B-2** Fallback MUST trigger on `LLMUnavailableError` and on nothing else.
- **B-3** `describe_image` MUST NOT fall back; it always uses the primary.
- **B-4** A provider with `supports_vision is False` MUST raise
  `LLMUnavailableError` from `describe_image` rather than returning a degraded result.
- **B-5** `chat` MUST NOT raise when the tool-round budget is exhausted; it
  returns a `ChatResult` explaining the limit was reached.
- **B-6** `get_llm_client()` MUST honour `settings.llm_provider`.
- **B-7** With default configuration, observable behaviour MUST be identical to
  the pre-migration system.
- **B-8** Retry and rate-limiting MUST be shared, not duplicated per provider.

## 8. Acceptance Criteria

| ID | Criterion (assertable) | Verifies | Test |
|---|---|---|---|
| AC-001-01 | `isinstance(p, ModelProvider)` is `True` for `GeminiClient`, `GroqClient`, `FallbackLLMClient` and `FakeLLMClient` | B-1 | `tests/test_model_provider_protocol.py` |
| AC-001-02 | `chat`'s keyword-only parameters are exactly `system_prompt, tools, tool_executor, think` | B-1 | `tests/test_model_provider_protocol.py` |
| AC-001-03 | `generate_json`'s first two positional parameters are `prompt, schema` in that order | B-1 | `tests/test_model_provider_protocol.py` |
| AC-001-04 | A primary raising `LLMUnavailableError` falls back; any other exception propagates | B-2 | `tests/test_fallback_client.py` |
| AC-001-05 | `describe_image` on a `supports_vision is False` provider raises `LLMUnavailableError` | B-4 | `tests/test_groq_client.py` |
| AC-001-06 | Exhausting `max_tool_rounds` returns a `ChatResult`, raising nothing | B-5 | `tests/test_gemini_client.py` |
| AC-001-07 | `llm_provider="groq"` yields a Groq-primary client | B-6 | `tests/test_llm_factory.py` |
| AC-001-08 | Every symbol importable from `intelligence.llm` before the migration is still importable, and `factory._client` patched through the new module is observed via the old path | B-7 | `tests/test_llm_shims.py` |
| AC-001-09 | The rate limiter admits `rpm_limit` calls per window then blocks; backoff is capped at 30s with bounded jitter | B-8 | `tests/test_throttle.py` |
| AC-001-10 | `test_gemini_client.py`, `test_groq_client.py`, `test_fallback_client.py` pass with zero behavioral change against the shims; `test_llm_factory.py` retargets its factory import (see §10) | B-7 | those four modules |

## 9. Test Matrix

| Layer | What | Where |
|---|---|---|
| Contract | Protocol satisfaction, signature introspection | `tests/test_model_provider_protocol.py` |
| Unit | shared throttle and backoff | `tests/test_throttle.py` |
| Characterization | existing provider tests, unmodified | the four legacy modules |
| Shim | import surface and global identity | `tests/test_llm_shims.py` |

## 10. Migration & Compatibility

Shadows `intelligence/llm/*`, which becomes re-export shims in this phase and is
**deleted in Phase 2**.

**The known trap:** `tests/conftest.py::patch_llm_factory` does
`monkeypatch.setattr(factory_module, "_client", fake)`. If the old module becomes
`from sephiroth.models.factory import *`, patching the old path binds a copy
while `get_llm_client` reads the real global — tests would pass while exercising
the live client. `conftest.py` is retargeted in the same pull request, and
AC-001-08 asserts the identity.

**v1.1.0 correction (found during implementation):** the same trap applies to
every test that patches `intelligence.llm.factory`'s module-level `settings`/
`_client` globals directly, not only `conftest.py`. `tests/test_llm_factory.py`
does this in its own `_reload_settings` helper, and `tests/test_api_agents.py`
/ `tests/test_api_patients_rag.py` each build a local `app` fixture with the
same pattern. All four had their two-line `import ... as factory_module`
retargeted to `sephiroth.models.factory` in this phase — a mechanical import
change, not a behavioral one, since each still patches the same conceptual
global and asserts the same outcomes. `test_gemini_client.py`,
`test_groq_client.py`, and `test_fallback_client.py` construct client
instances directly rather than patching module globals, so they needed no
change beyond a one-line comment anchoring the AC they verify. This is the
corrected scope of AC-001-10.

## 11. Risks & Open Questions

| # | Risk / question | Resolution |
|---|---|---|
| 1 | Shim global-state indirection silently disables the fake client | AC-001-08 |
| 2 | `import *` does not re-export underscore-prefixed names | Grep for cross-module `_`-prefixed access before merging; use explicit re-export if any exists |
| 3 | New settings break the container's startup validation | All new fields have defaults; Docker smoke test is the gate |
| 4 | Should `rounds` mean attempted or completed loops? | Completed, matching current behaviour; recorded here to prevent drift |
| 5 | `intelligence/mcp/registry.py` also patches `intelligence.llm.factory`-adjacent state? | Confirmed no — it depends only on `core.config.settings`, unaffected by this phase |

## 12. References

- [ADR-003](../08-decisions/ADR-003-model-provider-abstraction.md)
- `data/embeddings/base.py` — the structural-Protocol pattern being mirrored
- [Migration charter](../00-migration-charter.md) §3, shim rules

## Changelog

| Version | Date | Change |
|---|---|---|
| 1.0.0 | 2026-08-16 | Initial version; approved as the Phase 1 gate |
| 1.1.0 | 2026-08-16 | Implemented. Corrected AC-001-10 and §10: the factory-global-patching trap applies to `test_llm_factory.py`, `test_api_agents.py` and `test_api_patients_rag.py`, not only `conftest.py` — all three retargeted their factory import. |
