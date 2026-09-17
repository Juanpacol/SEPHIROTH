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

## Commit message format

Every commit from `SF001` onward must match:

```
SF<NNN> <body, max 50 words> [<type>]
```

Example: `SF001 Add commit-msg validator script enforcing SF id, word cap, and type suffix [chore]`

- **`SF<NNN>`** — the user story/feature id, not a per-commit counter. **Every
  commit that belongs to the same story shares the same id** (e.g. all
  commits implementing story SF001 are `SF001 ... [chore]`, `SF001 ...
  [docs]`, etc.). A new story gets the next id. Run `scripts/next-sf-id.sh`
  before starting a new story for the suggested next number. This is
  advisory, not a strict guarantee: two branches can independently start a
  story with the same next id before either merges. That gap is accepted and
  documented in [ADR-015](docs/08-decisions/ADR-015-commit-message-format.md)
  — the format is a greppable audit trail, not a strict primary key.
- **Body** — whitespace-split word count, excluding the `SF<NNN>` prefix and
  the `[<type>]` suffix, capped at 50. Describe what changed, directly.
- **`[<type>]`** — exactly one of: `feat`, `fix`, `docs`, `chore`, `refactor`,
  `test`.

This applies **going forward only** — commits before `SF001` keep their
existing Conventional Commits style and are never rewritten.

**This is enforced, not just documented.** A local `commit-msg` git hook
gives fast feedback; the `commit-lint` job (part of the **Code Review** gate,
see below) is the real gate — a PR with a malformed commit cannot be merged.
One-time setup per clone:

```bash
git config core.hooksPath .githooks
```

See [`.githooks/README.md`](.githooks/README.md) and
[ADR-015](docs/08-decisions/ADR-015-commit-message-format.md) for the full
rationale.

## Required PR gates

`main` is branch-protected with exactly two required status checks — no
approval requirement, since this is a solo-maintainer repo and GitHub refuses
to count a PR author's own approval toward a required-review count:

- **Security** (`.github/workflows/security.yml`, `security-gate`) —
  gitleaks (secret scanning) + bandit HIGH-severity/HIGH-confidence findings.
  Blocking. `dependency-audit` (pip-audit/npm audit) runs in the same
  workflow but stays advisory — third-party CVEs with no available fix must
  never turn `main` permanently red.
- **Code Review** (`.github/workflows/code-review.yml`, `code-review-gate`)
  — the automated stand-in for a human reviewer: lint, commit format,
  tests + coverage gate, the SDD spec-conformance check (every `Implemented`
  spec's acceptance criteria must exist in the test tree, contracts must not
  have drifted — see [the migration charter](docs/00-migration-charter.md)),
  frontend lint/test/build/e2e, and a real Docker build + boot smoke test
  under both dev and prod config. `type-check` (mypy) runs alongside but is
  excluded from this gate — see its job comment for the 61-error baseline
  (DEBT-012) blocking that promotion.

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
- [ ] A dev-log entry in `docs/dev-log/YYYY-MM-DD.md` (older entries live under `docs/dev-log/archive/`).

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
