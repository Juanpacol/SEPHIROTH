"""The documentation gates run in the test suite, not only in CI.

`scripts/docs_check.py` is what makes the SDD system binding rather than
aspirational. Running it here as well means a contributor finds a broken link
or a dangling feature reference locally, in the same command they already run,
instead of discovering it from a red pipeline.

Verifies AC-000-01, AC-000-02, AC-000-03, AC-000-04 and AC-000-06
(`docs/specs/SPEC-000-spec-process.md`).
"""

from pathlib import Path

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


# --------------------------------------------------------------------------
# Frontend acceptance criteria.
#
# `docs_check.check_acceptance_criteria` greps `tests/` — the pytest tree — for
# every AC id in an Implemented spec. A spec whose behaviour is proven by vitest
# instead would therefore fail the gate, and the tempting fix (point the grep at
# the frontend too) would let an id "pass" by appearing in any file at all,
# including a comment.
#
# This manifest is the honest version: each frontend AC names the exact suite
# that proves it, and the test below asserts the file exists and really contains
# the id. That satisfies the grep for the right reason, and a renamed or deleted
# suite fails here rather than rotting silently.
# --------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND = REPO_ROOT / "platform" / "frontend"

FRONTEND_ACCEPTANCE_CRITERIA = {
    # SPEC-017 — Interface Foundations
    "AC-017-01": "components/__tests__/sheet.test.tsx",
    "AC-017-02": "components/__tests__/sheet.test.tsx",
    "AC-017-03": "components/__tests__/sheet.test.tsx",
    "AC-017-04": "components/__tests__/sheet.test.tsx",
    "AC-017-05": "components/__tests__/sheet.test.tsx",
    "AC-017-06": "components/__tests__/mobile-nav.test.tsx",
    "AC-017-07": "components/__tests__/mobile-nav.test.tsx",
    "AC-017-08": "components/__tests__/mobile-nav.test.tsx",
    "AC-017-09": "components/__tests__/data-list.test.tsx",
    "AC-017-10": "components/__tests__/data-list.test.tsx",
    "AC-017-11": "components/__tests__/data-list.test.tsx",
    "AC-017-12": "lib/__tests__/responsive.test.ts",
    "AC-017-13": "lib/__tests__/responsive.test.ts",
    "AC-017-14": "lib/__tests__/responsive.test.ts",
    # SPEC-018 — Unified Clinical Tasks
    "AC-018-17": "app/tasks/__tests__/page.test.tsx",
    "AC-018-18": "app/tasks/__tests__/page.test.tsx",
}


@pytest.mark.parametrize("ac_id,suite", sorted(FRONTEND_ACCEPTANCE_CRITERIA.items()))
def test_frontend_acceptance_criteria_name_a_real_suite(ac_id: str, suite: str):
    path = FRONTEND / suite
    assert path.exists(), f"{ac_id} names {suite}, which does not exist"
    assert ac_id in path.read_text(), f"{suite} does not reference {ac_id}"
