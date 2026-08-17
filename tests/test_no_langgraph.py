"""LangGraph is gone (`docs/08-decisions/ADR-001-remove-langgraph.md`).

Scans source files under `intelligence/`, `platform/`, and `src/` for a
`langgraph` import, rather than relying on `requirements.txt` alone — a stray
import would still work locally if langgraph happened to be present in a
developer's environment from a previous install, so the guarantee needs to be
about the source tree, not just the declared dependency list.

Verifies AC-003-05 (`docs/specs/SPEC-003-agent-runtime.md`).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract

REPO_ROOT = Path(__file__).resolve().parents[1]
SCAN_DIRS = ["intelligence", "platform", "src"]
IMPORT_RE = re.compile(r"^\s*(from|import)\s+langgraph\b", re.MULTILINE)


def _python_files():
    for scan_dir in SCAN_DIRS:
        root = REPO_ROOT / scan_dir
        if not root.exists():
            continue
        yield from root.rglob("*.py")


def test_no_source_file_imports_langgraph():
    offenders = []
    for path in _python_files():
        if IMPORT_RE.search(path.read_text()):
            offenders.append(str(path.relative_to(REPO_ROOT)))

    assert not offenders, f"langgraph import found in: {offenders}"


def test_langgraph_is_not_a_declared_dependency():
    requirements = (REPO_ROOT / "requirements.txt").read_text()
    assert "langgraph" not in requirements.lower(), (
        "langgraph still listed in requirements.txt — ADR-001 removed it in Phase 3"
    )
