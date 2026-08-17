# Testing

## Running

```bash
PYTHONPATH=.:platform .venv/bin/pytest                        # unit suite
PYTHONPATH=.:platform .venv/bin/pytest --cov --cov-report=term  # with the 87% gate
PYTHONPATH=.:platform .venv/bin/python -m intelligence.evaluation.run --mode ci
```

The suite needs **no services and no API key**. `tests/conftest.py::no_gemini_key`
is autouse and deletes `GEMINI_API_KEY` from the environment, so a developer's
local `.env` can never leak a live key into a test run. The database is
in-memory SQLite, created per test via `Base.metadata.create_all` — Alembic is
never involved.

## How the LLM is faked

`tests/conftest.py::FakeLLMClient` is a scripted double for the whole LLM layer.
A script maps a **substring of the agent's system prompt** to an ordered list of
steps:

- `("tool", name, args)` — awaits the **real** `tool_executor`, so the MCP
  registry, RAG pipeline, and guideline corpus all execute for real and the
  resulting citations are genuine.
- `("answer", text)` — the final assistant content.

Injection is by setting the module-level singleton:

```python
monkeypatch.setattr(intelligence.llm.factory, "_client", fake)
```

Patching the global rather than the function object means every caller sees the
fake regardless of where it imported `get_llm_client` from.

### The script-key landmine

`_script_for` returns the first key that is a substring of the system prompt,
falling back to `default_script`. The two canonical keys are
`"clinical evidence specialist"` and `"coordinating physician-assistant"`.

If a role prompt is reworded, affected tests silently fall through to
`default_script` and **still pass while asserting nothing**.
`tests/test_prompt_contract.py` exists solely to make that failure loud. Keep it
green before touching any prompt.

## Conventions

- Tests are flat in `tests/`; there is no `tests/__init__.py`. New runtime tests
  go under `tests/sephiroth/<pkg>/`, and because collection is rootdir-based,
  **basenames must be unique across the whole tree**.
- One module per unit under test, `test_<module>.py`, with suffixes for
  variants: `_adversarial`, `_extra`, `_full`, `_live`, `_matching`.
- Skips are module-level `pytestmark = pytest.mark.skipif(<infra reachable>)`,
  never keyed on environment variables — a test that silently skips because a
  variable is unset is a test that never runs in CI.
- Registered markers: `spec`, `contract`, `integration`, `legacy`.
- Every test module opens with a docstring saying what is covered **and why it
  is structured that way**.

## The gates that matter

| Gate | Catches |
|---|---|
| `tests/test_sse_contract.py` | wire-format drift against the frontend's hand-rolled SSE parser |
| `tests/test_contracts_schema.py` | a domain model changing without its committed JSON Schema |
| `tests/test_prompt_contract.py` | tests silently degrading to `default_script` |
| `tests/test_tool_authorization.py` | an agent executing a tool outside its whitelist |
| `tests/test_coverage_config.py` | a new package being invisible to the coverage gate |
| `eval` CI job | agents getting *worse* — unit tests only see shape, not quality |
| `docker-build-smoke-test` | the real import graph, which pytest's `pythonpath` hides |

## Evaluation harness

`--mode ci` is deterministic and offline: retrieval metrics run against the
committed embeddings artifact, and citation metrics replay the 27 committed
transcripts. It fails the build if any metric drops below
`intelligence/evaluation/thresholds.json`, or if the results or embeddings
artifact are **stale** — that is, if `golden.json` or the transcripts changed
without the recorded run being regenerated.

`--mode full` calls the live API, burns quota, and never gates.
