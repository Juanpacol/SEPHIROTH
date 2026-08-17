# Agent registry

> **This document is rewritten in Phase 3.** Today it describes five Python
> classes. After [ADR-004](../08-decisions/ADR-004-capability-based-routing.md)
> lands, the YAML below becomes the normative source that
> `sephiroth.runtime.registry` actually loads, and agents stop being classes.

## The five agents today

Each is an `MCPAgent` subclass in `intelligence/agents/__init__.py`: a `name`, a
`role_prompt`, and an `allowed_tools` whitelist enforced at dispatch.

| Agent | `name` | Node name | Tools | Runs when |
|---|---|---|---|---|
| Evidence | `evidence` | `evidence` | `search_clinical_guidelines`, `search_pubmed` | always |
| Radiology | `radiology` | `radiology` | `inspect_medical_image`, `analyze_medical_image`, `describe_medical_image` | `image_path` present |
| Laboratory | `laboratory` | `laboratory` | *(none — works from context)* | `lab_results` present |
| Drug safety | `drug-safety` | `drug_safety` | `check_drug_interactions` | `medications` present |
| Coordinator | `coordinator` | `coordinator` | `extract_medical_entities`, `summarize_clinical_note` | always, last |

### The two-name problem

`drug-safety` (display) and `drug_safety` (node) are the same agent. The SSE
`routing` event carries node names; `agent_completed` carries display names; the
frontend normalises between them with `.replace("_", "-")`.

This is accidental, load-bearing, and frozen — see
[the migration charter](../00-migration-charter.md) §2.1. `AgentCapability`
carries both `id` and `node_name` explicitly so the normalisation can eventually
be removed deliberately rather than by accident.

## Target: agents as data

Phase 3 replaces the classes with entries like this:

```yaml
agent:
  id: drug-safety
  node_name: drug_safety
  name: Drug Safety Agent
  description: Screens medication lists for interactions.

capabilities:
  - drug_interaction
  - contraindication
  - medication_risk

tools:
  - check_drug_interactions

risk:
  level: high
  requires_human_review: false

execution:
  parallelizable: true
  requires_evidence: true
  requires_verification: true
```

Loaded into `sephiroth.contracts.AgentCapability`, which already exists and is
schema-locked.

### Why this shape

- **`capabilities` is what the router matches on.** The planner asks for
  `drug_interaction`; the router finds who provides it. Nothing names a class.
- **`risk.level` is a routing input**, so a high-risk task can be required to
  pass through verification.
- **`execution` flags are scheduling facts**, letting the executor decide what
  may run concurrently without hardcoding it.

## Adding an agent

Today (see [setup.md](../04-development/setup.md)):

1. Subclass `MCPAgent`; set `name`, `role_prompt`, `allowed_tools`.
2. Wire it into `intelligence/agents/workflow.py`.
3. **Add an entry to `_ACTION_TEMPLATES` / `_NO_TOOL_ACTIONS`** in
   `explainability.py` — `explanation` is rebuilt on read, so a missing template
   degrades *historical* consultations too.
4. Add its tools to the whitelist, or dispatch refuses them.

After Phase 3: add a registry entry. Steps 2–4 collapse into declaration.

## Role prompts are byte-frozen during migration

`tests/conftest.py::FakeLLMClient` selects a script by substring-matching the
system prompt. Two substrings are canonical across the suite:
`"clinical evidence specialist"` and `"coordinating physician-assistant"`.

Rewording a role prompt makes dozens of tests fall through to `default_script`
and **pass while asserting nothing**. `tests/test_prompt_contract.py` guards
this. Phase 3 moves the prompts byte-for-byte; rewording is a separate,
later change with its own test updates.
