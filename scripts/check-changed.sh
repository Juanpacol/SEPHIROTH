#!/usr/bin/env bash
# Runs only the checks that what you changed can break. The local twin of the CI's scope
# (scripts/ci_scope.py): the same rules decide what "changed" needs.
#
#   scripts/check-changed.sh                 # what changed since origin/main
#   scripts/check-changed.sh --base main     # ...since another ref
#   scripts/check-changed.sh --e2e           # also the browser specs you touched, at two sizes
#   scripts/check-changed.sh --e2e-only      # only those browser specs (used by `npm run test:e2e:changed`)
#   scripts/check-changed.sh --full          # everything the CI runs, plus the build and every viewport
#
# Use it while you work. Run --full once before you open the PR. The CI is the authority:
# this is only there so you find out in seconds, not after the PR is up.
set -uo pipefail

cd "$(git rev-parse --show-toplevel)" || exit 1
BASE="origin/main"
E2E=0
E2E_ONLY=0
FULL=0
while [ $# -gt 0 ]; do
  case "$1" in
    --base) BASE="$2"; shift ;;
    --e2e) E2E=1 ;;
    --e2e-only) E2E=1; E2E_ONLY=1 ;;
    --full) FULL=1; E2E=1 ;;
    -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

# The Python to use: $PYTHON, this checkout's .venv, the main checkout's .venv (a worktree has none
# of its own), then whatever python3 is on the PATH.
COMMON="$(cd "$(git rev-parse --git-common-dir)/.." && pwd)"
PY="${PYTHON:-}"
for candidate in ".venv/bin/python" "$COMMON/.venv/bin/python"; do
  [ -z "$PY" ] && [ -x "$candidate" ] && PY="$candidate"
done
PY="${PY:-python3}"

# Everything that differs from BASE: committed, staged or not, and new files. (The CI only sees
# commits; here you want to know before you commit.)
CHANGED="$(git diff --name-only "$BASE"...HEAD; git diff --name-only HEAD; git ls-files --others --exclude-standard)"
CHANGED="$(echo "$CHANGED" | sort -u | sed '/^$/d')"

# shellcheck disable=SC2086
eval "$($PY scripts/ci_scope.py --files $CHANGED | sed 's/^/SCOPE_/')"
# shellcheck disable=SC2154
echo "scope since $BASE: frontend=$SCOPE_frontend backend=$SCOPE_backend image=$SCOPE_image"
status=0
run() { echo "--> $*"; "$@" || status=1; }

if [ "$E2E_ONLY" -eq 0 ] && [ "$SCOPE_backend" = "true" ]; then
  run "$PY" -m ruff check .
  run "$PY" -m ruff format --check .
  if [ "$FULL" -eq 1 ]; then
    run env CI=true PYTHONPATH=.:platform "$PY" -m pytest -q
    run "$PY" scripts/export_contracts.py --check
  else
    TESTS="$(echo "$CHANGED" | grep -E '^tests/test_.*\.py$' | sort -u | tr '\n' ' ')"
    if [ -n "$TESTS" ]; then
      # shellcheck disable=SC2086
      run env CI=true PYTHONPATH=.:platform "$PY" -m pytest -q $TESTS
    else
      echo "(backend code changed but no test file did: run with --full, or pytest -k <area>)"
    fi
  fi
fi

if [ "$SCOPE_frontend" = "true" ]; then
  cd platform/frontend || exit 1
  if [ "$E2E_ONLY" -eq 0 ]; then
    run npx tsc --noEmit
    run npm run lint
    run npm run test
    [ "$FULL" -eq 1 ] && run npm run build
  fi
  if [ "$E2E" -eq 1 ]; then
    if [ "$FULL" -eq 1 ]; then
      run npx playwright test
    else
      SPECS="$(echo "$CHANGED" | grep -E '^platform/frontend/e2e/.*\.spec\.ts$' | sed 's#^platform/frontend/##' | sort -u | tr '\n' ' ')"
      if [ -n "$SPECS" ]; then
        # The built app is what Playwright serves: build first if it is older than the sources.
        [ -d .next ] || run npm run build
        # shellcheck disable=SC2086
        run npx playwright test --project=desktop --project=narrow $SPECS
      else
        echo "(no e2e spec changed: pick one with 'npx playwright test <file> --project=desktop')"
      fi
    fi
  fi
fi

[ "$status" -eq 0 ] && echo "ok" || echo "something failed"
exit "$status"
