#!/usr/bin/env python3
"""Auto-generate CHANGELOG.md entries grouped by user story (SF<NNN>).

Reuses `validate_commit_msg`'s shape regex — the single source of truth for
what an `SF<NNN> <body> [<type>]` subject looks like — so this can never
group commits differently than the commit-msg hook/CI validate them.

State: `scripts/.changelog_cursor` holds the SHA of the last commit already
folded into CHANGELOG.md. Each run only processes `<cursor>..HEAD`, so a
commit is never entered twice and the script is safe to run on every push to
main. First run (no cursor file yet) seeds the cursor at the current HEAD
instead of backfilling all of history — this tool starts documenting new
work going forward, not rewriting the existing hand-written changelog.

Intended to run in CI on every push to main (see
`.github/workflows/changelog.yml`), which commits the result back. Also
runnable locally (`python scripts/generate_changelog.py`) for a preview —
it only ever touches CHANGELOG.md and the cursor file, both of which `git
diff` shows before you'd commit them yourself.
"""

from __future__ import annotations

import subprocess
import sys
from collections import OrderedDict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from validate_commit_msg import _SHAPE_PATTERN  # noqa: E402

REPO_ROOT = Path(__file__).parent.parent
CHANGELOG_PATH = REPO_ROOT / "CHANGELOG.md"
CURSOR_PATH = REPO_ROOT / "scripts" / ".changelog_cursor"
UNRELEASED_HEADING = "## [Unreleased]\n"


def _run(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout


def _current_head() -> str:
    return _run("rev-parse", "HEAD").strip()


def _commits_since(cursor: str | None) -> list[tuple[str, str]]:
    """(sha, subject) pairs, oldest first, for `cursor..HEAD` (or all of
    history if `cursor` is None — never happens in the normal flow, since
    the caller seeds the cursor before this is reached)."""
    range_spec = f"{cursor}..HEAD" if cursor else "HEAD"
    out = _run("log", range_spec, "--format=%H%x1f%s", "--reverse")
    pairs = []
    for line in out.splitlines():
        if not line:
            continue
        sha, _, subject = line.partition("\x1f")
        pairs.append((sha, subject))
    return pairs


def _group_by_story(commits: list[tuple[str, str]]) -> "OrderedDict[str, list[str]]":
    """Maps SF id -> ordered list of '<body> [<type>]' lines. A commit whose
    subject doesn't match the shape (shouldn't happen — commit-lint already
    gates every PR merge — but a direct push to main isn't gated, see
    `code-review.yml`'s commit-lint job condition) is silently skipped rather
    than crashing changelog generation over it."""
    groups: "OrderedDict[str, list[str]]" = OrderedDict()
    for _sha, subject in commits:
        match = _SHAPE_PATTERN.match(subject)
        if not match:
            continue
        story_id, body, kind = match.group(1), match.group(2), match.group(3)
        groups.setdefault(f"SF{story_id}", []).append(f"{body} [{kind}]")
    return groups


def _render(groups: "OrderedDict[str, list[str]]") -> str:
    blocks = []
    for story_id, lines in groups.items():
        bullets = "\n".join(f"- {line}" for line in lines)
        blocks.append(f"## {story_id}\n\n{bullets}\n")
    return "\n".join(blocks)


def main() -> int:
    cursor = CURSOR_PATH.read_text().strip() if CURSOR_PATH.exists() else None
    head = _current_head()

    if cursor is None:
        # First run: start documenting from here on, don't backfill the
        # hand-written history above.
        CURSOR_PATH.write_text(head + "\n")
        print(f"No cursor found — seeded at HEAD ({head[:8]}). Nothing to generate yet.")
        return 0

    if cursor == head:
        print("Nothing new since the last run.")
        return 0

    groups = _group_by_story(_commits_since(cursor))
    if not groups:
        CURSOR_PATH.write_text(head + "\n")
        print("No SF<NNN> commits in range (only merges/reverts?) — cursor advanced, nothing written.")
        return 0

    rendered = _render(groups)
    current = CHANGELOG_PATH.read_text()
    if UNRELEASED_HEADING not in current:
        print(
            f"error: {CHANGELOG_PATH} has no '{UNRELEASED_HEADING.strip()}' heading to insert after",
            file=sys.stderr,
        )
        return 1

    updated = current.replace(UNRELEASED_HEADING, UNRELEASED_HEADING + "\n" + rendered, 1)
    CHANGELOG_PATH.write_text(updated)
    CURSOR_PATH.write_text(head + "\n")
    print(
        f"Added {len(groups)} stor{'y' if len(groups) == 1 else 'ies'} to CHANGELOG.md: {', '.join(groups)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
