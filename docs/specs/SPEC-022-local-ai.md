---
id: SPEC-022
title: Local AI by Default, and Honest About It
phase: 20
version: 1.0.0
status: Implemented
authors: [jbotero]
created: 2026-09-06
updated: 2026-09-06
supersedes: []
superseded_by: null
depends_on: [SPEC-001]
adrs: [ADR-015]
features: [F-091, F-092, F-093, F-094]
diagrams: []
---

# SPEC-022 — Local AI by Default, and Honest About It

## 1. Summary

Makes the local provider the default path, replaces three hardcoded claims
about which model is running with the truth, and adds the control that decides
whether patient content may leave the machine at all.

No new AI capability is built here. `OllamaClient` has existed and worked since
before this plan started; what did not exist was a deployment where it is the
default, a way for an operator to *see* which provider is actually serving
requests, and a switch that stops PHI reaching a remote one.

## 2. Motivation

The product ships a privacy notice saying clinical text and images go to
Google. That notice is accurate today and there is no mechanism behind it —
nothing in the codebase can be set to make it false. For a clinic that cannot
send patient data to a third party, "use only synthetic data" is not a
configuration, it is a disclaimer.

Three specific untruths make this worse than a missing feature, because they
tell an operator the opposite of what is happening:

```python
# platform/api/routers/agents.py — the status endpoint
"model": settings.gemini_model,
"provider": "gemini",
"local_only": False,
```

That block is printed regardless of `llm_provider`. Run the whole stack against
a local Ollama and the operations screen still says the data is going to
Google. It also says `local_only: False` when it is, in fact, local only —
which is the direction of error that makes someone stop trusting the field
entirely.

```python
# platform/api/main.py
return {"status": "healthy", ..., "model": settings.gemini_model}
checks["llm"] = "configured" if settings.gemini_api_key else "unconfigured"
```

`/health` names a model that may not be in use, and `/health/ready` calls the
LLM unconfigured whenever `GEMINI_API_KEY` is absent — which is the *normal*
state of the local-first deployment this phase exists to make default. A
readiness probe that reports a correctly configured system as degraded is a
probe an operator learns to ignore.

And one real correctness bug hides behind the same inattention:
`data/embeddings/__init__.py` selects the Ollama embedding provider only when
`llm_provider == "ollama"`, never for `"split"`. A `split` deployment therefore
builds its cached artifact with one model and answers cache misses with
another. Vectors from two embedding models are not comparable; the similarity
scores are silently wrong, and nothing fails.

## 3. Goals

- **G-1** The local provider is the default, so a fresh install sends nothing
  anywhere.
- **G-2** Every endpoint that names a provider or a model names the real one.
- **G-3** An operator can forbid patient content reaching a remote provider,
  and the system enforces it rather than documenting it.
- **G-4** A `split` deployment retrieves in one vector space.
- **G-5** Losing the model degrades to something deterministic, not to a 503
  that blames the wrong provider.

## 4. Non-Goals

- **NG-1** No new model provider. `OllamaClient` is complete; this phase
  changes which one is chosen, not what any of them can do.
- **NG-2** No PHI classifier. `ai_allow_phi` gates the *seams* that are known
  to carry patient content, listed in §6.5. Inferring whether an arbitrary
  string contains PHI is a different, much weaker guarantee, and a heuristic
  that is right most of the time is worse than an explicit list because it
  invites trusting it.
- **NG-3** No change to the frozen contracts of `docs/00-migration-charter.md`
  §2. The SSE event set, `ConsultResponse`, and the persistence shape are
  untouched.
- **NG-4** No automatic model download or Ollama supervision from the API
  process. The compose file and the runbook install and pull; the application
  reports what it finds.
- **NG-5** No HIPAA/GDPR compliance claim. `ai_allow_phi=false` plus a local
  provider removes one specific exposure — content leaving the machine to a
  model vendor. Compliance is a programme, not a flag, and saying otherwise
  here would be the same kind of untruth this phase is removing.

