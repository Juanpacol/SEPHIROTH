"""The documentation gates run in the test suite, not only in CI.

`scripts/docs_check.py` catches a broken link or a dangling feature reference
locally, in the same command a contributor already runs, instead of
discovering it from a red pipeline. The formal SDD spec-frontmatter/
acceptance-criteria checks this file used to also exercise were removed along
with `docs/specs/SPEC-NNN-*.md` when the project retired that process
(`CONTRIBUTING.md`) — what remains here still applies to every other doc.
"""

import pytest

from scripts.docs_check import (
    Report,
    check_feature_references,
    check_mermaid_placement,
    check_project_state,
    check_relative_links,
)

pytestmark = pytest.mark.spec


def _run(check) -> Report:
    report = Report()
    check(report)
    return report


def test_mermaid_source_lives_only_in_the_diagrams_directory():
    """AC-000-03 — a copied diagram is a diagram that will diverge from the one
    people maintain."""
    assert not _run(check_mermaid_placement).errors


def test_project_state_paths_resolve():
    """AC-000-04 — project-state.yaml cannot describe modules that no longer
    exist under the names it uses."""
    assert not _run(check_project_state).errors


def test_feature_references_resolve():
    """AC-000-06 — every F-XXX mentioned outside the registry exists in it."""
    assert not _run(check_feature_references).errors


def test_relative_documentation_links_resolve():
    """Offline only; external URL liveness is deliberately not checked."""
    assert not _run(check_relative_links).errors
