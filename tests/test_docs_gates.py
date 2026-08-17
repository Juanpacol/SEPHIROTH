"""The documentation gates run in the test suite, not only in CI.

`scripts/docs_check.py` is what makes the SDD system binding rather than
aspirational. Running it here as well means a contributor finds a broken link
or a dangling feature reference locally, in the same command they already run,
instead of discovering it from a red pipeline.

Verifies AC-000-01, AC-000-02, AC-000-03, AC-000-04 and AC-000-06
(`docs/specs/SPEC-000-spec-process.md`).
"""

import pytest

from scripts.docs_check import (
    Report,
    check_acceptance_criteria,
    check_feature_references,
    check_mermaid_placement,
    check_project_state,
    check_relative_links,
    check_spec_front_matter,
)

pytestmark = pytest.mark.spec


def _run(check) -> Report:
    report = Report()
    check(report)
    return report


def test_spec_front_matter_is_valid():
    """AC-000-01 — every spec declares a legal status and a semver version."""
    assert not _run(check_spec_front_matter).errors


def test_implemented_specs_have_their_criteria_covered():
    """AC-000-02 — an Implemented spec may not declare an acceptance criterion
    that no test references. Warnings are expected for Draft/Approved specs,
    whose tests are written after approval."""
    assert not _run(check_acceptance_criteria).errors


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
