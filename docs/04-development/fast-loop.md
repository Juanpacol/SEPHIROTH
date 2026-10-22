# The fast loop

How to get feedback in seconds while you work, and how the CI decides how much to run on a
pull request. (AB#47. The aim: stop waiting for checks a change cannot break, without
removing a check that could catch something.)

## While you work

Run only what your change can break:

```bash
scripts/check-changed.sh              # what differs from origin/main, committed or not
scripts/check-changed.sh --e2e        # ...and the browser specs you touched, at two screen sizes
scripts/check-changed.sh --full       # everything the CI runs, plus the build and every viewport
```

It uses the same rules as the CI (`scripts/ci_scope.py`), so "what changed needs" means the
same thing on your machine and on the PR. From the frontend folder, `npm run test:e2e:fast`
runs the whole browser suite at two sizes (desktop and a 320 px phone) and
`npm run test:e2e:changed` runs just the specs you touched.

| You are doing | Run |
|---|---|
| Editing a component or a page | `npm run test` for the unit tests, and `npx playwright test <spec> --project=desktop` for the spec that covers it |
| Judging how something looks | `next dev` (it reloads on save). Build only before the PR |
| A backend change | `pytest <the test file for it>`; `pytest -k <area>` for a wider look |
| About to open the PR | `scripts/check-changed.sh --full` once |

Two habits save the most time: check one screen size while you iterate and all four at the
end, and settle what a new section should look like (a screenshot or a sketch) before you build
it, because rebuilding a section costs more than every test run put together.

## What the CI runs on a pull request

Branch protection requires three checks, `quality`, `test` and `deploy-smoke`. Their names do
not change. What changes is which of their steps run, decided from the files in the PR:

| Check | Always runs | Runs only if the change needs it |
|---|---|---|
| `quality` | secret scan (gitleaks), ruff lint and format, bandit, commit-message format, no merge commits | frontend lint, unit tests and build: when a frontend file changed |
| `test` | nothing but the scope step | Postgres, migrations, the pytest suite with its coverage gate, the contract drift check: when backend files changed |
| `deploy-smoke` | nothing but the scope step | image build, the dev and prod boots, the bad-config check, the Trivy scan: when something that reaches the production image changed |

A check whose steps are skipped still reports success, and says in its log why it skipped.

| What changed | frontend | backend | image |
|---|:-:|:-:|:-:|
| Only `platform/frontend/**` | yes | no | no |
| Only `docs/**`, `*.md`, `.claude/**` | no | no | no |
| Python code, migrations, dependencies | no | yes | yes |
| Only `tests/**` or `scripts/**` | no | yes | no |
| Only the `Dockerfile` or `.dockerignore` | no | no | yes |
| `ci.yml` or `scripts/ci_scope.py` | yes | yes | yes |
| **Any file the rules do not know** | yes | yes | yes |
| A push to `main` | yes | yes | yes |

The last two rows are the safety net. A forgotten category can only cost time: an unknown file
turns everything on, and `main` always runs everything because it gates the deploy. The rules
live in `scripts/ci_scope.py` and are tested in `tests/test_ci_scope.py`;
`tests/test_ci_workflow.py` fails if a job is renamed, loses its time limit, or has an expensive
step that is not gated (or a safety step that is).

Also: every job has a time limit, so a hung step fails in at most 25 minutes instead of holding
the PR; and a newer push to a PR cancels that PR's older run. Runs on `main` are never cancelled.

## What was not removed

- No required check was dropped, and the branch protection rules are unchanged (including the
  rule that a PR must be up to date with `main`).
- The full browser suite still runs nightly and on demand (`extended-checks.yml`); it does not
  run on a PR. Run `--full` yourself before you open one that changes how something looks.
- Coverage, contract drift, secret scanning, bandit, the image smoke boots and the CVE scan all
  still run whenever a change could affect them.

## Writing browser specs that do not flake

Two things made specs fail now and then for reasons unrelated to what they test, and both have
a helper in `platform/frontend/e2e/fixtures/`:

- The site scrolls smoothly, and a second `scrollTo` during a smooth scroll can be dropped in
  WebKit. Import `test` from `./fixtures/test` instead of `@playwright/test`: it turns smooth
  scrolling off and changes nothing else.
- A "scroll to the end" that goes before the pictures further up have loaded lands short,
  because the page grows as they arrive. Use `scrollToEnd` from `./fixtures/scroll`, which keeps
  going until the page stops growing (`scrollToTop` and `scrollToY` jump at once).

Do not wait a fixed time for the page to be ready: poll for the thing you are about to assert.
