"""The mypy ratchet: files that are type-clean stay type-clean.

Whole-repo mypy is advisory (DEBT-012) and still reports a real backlog, so it
cannot gate anything — a permanently-red gate is one nobody reads. This is the
half that can gate: the subset already at zero errors, enforced by the suite the
`test` CI job runs anyway.

Two failure modes, both loud:

  * a clean file regresses -> `test_clean_files_have_no_mypy_errors` fails with
    mypy's own output,
  * the file list and the strictness overrides drift apart -> the parity test
    fails. They are separate lists because mypy needs module names and the
    checker needs paths, so parity is asserted rather than assumed.

To add a file: get `mypy <file>` clean, then add it to BOTH
`[tool.mypy-ratchet].files` and `[[tool.mypy.overrides]].module`. Never remove
one to make a build pass.
"""

import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Roots from `[tool.mypy].mypy_path`, longest first so "platform/api/x.py"
#: resolves against "platform" before the "." that also matches it.
_MODULE_ROOTS = ("platform", "src", ".")


def _config() -> dict:
    return tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())


def _clean_files() -> list[str]:
    return _config()["tool"]["mypy-ratchet"]["files"]


def _strict_modules() -> set[str]:
    """Module names from the `[[tool.mypy.overrides]]` block that raises
    strictness on the clean set — identified by the flags it sets, not by
    position, so an unrelated override block added later doesn't break this."""
    overrides = _config()["tool"]["mypy"]["overrides"]
    strict = [o for o in overrides if o.get("check_untyped_defs")]
    assert len(strict) == 1, f"expected exactly one strict override block, found {len(strict)}"
    return set(strict[0]["module"])


def _module_name(path: str) -> str:
    """ "platform/api/routers/rag.py" -> "api.routers.rag".

    `explicit_package_bases` + `mypy_path = "src:.:platform"` means a file is
    named relative to its root, so `platform/` and `src/` are stripped but
    `intelligence/` (which sits at ".") is not.
    """
    stem = path[: -len(".py")]
    for root in _MODULE_ROOTS:
        prefix = "" if root == "." else root + "/"
        if prefix and stem.startswith(prefix):
            stem = stem[len(prefix) :]
            break
    return stem.replace("/", ".")


def test_clean_file_list_is_not_empty_and_exists():
    files = _clean_files()
    assert files, "the ratchet is empty — it would pass vacuously"
    missing = [f for f in files if not (REPO_ROOT / f).is_file()]
    assert missing == [], f"listed in [tool.mypy-ratchet] but not on disk: {missing}"


def test_strict_overrides_cover_exactly_the_clean_files():
    """The two lists describe one set. Without this, a file could be in the
    ratchet while the stricter flags never apply to it, and the gate would be
    weaker than it looks."""
    expected = {_module_name(f) for f in _clean_files()}
    actual = _strict_modules()
    assert actual == expected, (
        "[tool.mypy-ratchet].files and the strict [[tool.mypy.overrides]] have drifted.\n"
        f"  only in overrides: {sorted(actual - expected)}\n"
        f"  only in files:     {sorted(expected - actual)}"
    )


def test_clean_files_have_no_mypy_errors():
    """The ratchet itself."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "mypy", *_clean_files()],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except FileNotFoundError:  # pragma: no cover - mypy is in requirements-dev
        pytest.skip("mypy not installed")

    # Filter to the listed files rather than trusting the exit code. Naming a
    # file on mypy's command line also pulls in what it imports, and whether
    # errors in *those* get reported varies with the environment — this test
    # passed locally and failed in CI on exactly that difference, with errors
    # from intelligence/nlp and data/rag that the ratchet never claimed to own.
    # The advisory `type-check` job is what covers the rest; this one's contract
    # is only ever "these files are clean".
    owned = tuple(_clean_files())
    offenders = [line for line in result.stdout.splitlines() if line.startswith(owned) and ": error:" in line]
    assert offenders == [], (
        "a file in [tool.mypy-ratchet] regressed. Fix the type error — do not "
        "remove the file from the list.\n\n" + "\n".join(offenders)
    )

    # A non-zero exit with nothing attributable to our files is usually mypy
    # itself failing to run (bad config, crash). Silence there would make the
    # whole gate vacuous, so surface it.
    if result.returncode != 0 and not result.stdout.strip():
        raise AssertionError("mypy did not run:\n" + result.stdout + result.stderr)
