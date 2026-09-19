"""Guards the `dependabot: ` exemption in `scripts/validate_commit_msg.py`.

The exemption is a deliberate hole in the commit-lint gate (ADR-015 amendment,
SF017) — every Dependabot-authored subject must be exempt, but the exemption
must not degrade into a bare `^Bump ` heuristic that lets a human-typed commit
through. `scripts/` is not a package (see CONTRIBUTING.md), so the module is
imported the same way `scripts/generate_changelog.py` imports `_SHAPE_PATTERN`
— `sys.path.insert` then a direct module import.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from validate_commit_msg import validate  # noqa: E402


def test_dependabot_prefixed_bump_is_exempt() -> None:
    assert validate("dependabot: Bump next from 14.2.15 to 14.2.36") == []


def test_dependabot_prefixed_update_is_exempt() -> None:
    assert validate("dependabot: Update fastapi requirement from >=0.115 to >=0.118") == []


def test_dependabot_group_update_is_exempt() -> None:
    assert validate("dependabot: Bump the npm group with 3 updates") == []


def test_dependabot_scoped_prefix_is_exempt() -> None:
    assert validate("dependabot(deps): Bump actions/checkout from 4 to 5") == []


def test_bare_bump_without_prefix_is_not_exempt() -> None:
    # Proves the exemption keys off the literal prefix, not a `^Bump ` hole.
    assert validate("Bump next from 14.2.15 to 14.2.36") != []


def test_capitalised_human_typed_dependabot_is_not_exempt() -> None:
    assert validate("Dependabot: Bump something") != []


def test_dependabot_prefix_without_colon_space_is_not_exempt() -> None:
    assert validate("dependabot upgrade of foo") != []


def test_merge_commit_still_exempt() -> None:
    assert validate("Merge branch 'main'") == []


def test_revert_commit_still_exempt() -> None:
    assert validate('Revert "SF001 something [chore]"') == []


def test_wellformed_subject_still_passes() -> None:
    assert validate("SF009 Add CI security tooling [chore]") == []


def test_malformed_subject_without_suffix_still_fails() -> None:
    assert validate("SF009 Add CI security tooling") != []
