#!/usr/bin/env python3
"""Documentation gates for the SEPHIROTH SDD system.

Prose documentation drifts because nothing fails when it lies. These checks are
the subset of "is the documentation still true?" that a machine can answer:

  1. every spec has valid front-matter (legal status, semver version)
  2. every acceptance criterion in an Implemented spec exists in the test tree
  3. Mermaid source lives only in docs/09-diagrams/ (copies diverge)
  4. every components.* key in project-state.yaml resolves to a real path
  5. every F-XXX referenced outside the registry exists in the registry
  6. relative links between markdown files resolve

Deliberately capped at stdlib + PyYAML. If a check needs another dependency, it
is too clever — delete it instead.

Usage:
    python scripts/docs_check.py            # report and exit non-zero on failure
    python scripts/docs_check.py --verbose  # also list what passed
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS = REPO_ROOT / "docs"
SPECS = DOCS / "specs"
DIAGRAMS = DOCS / "09-diagrams"
TESTS = REPO_ROOT / "tests"
PROJECT_STATE = DOCS / "project-state.yaml"
FEATURE_REGISTRY = DOCS / "03-features" / "feature-registry.md"

LEGAL_STATUSES = {"Draft", "Approved", "Implemented", "Superseded"}
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
AC_ID = re.compile(r"\bAC-\d{3}-\d{2}\b")
FEATURE_ID = re.compile(r"\bF-\d{3}\b")
FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
MERMAID_FENCE = re.compile(r"^```mermaid", re.MULTILINE)
MD_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")

# Root-level markdown that is allowed to exist outside docs/.
ROOT_MD_ALLOWLIST = {"README.md", "CLAUDE.md", "CONTRIBUTING.md", "CHANGELOG.md", "ARCHITECTURE.md"}


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.passed: list[str] = []

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def ok(self, message: str) -> None:
        self.passed.append(message)


def _front_matter(path: Path) -> dict | None:
    match = FRONT_MATTER.match(path.read_text())
    if not match:
        return None
    try:
        return yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        return None


def _markdown_files() -> list[Path]:
    files = sorted(DOCS.rglob("*.md")) if DOCS.exists() else []
    files += [REPO_ROOT / name for name in ROOT_MD_ALLOWLIST if (REPO_ROOT / name).exists()]
    return files


def check_spec_front_matter(report: Report) -> None:
    if not SPECS.exists():
        report.error(f"missing spec directory: {SPECS.relative_to(REPO_ROOT)}")
        return

    specs = sorted(SPECS.glob("SPEC-*.md"))
    if not specs:
        report.error("no specs found under docs/specs/")
        return

    for spec in specs:
        rel = spec.relative_to(REPO_ROOT)
        meta = _front_matter(spec)
        if meta is None:
            report.error(f"{rel}: missing or unparseable front-matter")
            continue
        status = meta.get("status")
        if status not in LEGAL_STATUSES:
            report.error(f"{rel}: illegal status {status!r} (expected one of {sorted(LEGAL_STATUSES)})")
        version = str(meta.get("version", ""))
        if not SEMVER.match(version):
            report.error(f"{rel}: version {version!r} is not semver")
        if meta.get("status") == "Superseded" and not meta.get("superseded_by"):
            report.error(f"{rel}: Superseded specs must name their successor in `superseded_by`")
    report.ok(f"{len(specs)} spec(s) have valid front-matter")


def check_acceptance_criteria(report: Report) -> None:
    """Every AC in an Implemented spec must appear in the test tree.

    Warn-only while a spec is Draft or Approved: the tests are written after
    approval, so demanding them earlier would invert the SDD order.
    """
    if not TESTS.exists():
        report.error("missing tests/ directory")
        return

    test_text = "\n".join(p.read_text() for p in TESTS.rglob("*.py"))
    checked = 0

    for spec in sorted(SPECS.glob("SPEC-*.md")):
        rel = spec.relative_to(REPO_ROOT)
        meta = _front_matter(spec) or {}
        status = meta.get("status")
        body = spec.read_text()
        ac_ids = sorted(set(AC_ID.findall(body)))
        if not ac_ids:
            report.warn(f"{rel}: no acceptance criteria declared")
            continue

        for ac in ac_ids:
            checked += 1
            if ac in test_text:
                continue
            message = f"{rel}: {ac} is not referenced anywhere under tests/"
            if status == "Implemented":
                report.error(message)
            else:
                report.warn(f"{message} (spec is {status}; required once Implemented)")

    report.ok(f"{checked} acceptance criteria checked against the test tree")


def check_mermaid_placement(report: Report) -> None:
    """Diagrams live once. A copied Mermaid block is a diagram that will
    silently diverge from the one people actually maintain."""
    offenders = []
    for path in _markdown_files():
        if DIAGRAMS.exists() and DIAGRAMS in path.parents:
            continue
        if MERMAID_FENCE.search(path.read_text()):
            offenders.append(str(path.relative_to(REPO_ROOT)))

    if offenders:
        report.error(
            "mermaid source found outside docs/09-diagrams/ (link to the diagram "
            f"instead of copying it): {offenders}"
        )
    else:
        report.ok("all mermaid source lives in docs/09-diagrams/")


def check_project_state(report: Report) -> None:
    if not PROJECT_STATE.exists():
        report.error("missing docs/project-state.yaml")
        return

    try:
        state = yaml.safe_load(PROJECT_STATE.read_text())
    except yaml.YAMLError as exc:
        report.error(f"docs/project-state.yaml does not parse: {exc}")
        return

    components = state.get("components") or {}
    missing = []
    count = 0
    for group, entries in components.items():
        for key in entries or {}:
            count += 1
            if not (REPO_ROOT / key).exists():
                missing.append(f"{group}.{key}")

    if missing:
        report.error(
            f"project-state.yaml component keys do not resolve to real paths (renamed or deleted?): {missing}"
        )
    else:
        report.ok(f"{count} project-state component paths resolve")


def check_feature_references(report: Report) -> None:
    if not FEATURE_REGISTRY.exists():
        report.error("missing docs/03-features/feature-registry.md")
        return

    known = set(FEATURE_ID.findall(FEATURE_REGISTRY.read_text()))
    if not known:
        report.error("feature registry declares no F-XXX ids")
        return

    dangling: dict[str, set[str]] = {}
    for path in _markdown_files():
        if path == FEATURE_REGISTRY:
            continue
        referenced = set(FEATURE_ID.findall(path.read_text()))
        unknown = referenced - known
        if unknown:
            dangling[str(path.relative_to(REPO_ROOT))] = unknown

    if dangling:
        report.error(f"references to features absent from the registry: {dangling}")
    else:
        report.ok(f"{len(known)} registry features; all external references resolve")


def check_relative_links(report: Report) -> None:
    """Offline only. External URL liveness is flaky and would turn someone
    else's outage into a red build."""
    broken: list[str] = []
    for path in _markdown_files():
        for target in MD_LINK.findall(path.read_text()):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            resolved = (path.parent / target.split("#")[0]).resolve()
            if not resolved.exists():
                broken.append(f"{path.relative_to(REPO_ROOT)} -> {target}")

    if broken:
        report.error(f"broken relative links: {broken}")
    else:
        report.ok("all relative markdown links resolve")


CHECKS = (
    check_spec_front_matter,
    check_acceptance_criteria,
    check_mermaid_placement,
    check_project_state,
    check_feature_references,
    check_relative_links,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", action="store_true", help="also list passing checks")
    args = parser.parse_args()

    report = Report()
    for check in CHECKS:
        check(report)

    if args.verbose:
        for item in report.passed:
            print(f"  ok      {item}")
    for item in report.warnings:
        print(f"  warn    {item}")
    for item in report.errors:
        print(f"  ERROR   {item}", file=sys.stderr)

    if report.errors:
        print(
            f"\ndocs_check: {len(report.errors)} error(s), {len(report.warnings)} warning(s)",
            file=sys.stderr,
        )
        return 1

    print(f"docs_check: OK ({len(report.passed)} checks, {len(report.warnings)} warning(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
