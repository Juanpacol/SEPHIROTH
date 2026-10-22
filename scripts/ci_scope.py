"""Decides which parts of the CI a change needs to run.

    python scripts/ci_scope.py --base <ref>        # files changed since <ref>
    python scripts/ci_scope.py --all               # everything (a push to main)
    python scripts/ci_scope.py --files a b c       # explicit list, for tests

Prints `frontend=true|false`, `backend=true|false` and `image=true|false`, and appends the
same lines to `$GITHUB_OUTPUT` when it is set, so a workflow step can read them.

The rule that matters is the last one: **a file this script does not recognise turns every
output on.** The three required checks keep their names and always report; what changes is
which of their steps run. Skipping is only ever for files known to be irrelevant, so a
forgotten category costs time and never costs a missed check.

  frontend  platform/frontend/**                       (build, lint, unit tests)
  backend   the Python code, its tests and its tooling (pytest against Postgres, contracts)
  image     what ends up in the production image       (the Docker build and smoke boot)
  docs      docs/**, markdown, editor settings         (needs none of the three)
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from fnmatch import fnmatch

FRONTEND = ("platform/frontend/*",)

# Python code and the things only it uses. `tests/*` is backend but not in the image.
BACKEND_ONLY = (
    "src/*",
    "platform/api/*",
    "platform/auth/*",
    "platform/core/*",
    "platform/data/*",
    "intelligence/*",
    "data/*",
    "migrations/*",
    "real_data/*",
    "alembic.ini",
    "pyproject.toml",
    "requirements*.txt",
    "docker-compose*.yml",
)
BACKEND_TESTS_ONLY = ("tests/*", "scripts/*", "conftest.py", "pytest.ini")
# Reaches the production image as well.
IMAGE_ONLY = ("Dockerfile", ".dockerignore")

DOCS = ("docs/*", "*.md", ".claude/*", ".github/ISSUE_TEMPLATE/*", ".github/PULL_REQUEST_TEMPLATE*")

# Files that change what the CI itself does: they have to be proven by the CI they change.
CI_ITSELF = (".github/workflows/ci.yml", "scripts/ci_scope.py")


@dataclass(frozen=True)
class Scope:
    frontend: bool
    backend: bool
    image: bool

    def lines(self) -> list[str]:
        return [
            f"{name}={'true' if getattr(self, name) else 'false'}"
            for name in ("frontend", "backend", "image")
        ]


def _matches(path: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch(path, p) for p in patterns)


def scope_for(files: list[str]) -> Scope:
    """What a change touching `files` needs. An empty list needs nothing; an unknown file needs everything."""
    frontend = backend = image = False
    for raw in files:
        path = raw.strip().lstrip("./")
        if not path:
            continue
        if _matches(path, CI_ITSELF):
            return Scope(True, True, True)
        # `*.md` is docs wherever it sits, but a frontend path wins first: the frontend's own
        # markdown (its CLAUDE.md, a README in public/) is docs too and needs no build.
        if _matches(path, DOCS):
            continue
        if _matches(path, FRONTEND):
            frontend = True
        elif _matches(path, BACKEND_ONLY):
            backend = image = True
        elif _matches(path, IMAGE_ONLY):
            image = True
        elif _matches(path, BACKEND_TESTS_ONLY):
            backend = True
        else:
            # Not a file this script knows about: run everything rather than guess.
            return Scope(True, True, True)
    return Scope(frontend, backend, image)


def changed_files(base: str) -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...HEAD"], capture_output=True, text=True, check=True
    ).stdout
    return [line for line in out.splitlines() if line]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--base", help="the ref the change is measured against, e.g. origin/main")
    group.add_argument("--all", action="store_true", help="run everything")
    group.add_argument("--files", nargs="*", help="an explicit list of changed files")
    args = parser.parse_args(argv)

    if args.all:
        scope = Scope(True, True, True)
    elif args.files is not None:
        scope = scope_for(args.files)
    else:
        try:
            scope = scope_for(changed_files(args.base))
        except (subprocess.CalledProcessError, FileNotFoundError) as err:
            # Cannot tell what changed (no history, no git): run everything.
            print(f"could not diff against {args.base} ({err}); running everything", file=sys.stderr)
            scope = Scope(True, True, True)

    for line in scope.lines():
        print(line)
    target = os.environ.get("GITHUB_OUTPUT")
    if target:
        with open(target, "a", encoding="utf-8") as fh:
            fh.write("\n".join(scope.lines()) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
