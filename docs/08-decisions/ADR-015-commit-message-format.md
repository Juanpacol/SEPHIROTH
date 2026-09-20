# ADR-015 — Enforced commit-message format

**Status:** Accepted · **Date:** 2026-09-16

## Context

No commit-message convention was documented or enforced. Recent history used
ad-hoc Conventional Commits (`fix(ci): ...`, `chore(workflows): ...`), and
`main` accepted direct pushes with no PR gate. A lightweight, greppable,
sequential-ish audit trail was requested, with real enforcement — a
documentation-only rule has no teeth.

## Decision

Every commit from `SF001` onward must match `SF<NNN> <body, max 50 words>
[<type>]`, `<type>` one of `feat`, `fix`, `docs`, `chore`, `refactor`, `test`.
`<NNN>` identifies the user story/feature, not the individual commit — every
commit implementing that story shares the same id (`SF001 ... [chore]`,
`SF001 ... [docs]`, etc.); a new story gets the next id. Applies going
forward only; prior history is not rewritten.

Two-layer enforcement, both calling the same `scripts/validate_commit_msg.py`
(stdlib-only Python) so they cannot drift apart:

1. **Local `commit-msg` hook** (`.githooks/commit-msg`, opt-in per clone via
   `git config core.hooksPath .githooks`) — fast feedback, bypassable with
   `--no-verify` or simply never installed.
2. **`commit-lint` job** in `.github/workflows/ci.yml`, required via GitHub
   branch protection on every pull request against `main` — the actual gate.
   It diffs `git log --format=%s origin/${{ github.base_ref }}..HEAD` rather
   than the PR event's commit list (capped/paginated on large PRs) and
   validates every subject, skipping merge/revert **and Dependabot-authored**
   commits.

Branch protection on `main` (require PR before merging, require `commit-lint`
to pass, no force-push/deletion, no bypass for admins) is a manual,
one-time GitHub configuration step — not something a commit can accomplish.

**Explicitly accepted gap: `<NNN>` uniqueness is not enforced.** CI cannot
rewrite a commit message after the fact without rewriting history, which
this decision deliberately avoids. The validator checks *format* only
(regex shape, word count, type enum, and that all commits carry a valid
`SF<NNN>` — not that the number is unique) — it cannot see other developers'
unmerged branches, so it cannot guarantee a story id is globally unique.
`scripts/next-sf-id.sh` scans `main` and suggests the next unused story id,
but is advisory only. Two branches starting a new story at the same time can
independently pick the same id; whichever merges second lands a duplicate
story id in `main` history. This is tolerated: the format's purpose is a
human-scannable trail grouping a story's commits together, not a strict
primary key. A future enhancement — a post-merge job that *warns* (never
blocks) on duplicates — is possible but out of scope here.

## Consequences

- A contributor who never runs the one-time hook setup still gets stopped at
  the PR stage, just later than local commit time.
- `SF<NNN>` numbers may occasionally collide or land out of order across
  concurrently-merged branches; this is a known, accepted limitation, not a
  bug to be triaged if observed.
- Adding a new allowed type requires updating `ALLOWED_TYPES` in
  `scripts/validate_commit_msg.py` and the list in CONTRIBUTING.md together
  — they are two literal lists, not derived from one source, since the
  validator has no CONTRIBUTING.md-parsing logic.
- `commit-message.prefix` in `.github/dependabot.yml` and `_SKIP_PATTERN` in
  `scripts/validate_commit_msg.py` are two literal strings that must change
  together — the same shape as the `ALLOWED_TYPES`/CONTRIBUTING.md coupling
  above. Changing one without the other silently re-blocks Dependabot.