## 5. Definitions

- **Local provider** — one whose `base_url` resolves to the machine or the
  clinic's own network, so no request leaves the deployment. `OllamaClient`
  is local *unless* its `base_url` is pointed at a hosted endpoint, which is
  supported (OpenRouter) and is therefore decided per instance, not per class.
- **PHI seam** — a call site where patient-derived content is passed to a
  model. Enumerated in §6.5.
- **Provider report** — the single structure every endpoint uses to describe
  what is running (§6.1).

## 6. Contracts

### 6.1 Types

`src/sephiroth/models/base.py`:

```python
@dataclass(frozen=True)
class ProviderInfo:
    provider: str  # "gemini" | "groq" | "ollama" | "fallback" | "split" | "fake"
    model: str  # the chat model actually configured
    vision_model: str  # "" when this provider cannot do vision
    local: bool  # True only when no request leaves the deployment
    endpoint: str  # host only, never a key or a path
    components: tuple["ProviderInfo", ...] = ()  # composites describe their parts
```

`ModelProvider` gains one member:

```python
def describe(self) -> ProviderInfo: ...
```

A method rather than an attribute, because the two composite clients
(`FallbackLLMClient`, `VisionChatSplitClient`) have to build theirs from their
constituents, and `local` for a composite is the conjunction — a split client
whose vision half is Gemini is **not** local, and reporting otherwise would be
the exact failure mode this spec exists to fix.

### 6.2 Interfaces

| Endpoint | Field | Before | After |
|---|---|---|---|
| `GET /health` | `model` | `settings.gemini_model` | the running model |
| `GET /health/ready` | `checks.llm` | `configured` iff `GEMINI_API_KEY` | `ok` / `unreachable` from a real probe |
| `GET /api/agents/status` | `system.provider` | literal `"gemini"` | the running provider |
| `GET /api/agents/status` | `system.model` | `settings.gemini_model` | the running model |
| `GET /api/agents/status` | `system.local_only` | literal `False` | `ProviderInfo.local` |
| `GET /api/agents/status` | `system.phi_allowed` | absent | `settings.ai_allow_phi` |

`/health` stays liveness-only: it reads the built client's `describe()`, which
is a pure attribute read, and performs no I/O. `/health/ready` is the one that
probes.

Additive fields only; nothing is removed or renamed, so no frontend change is
forced by this spec.

### 6.3 State machine

`N/A` — no entity gains a lifecycle.

### 6.4 Errors

`PHINotAllowedError(LLMUnavailableError)`. It subclasses the existing
unavailability error deliberately: every PHI seam already has a degrade path
for "the model cannot serve this", and a refusal on privacy grounds should take
that same path rather than needing a second one written at each site. Callers
that want to distinguish it can; callers that do not, degrade correctly by
default.

The HTTP surface is `503` with an explicit detail, not `403`: from the
clinician's side the capability is unavailable in this deployment, which is
what `503` means. `403` would suggest their account lacks permission.

### 6.5 Configuration

| Setting | Type | Default | Meaning |
|---|---|---|---|
| `llm_provider` | literal | **`ollama`** (was `gemini`) | which client `get_llm_client()` builds |
| `ai_allow_phi` | bool | `false` | may patient-derived content reach a **non-local** provider |

The default flip is the phase. A fresh checkout with no keys now runs against a
local Ollama and sends nothing to anyone; a deployment that wants Gemini says
so, and — if it wants patient data to go there — says that separately.

Both defaults are safe-by-omission, and `ai_allow_phi=false` is inert on a
local provider, so the two interact in the one direction that matters: turning
the provider remote without also turning the flag on degrades, it does not
leak.

**The PHI seams `ai_allow_phi` gates**, enumerated rather than inferred:

