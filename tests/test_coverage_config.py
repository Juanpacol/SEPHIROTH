"""Every `src/sephiroth` package is covered by the coverage gate.

The dangerous failure mode of `fail_under` is silent: forget to add a new
package to `coverage.run.source` and the new code becomes invisible to the
gate, so CI stays green while the migration goes unverified. Adding it too
early only turns CI red, which is loud and therefore harmless.

This converts the silent failure into a loud one. See
`docs/00-migration-charter.md` §5.
"""

import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src" / "sephiroth"


def _coverage_source() -> list[str]:
    config = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    return config["tool"]["coverage"]["run"]["source"]


def _sephiroth_packages() -> list[str]:
    return sorted(p.name for p in SRC_ROOT.iterdir() if p.is_dir() and (p / "__init__.py").exists())


def test_every_sephiroth_package_is_in_coverage_source():
    source = _coverage_source()
    missing = [pkg for pkg in _sephiroth_packages() if f"src/sephiroth/{pkg}" not in source]
    assert not missing, (
        f"packages absent from [tool.coverage.run] source: {missing}. "
        "Add each as its own entry in the same pull request that creates it, "
        "or its code is invisible to the 87% gate."
    )


def test_coverage_source_has_no_wildcard_sephiroth_root():
    """`src/sephiroth` wholesale would silently absorb future subpackages and
    reintroduce exactly the failure this file exists to prevent."""
    source = _coverage_source()
    assert "src/sephiroth" not in source, (
        "list sephiroth packages individually, never the root — a wildcard root "
        "hides future subpackages from the gate"
    )


def test_coverage_source_entries_all_exist():
    """A stale entry pointing at a deleted directory makes the gate quietly
    weaker; coverage ignores paths it cannot find."""
    missing = [entry for entry in _coverage_source() if not (REPO_ROOT / entry).exists()]
    assert not missing, f"[tool.coverage.run] source entries do not exist: {missing}"
