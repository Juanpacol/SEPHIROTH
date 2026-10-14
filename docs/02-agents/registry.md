# Agent registry

> Current, not historical. The agents-as-data design this document used to
> propose as "Phase 3 target" has been the real implementation since Phase 3
> — the project is at Phase 16 now. Source of truth: `src/sephiroth/runtime/registry.py`.

## The three agents

Each is an `AgentCapability` record (`sephiroth.contracts.AgentCapability`), not
a class — `id`, `node_name`, a `role_prompt`, and a `tools` whitelist enforced
at dispatch by `ToolRuntime.scoped_executor()`.

| Agent | `id` | `node_name` | Tools | Runs when |
|---|---|---|---|---|
| Evidence | `evidence` | `evidence` | `search_clinical_guidelines`, `search_pubmed` | default / always eligible |
| Radiology | `radiology` | `radiology` | `inspect_medical_image`, `analyze_medical_image`, `describe_medical_image` | `image_path` present in context |
| Drug safety | `drug-safety` | `drug_safety` | `check_drug_interactions` | `medications` present in context |

`intent_router.py` routes every consultation to exactly **one** of these three
— its answer is the final answer, no coordinator turn (`ADR-016`). `Laboratory`
and `Coordinator` (and the 5-agent, multi-agent-fan-out world this document
used to describe) were removed in Phase 14 (`SPEC-029`): `Laboratory`
duplicated `sephiroth.safety.risk`'s deterministic lab rules with no test on
its own clinical output; `Coordinator`/the fan-out it merged had been
unreachable in production since single-specialist routing became the default.

### The two-name problem (still live, still frozen)

`drug-safety` (`id`, display form) and `drug_safety` (`node_name`) are the same
agent. The SSE `routing` event carries node names; `agent_completed` carries
display names; the frontend normalises between them with `.replace("_", "-")`.

This is accidental, load-bearing, and frozen — see
[the migration charter](../00-migration-charter.md) §2.1. `AgentCapability`
carries both `id` and `node_name` explicitly so the normalisation can
eventually be removed deliberately rather than by accident.

## Adding an agent

See CLAUDE.md's "How to Extend → Add a New Agent" for the current steps
(add an `AgentCapability` to `registry.py`, give `intent_router.py` a way to
route to it, add an `explainability.py` template entry).

## Role prompts are byte-sensitive

`tests/conftest.py::FakeLLMClient` selects a script by substring-matching the
system prompt. The canonical substring for the Evidence agent,
`"clinical evidence specialist"`, is asserted by
`tests/test_prompt_contract.py` — rewording it makes dozens of tests fall
through to `default_script` and **pass while asserting nothing**.