| Seam | Content |
|---|---|
| `runtime/executor.py` — both entry points | the query and the patient context |
| `intelligence/nlp/timeline_extractor.py` | clinical note text |
| `intelligence/mcp/vision_server.py` | medical images |
| `platform/api/routers/medical.py` — the streaming half | medical images |
| `intelligence/mcp/patient_comms_server.py::draft_message` | the patient's name and follow-up facts |

The drafting gate sits in `patient_comms_server`, not in the approvals router
that was this spec's first guess: that is where the model is actually reached,
and the `@mcp.tool` wrapper shares the same function. `routers/medical.py` was
not in the first draft of this list at all — it calls `describe_image_stream`
directly instead of going through `vision_server`, and the enforcement test
described in §11 risk 3 caught it on its first run.

Modules that carry patient content but are reachable only *through* a gated
seam (`sephiroth/verification/*`, `runtime/agent.py`, the routers that call
them) are recorded in `PHI_DOWNSTREAM` rather than gated twice. A second check
on the same path is noise, and noise is what makes people stop reading a list.

Not gated, deliberately: `intelligence/evaluation/*` (synthetic corpus, no
patient rows), `runtime/intent_router.py` (runs before patient context is
assembled), and `fast_path.py`'s guideline lookup — a question about a
guideline is not patient content, and the moment it carries a patient context
it is no longer the fast path.

## 7. Behaviour

- **B-1** `get_llm_client()` MUST build an `OllamaClient` when `llm_provider`
  is unset.
- **B-2** `describe()` MUST report the model and provider actually configured
  on that client, never a setting for a different provider.
- **B-3** A composite's `local` MUST be the conjunction of its components'.
- **B-4** `local` MUST be `False` for an `OllamaClient` whose `base_url` is not
  a loopback or private-network host.
- **B-5** `/health`, `/health/ready` and `/api/agents/status` MUST derive every
  provider and model field from `describe()`.
- **B-6** `/health` MUST NOT perform I/O.
- **B-7** With `ai_allow_phi=false` and a non-local provider, every seam in
  §6.5 MUST raise `PHINotAllowedError` before any request is sent.
- **B-8** With `ai_allow_phi=false` and a **local** provider, every seam MUST
  behave exactly as before — the flag is about egress, not about AI.
- **B-9** Embedding provider selection MUST match the chat provider's vector
  space for `ollama` **and** `split`.
- **B-10** A consultation whose model is unreachable MUST attempt the
  deterministic fast path before failing, and its failure message MUST name the
  provider that is actually down.
- **B-11** A draft whose model is unreachable or refused MUST keep its
  deterministic template rather than failing.

## 8. Acceptance Criteria

| ID | Criterion (assertable) | Verifies | Test |
|---|---|---|---|
| AC-022-01 | With no settings at all, the built client is an `OllamaClient` | B-1 | `tests/test_local_ai_default.py::TestDefaultProvider` |
| AC-022-02 | Every provider's `describe()` reports its own model; a composite's `local` is the conjunction of its parts' | B-2, B-3 | `tests/test_provider_describe.py` |
| AC-022-03 | An Ollama client pointed at a hosted endpoint reports `local=False` | B-4 | `tests/test_provider_describe.py::TestLocality` |
| AC-022-04 | `/health`, `/health/ready` and `/api/agents/status` report the running provider under each configuration, and `/health` opens no connection | B-5, B-6 | `tests/test_provider_honesty_endpoints.py` |
| AC-022-05 | Each §6.5 seam refuses before sending when PHI egress is forbidden, and is unaffected when the provider is local | B-7, B-8 | `tests/test_phi_egress_gate.py` |
| AC-022-06 | `split` selects the Ollama embedding provider | B-9 | `tests/test_embedding_provider_selection.py` |
| AC-022-07 | An unreachable model degrades a consultation to the fast path and a draft to its template, and the error names the real provider | B-10, B-11 | `tests/test_local_ai_degradation.py` |
| AC-022-08 | `OllamaClient` and `VisionChatSplitClient` satisfy `ModelProvider` | B-2 | `tests/test_model_provider_protocol.py` |

