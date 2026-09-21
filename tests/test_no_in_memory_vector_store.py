"""SPEC-030 AC-030-06 / ADR-017 NG-5: no fallback to the in-memory vector
store when Postgres is unreachable — `InMemoryVectorStore` is deleted
outright, not kept as a degraded mode, so nothing under the application
tree may still import it.
"""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SEARCH_DIRS = ["src", "intelligence", "platform", "data"]


def _imports_in_memory_vector_store(path: Path) -> bool:
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and "data.vectors" in node.module:
            return True
        if isinstance(node, ast.Import):
            if any("data.vectors" in alias.name for alias in node.names):
                return True
    return False


def test_no_module_imports_data_vectors():
    offenders = []
    for base in SEARCH_DIRS:
        for path in (REPO_ROOT / base).rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            if _imports_in_memory_vector_store(path):
                offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == []
