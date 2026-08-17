"""The `src/sephiroth` package is importable, and the contracts package is a leaf.

`pythonpath` in pyproject only serves pytest — it does not cover uvicorn,
`python -m`, `scripts/smoke_test.sh`, or Docker. The package is therefore made
importable by editable install (`pip install -e .`). If that install is missing
in CI, this module fails immediately and unambiguously rather than surfacing as
a confusing ImportError somewhere downstream.

See `docs/00-migration-charter.md` §4.
"""

import inspect

import pytest

import sephiroth
from sephiroth import contracts


def test_sephiroth_is_importable():
    assert isinstance(sephiroth.__version__, str)
    assert sephiroth.__version__


def test_version_matches_pyproject():
    """A drifting version makes CHANGELOG entries meaningless."""
    import tomllib
    from pathlib import Path

    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    declared = tomllib.loads(pyproject.read_text())["project"]["version"]
    assert sephiroth.__version__ == declared, (
        f"sephiroth.__version__ ({sephiroth.__version__}) != pyproject version ({declared})"
    )


def test_contracts_package_is_a_leaf():
    """`sephiroth.contracts` must not import from the rest of `sephiroth`.

    Keeping it dependency-free is what lets schema export, tests, and any
    future type generation consume the contracts without dragging in provider
    SDKs or the runtime. A single convenience import would quietly end that.
    """
    offenders: list[str] = []
    for _, module in inspect.getmembers(contracts, inspect.ismodule):
        name = module.__name__ or ""
        if not name.startswith("sephiroth.contracts"):
            continue
        source = inspect.getsource(module)
        for line in source.splitlines():
            stripped = line.strip()
            if not stripped.startswith(("import ", "from ")):
                continue
            if "sephiroth" in stripped and "sephiroth.contracts" not in stripped:
                offenders.append(f"{name}: {stripped}")

    assert not offenders, (
        f"sephiroth.contracts must stay a leaf package; found imports from the wider package: {offenders}"
    )


@pytest.mark.parametrize("name", ["contracts"])
def test_declared_subpackages_exist(name):
    """Guards against a coverage entry pointing at a package that was renamed."""
    import importlib

    assert importlib.import_module(f"sephiroth.{name}")
