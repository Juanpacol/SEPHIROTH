"""Regression guard for scripts/validate_commit_msg.py's _SKIP_PATTERN.

Minimal on purpose: covers only the changelog-bot exemption added to fix the
self-triggering changelog loop (see .github/workflows/changelog.yml's header
comment). A fuller suite (Dependabot's own exemption, adversarial near-miss
cases) lands separately.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from validate_commit_msg import validate  # noqa: E402


def test_changelog_bot_commit_is_exempt():
    assert validate("changelog-bot: update CHANGELOG.md with entries grouped by story") == []


def test_changelog_bot_commit_never_needs_an_sf_id():
    """The whole point of the exemption: this subject must not require (or
    accept) a real SF<NNN> — that's what caused the loop in the first place."""
    assert validate("SF040 update CHANGELOG.md with entries grouped by story [chore]") == []
    # The bot's actual commit shape — no SF<NNN>, no [type] suffix — still passes.
    assert validate("changelog-bot: update CHANGELOG.md") == []


def test_similar_but_unprefixed_subject_still_fails():
    """Guard against the exemption silently widening — this must still need
    the normal SF<NNN> ... [<type>] shape."""
    assert validate("update CHANGELOG.md with entries grouped by story") != []


def test_merge_and_revert_still_exempt():
    assert validate("Merge branch 'main'") == []
    assert validate('Revert "SF001 something [chore]"') == []