## 9. Test Matrix

| Layer | What | Where |
|---|---|---|
| Pure | `ProviderInfo` construction, locality classification | `tests/test_provider_describe.py` |
| Contract | every client satisfies the widened protocol | `tests/test_model_provider_protocol.py` |
| Factory | default selection, embedding-space coherence | `tests/test_local_ai_default.py`, `tests/test_embedding_provider_selection.py` |
| HTTP | the three endpoints under gemini / ollama / split | `tests/test_provider_honesty_endpoints.py` |
| Policy | each PHI seam, both flag positions, both localities | `tests/test_phi_egress_gate.py` |
| Degradation | model down: consultation, draft, timeline, vision | `tests/test_local_ai_degradation.py` |

## 10. Migration & Compatibility

**No schema change. No migration.**

The breaking change is a default, and it is deliberate: an existing deployment
that sets `GEMINI_API_KEY` but never set `LLM_PROVIDER` was getting Gemini by
omission and will now get Ollama. That is the whole point of the phase, but it
must not be silent, so:

- `Settings` logs a single explicit line at startup naming the provider, the
  model and the locality. An operator who reads one line of the boot log knows
  what they are running.
- If `GEMINI_API_KEY` is set while `llm_provider` is defaulted to `ollama`, the
  line says so directly — that combination is almost always someone who
  upgraded and expected the old behaviour, and telling them costs one warning.
- `README.md` and `CLAUDE.md`'s "Key Design Decisions" #1 are rewritten. #1
  currently says the migration went *from* Ollama *to* Gemini; leaving it would
  make the repository's own documentation the next thing contradicting the
  code.

`.env.example` and the Render/Vercel deployment notes gain `LLM_PROVIDER=gemini`
plus `AI_ALLOW_PHI` set explicitly, so the public demo keeps working and states
what it does with data.

## 11. Risks & Open Questions

| # | Risk / question | Resolution |
|---|---|---|
| 1 | The default flip breaks a developer who had a Gemini key and no `LLM_PROVIDER` | Accepted and mitigated by the startup line and the docs rewrite. The alternative — a default that quietly sends patient data to a third party — is the thing being fixed |
| 2 | `local` is inferred from the endpoint host, which a determined configuration can defeat (a tunnel, a proxy on loopback) | Accepted. The check answers "is this address on this machine or this network", which is the honest question a host string can answer. It is a report, not a firewall, and §11.4 records what it is not |
| 3 | `ai_allow_phi` gates an enumerated list, so a seam added later is ungated by default | Mitigated by a test that walks every module reaching a client and fails on one that is on none of the three lists — the list is enforced, not merely written down. It earned its place immediately: it found `routers/medical.py`'s streaming image call, which this spec's own first draft of §6.5 had missed. NG-2 explains why a classifier is worse |
| 4 | A local model is materially weaker than Gemini at the same task | Real, and out of this spec's scope to fix. It is the trade the owner chose; the evaluation harness (`--mode full`) is how it gets measured rather than guessed at |
| 5 | The on-prem compose file pulls a multi-gigabyte model on first run | Documented in the runbook with sizes and a pre-pull step. Not automated — see NG-4 |
| 6 | `qwen2.5:14b` may not fit a clinic's hardware | The runbook lists the smaller variants and what each gives up. Choosing one is a deployment decision, and burying it in a default would be pretending it isn't |

## 12. References

- `docs/specs/SPEC-001-model-provider.md` — the `ModelProvider` protocol this
  widens.
- `docs/00-migration-charter.md` §2 — the frozen contracts left untouched.
- `src/sephiroth/models/ollama.py` — the client that already worked.

## Changelog

| Version | Date | Change |
|---|---|---|
| 1.0.0 | 2026-09-06 | Initial version |
