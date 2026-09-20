#!/usr/bin/env python3
"""Validate a commit subject against the SEPHIROTH commit-message format.

Required shape: ``SF<NNN> <body, max 50 words> [<type>]``

Single source of truth for both enforcement layers: the local
``.githooks/commit-msg`` hook (fast feedback) and the ``commit-lint`` job in
``.github/workflows/ci.yml`` (the real, unbypassable gate). Both call this
script so the two layers can never drift apart.

See docs/08-decisions/ADR-015-commit-message-format.md for the full
rationale, including the accepted gap: this script validates *format* only —
it does not, and cannot, guarantee that <NNN> is globally unique across
branches.

Two automated authors are exempt from the shape check, same as merge/revert
commits — neither can produce an `SF<NNN> ... [<type>]` subject:

- Dependabot-authored subjects (the `dependabot: ` prefix configured in
  `.github/dependabot.yml`). That prefix and `commit-message.prefix` in
  `.github/dependabot.yml` are two literal strings that must change together.
- `changelog-bot: ` (the prefix `.github/workflows/changelog.yml` commits its
  CHANGELOG.md updates under) — it MUST NOT be given a real SF<NNN> id either:
  an earlier version claimed one via `next-sf-id.sh`, which made the bot's own
  commit look like a user story to the next run and caused a self-triggering
  loop (29 near-duplicate "Auto-update" commits before this was caught — see
  the changelog.yml header comment for the full story).
"""

from __future__ import annotations

import argparse
import re
import sys

ALLOWED_TYPES = ("feat", "fix", "docs", "chore", "refactor", "test")
MAX_BODY_WORDS = 50

_SKIP_PATTERN = re.compile(r'^(Merge\b|Revert "|dependabot(?:\([^)]*\))?: |changelog-bot: )')
_SHAPE_PATTERN = re.compile(r"^SF(\d{3,})\s+(.+)\s+\[(" + "|".join(ALLOWED_TYPES) + r")\]$")
_HAS_PREFIX = re.compile(r"^SF\d{3,}\s")
_HAS_SUFFIX = re.compile(r"\[([^\]]*)\]\s*$")


def validate(subject: str) -> list[str]:
    """Return a list of human-readable errors; empty list means valid."""
    subject = subject.rstrip("\n")

    if _SKIP_PATTERN.match(subject):
        return []

    match = _SHAPE_PATTERN.match(subject)
    if match:
        body = match.group(2)
        word_count = len(body.split())
        if word_count > MAX_BODY_WORDS:
            return [f"Commit body has {word_count} words, exceeds the {MAX_BODY_WORDS}-word limit: '{body}'"]
        return []

    errors: list[str] = []
    if not _HAS_PREFIX.match(subject):
        errors.append(
            "Missing or malformed 'SF<NNN>' prefix (e.g. 'SF001'). "
            "Run scripts/next-sf-id.sh for the suggested next id."
        )

    suffix_match = _HAS_SUFFIX.search(subject)
    if not suffix_match:
        errors.append("Missing trailing type suffix, e.g. '[chore]' at the very end of the subject line.")
    elif suffix_match.group(1) not in ALLOWED_TYPES:
        errors.append(f"Type suffix '[{suffix_match.group(1)}]' is not one of: {', '.join(ALLOWED_TYPES)}")

    if not errors:
        errors.append(
            f"Commit message does not match required format 'SF<NNN> <body> [<type>]'. Got: '{subject}'"
        )

    return errors


def _read_subject_from_file(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.readline()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "commit_msg_file",
        nargs="?",
        help="Path to a commit-message file (first line only is read)",
    )
    parser.add_argument(
        "--message",
        help="A commit subject string to validate directly (used by CI)",
    )
    args = parser.parse_args(argv)

    if args.message is not None:
        subject = args.message
    elif args.commit_msg_file:
        subject = _read_subject_from_file(args.commit_msg_file)
    else:
        parser.error("either a commit-msg file path or --message is required")
        return 2

    errors = validate(subject)
    if errors:
        print(f"Invalid commit subject: '{subject.rstrip()}'", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
