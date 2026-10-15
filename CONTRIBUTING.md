# Contributing

## Setup

See [docs/04-development/setup.md](docs/04-development/setup.md). Short version:

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -e .
```

## The loop

SEPHIROTH used formal **Spec-Driven Development** (write a `docs/specs/SPEC-NNN`,
get it `Approved`, write failing tests from its acceptance criteria, then
implement) through Phase 16. That process — and the `docs/specs/*.md` files it
produced — was retired once the project moved to solo development: the
ceremony of writing and approving a spec before touching code made sense for
coordinating reviewers, not for one person. `docs/08-decisions/` (ADRs) still
records *why* a non-obvious decision was made; `docs/project-state.yaml`
still tracks what's actually implemented. Tests are still written
test-first for anything non-trivial — that habit didn't need the spec
ceremony to keep.

`docs/specs/contracts/` (JSON Schema exports of the Pydantic domain models) is
unrelated to the spec documents and still active — regenerate it with
`python scripts/export_contracts.py` whenever a contract type changes;
`tests/test_contracts_schema.py` fails on drift.

## Commit message format

Every commit from `AB#5` onward must match:

```
AB#<NNN> <body, max 50 words> [<type>]
```

Example: `AB#5 Switch commit format to the Azure Boards work item id [chore]`

- **`AB#<NNN>`** — the **Azure Boards work item id**, not a local counter.
  Create (or get assigned) the work item in Azure Boards first, then use its
  id. **Every commit that belongs to the same work item shares the same
  id** (e.g. all commits implementing AB#5 are `AB#5 ... [chore]`, `AB#5
  ... [docs]`, etc.). The repo's GitHub connection to Azure Boards (Project
  Settings → Boards → GitHub connections) auto-links any commit or PR
  mentioning `AB#<id>`, and `Fixes AB#<id>` / `Closes AB#<id>` transitions
  the work item on merge. See
  [ADR-020](docs/08-decisions/ADR-020-commit-format-azure-boards-id.md).
- **Body** — whitespace-split word count, excluding the `AB#<NNN>` prefix
  and the `[<type>]` suffix, capped at 50. Describe what changed, directly.
- **`[<type>]`** — exactly one of: `feat`, `fix`, `docs`, `chore`, `refactor`,
  `test`.
- **PR titles** must also start with the same `AB#<NNN>` as the commits
  inside them.

This applies **going forward only** — commits before `AB#5` keep their
`SF<NNN>` subjects (the format this one replaces,
[ADR-015](docs/08-decisions/ADR-015-commit-message-format.md), itself
introduced under the same "going forward only" rule over plain
Conventional Commits) and are never rewritten.

Dependabot's own commits are exempt from this format — it cannot produce an
`AB#<NNN> ... [<type>]` subject — via the `dependabot: ` prefix configured in
`.github/dependabot.yml` and matched by the validator, plus an author-email
check in the `commit-lint` job as a second, independent net.

**This is enforced, not just documented.** A local `commit-msg` git hook
gives fast feedback; the `commit-lint` job (part of the required CI pipeline,
see below) is the real gate — a PR with a malformed commit cannot be merged.
One-time setup per clone:

```bash
git config core.hooksPath .githooks
```

See [`.githooks/README.md`](.githooks/README.md) and
[ADR-020](docs/08-decisions/ADR-020-commit-format-azure-boards-id.md) for the
full rationale.

## Rebase, never merge

This repo only has **"Rebase and merge"** enabled on GitHub (merge commits
and squash are both turned off) — `main`'s history is linear by policy, one
commit per PR commit, no merge bubbles.

That repo setting only controls the button GitHub itself offers for landing
a PR; it does nothing to stop a merge commit living *inside* a branch's own
history. **Update a branch with the latest `main` using `git rebase origin/main`
(then `git push --force-with-lease`), never `git merge origin/main`.** A merge
commit inside a branch can replay strangely — or fail outright — when GitHub
tries to "rebase and merge" it, and it defeats the whole point of keeping
history linear even if the merge itself technically succeeds.

`--force-with-lease` (not bare `--force`) is safe here specifically because
it's your own unmerged feature branch — it refuses to overwrite anyone else's
push you haven't seen, unlike `--force`, which overwrites blindly.

**This is enforced, not just documented.** The `commit-lint` job (part of the
Code Review gate) fails the PR if `git log --merges` finds anything in the
branch's history — a PR with a merge commit cannot be merged, matching how
the commit-format rule itself is enforced.

## Required PR gates

`main` is branch-protected with exactly two required status checks — no
approval requirement, since this is a solo-maintainer repo and GitHub refuses
to count a PR author's own approval toward a required-review count:

- **Security** (`.github/workflows/security.yml`, `security-gate`) —
  gitleaks (secret scanning) + bandit HIGH-severity/HIGH-confidence findings.
  Blocking. `dependency-audit` (pip-audit/npm audit) runs in the same
  workflow but stays advisory — third-party CVEs with no available fix must
  never turn `main` permanently red. The same workflow also runs CodeQL
  (Python, JavaScript/TypeScript) and Semgrep (`platform/frontend`),
  advisory, both publishing SARIF to the repo's Security tab.
- **Code Review** (`.github/workflows/code-review.yml`, `code-review-gate`)
  — the automated stand-in for a human reviewer: lint, commit format,
  tests + coverage gate, the SDD spec-conformance check (every `Implemented`
  spec's acceptance criteria must exist in the test tree, contracts must not
  have drifted — see [the migration charter](docs/00-migration-charter.md)),
  frontend lint/test/build/e2e, and a real Docker build + boot smoke test
  under both dev and prod config. `docker-build-smoke-test` also fails on a
  CRITICAL OS-package CVE in the built image (Trivy, `vuln-type: os`,
  `ignore-unfixed: true`). `type-check` (mypy) runs alongside but is
  excluded from this gate — a pre-existing error baseline across the repo
  (DEBT-012, `docs/project-state.yaml`) blocks that promotion; see the
  job's own comment in `.github/workflows/code-review.yml` for the current
  count, and `pyproject.toml`'s `[tool.mypy-ratchet]` for the files that
  are held clean in the meantime.

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
- [ ] After merging a Dependabot `pip` PR: re-run
      `uv pip compile requirements.txt -o requirements.lock.txt` and commit
      the result under the same `SF<NNN>` — Dependabot bumps
      `requirements.txt` but the Dockerfile installs from
      `requirements.lock.txt`, which it cannot regenerate.

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
