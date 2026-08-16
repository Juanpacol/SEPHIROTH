# Contributing

## Setup

See [docs/04-development/setup.md](docs/04-development/setup.md). Short version:

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -e .
```

## The loop

SEPHIROTH uses **Spec-Driven Development**. For anything that changes a contract
— a type, an interface, a wire format, a state transition — the order is:

1. **Spec.** Write or amend a `docs/specs/SPEC-00N`, following
   [SPEC-000](docs/specs/SPEC-000-spec-process.md). Get it to `Approved`.
2. **Tests.** Write them from the spec's acceptance criteria. They should fail.
3. **Code.** Make them pass.
4. **Mark it.** Set the spec to `Implemented` once its criteria are green.

Bug fixes, dependency bumps and anything that changes no contract skip this
entirely. The ceremony is for contracts, not for every commit.

## Before opening a pull request

Run the same gate CI runs:

```bash
.venv/bin/ruff check . && .venv/bin/ruff format --check .
PYTHONPATH=.:platform .venv/bin/pytest --cov
PYTHONPATH=.:platform .venv/bin/python -m intelligence.evaluation.run --mode ci
.venv/bin/python scripts/docs_check.py
.venv/bin/python scripts/export_contracts.py --check
```

Checklist:

- [ ] Coverage ≥ 87%. **Do not lower the threshold** — add tests instead.
- [ ] New `src/sephiroth/<pkg>/` added to `coverage.run.source` in the same PR.
- [ ] Contract schemas regenerated if a model changed.
- [ ] `docs/03-features/feature-registry.md` updated if a feature's status moved.
- [ ] `docs/project-state.yaml` updated if a component's status moved.
- [ ] `CHANGELOG.md` entry under `[Unreleased]`.
- [ ] A dev-log entry in `docs/dev-log/YYYY-MM-DD.md`.

## Things that will bite you

**The frozen contracts.** [The migration charter](docs/00-migration-charter.md)
§2 lists four interfaces the frontend and database depend on: the five SSE
events, the persisted state shape, `ConsultResponse`, and the derived
`explanation`. Changing one requires a coordinated frontend change.
`tests/test_sse_contract.py` will stop you.

**The script-key trap.** `FakeLLMClient` picks a script by substring-matching the
system prompt. Reword a role prompt and dozens of tests fall through to
`default_script` and **pass while asserting nothing**.
`tests/test_prompt_contract.py` exists to make that loud.

**New agents need explainability templates.** `explanation` is rebuilt on read,
so a missing `_ACTION_TEMPLATES` entry degrades *historical* consultations, not
just new ones.

**New tools need whitelist entries.** Tool authorization is enforced at
dispatch; an unlisted tool returns an authorization error rather than running.

**Coverage entries are per-package.** Never add `src/sephiroth` wholesale — a
wildcard root silently hides future subpackages from the gate.

## Conventions

- Ruff, line length 110. `ruff format` is enforced in CI.
- Tests are flat in `tests/`; new runtime tests go in `tests/sephiroth/<pkg>/`
  with **globally unique basenames** (collection is rootdir-based).
- Every test module opens with a docstring saying what it covers *and why it is
  structured that way*.
- Mermaid source only in `docs/09-diagrams/`. Everything else links to it.
- No secrets in code, ever. `.env` is gitignored and gitleaks blocks CI.

## Where to look

| Question | File |
|---|---|
| What is this project? | [docs/00-project/vision.md](docs/00-project/vision.md) |
| What is actually built? | [docs/project-state.yaml](docs/project-state.yaml) |
| Why is it built that way? | [docs/08-decisions/](docs/08-decisions/) |
| What are the rules of the migration? | [docs/00-migration-charter.md](docs/00-migration-charter.md) |
| How do I test this? | [docs/04-development/testing.md](docs/04-development/testing.md) |
| What proves requirement X? | [docs/traceability.md](docs/traceability.md) |

## Medical accuracy is non-negotiable

Every agent prompt references clinical guidelines. Every recommendation cites
sources. The disclaimer is on every page. This is decision support for
professionals, not a diagnostic tool — and no change should blur that.
