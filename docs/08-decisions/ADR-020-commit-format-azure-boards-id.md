# ADR-020 — Commit/PR format uses the Azure Boards work item id (`AB#<NNN>`)

**Status:** Accepted · **Date:** 2026-10-15

## Context

[ADR-015](ADR-015-commit-message-format.md) introduced `SF<NNN>` as a
project-local story id: a counter scanned out of `main`'s own git history
(`scripts/next-sf-id.sh`), with no connection to anything outside the repo.
Work is now tracked in Azure Boards, which already has its own id per work
item and — once a repo is connected under Project Settings → Boards → GitHub
connections — auto-links any commit or PR that mentions `AB#<id>` in its
message, and transitions the work item's state on `Fixes AB#<id>` /
`Closes AB#<id>`. Keeping `SF<NNN>` as the primary id meant maintaining two
parallel identifiers for the same unit of work (a local counter and an Azure
Boards id), manually cross-referencing them (as AB#4/PR #163 did, adding
`AB#4` as an afterthought in the commit body) instead of the Azure id being
the format natively.

## Decision

Every commit from `AB#5` onward must match `AB#<NNN> <body, max 50 words>
[<type>]`, same `<type>` enum as before (`feat`, `fix`, `docs`, `chore`,
`refactor`, `test`) and the same "every commit implementing the same unit of
work shares the same id" rule. `<NNN>` is the literal Azure Boards work item
id — not zero-padded, not a local counter — so a contributor creates (or is
given) the work item in Azure Boards *before* writing the first commit for
it; there is no `scripts/next-sf-id.sh` equivalent, since there is nothing
local left to scan or suggest.

PR titles must also start with the same `AB#<NNN>` (not just the commit
subjects) — Azure Boards scans both, and a PR title carrying the id makes
the link visible at a glance in the GitHub PR list, not just inside commit
history.

Same two-layer enforcement as ADR-015, same file
(`scripts/validate_commit_msg.py`, now matching `AB#(\d+)` instead of
`SF(\d{3,})`), same accepted gap: the validator checks *format* only — it
does not call the Azure DevOps API, so it cannot confirm `<NNN>` is a real,
open work item, only that the shape is right.

Applies **going forward only**: `SF001`-`SF081` keep their existing
subjects and are never rewritten, same rule ADR-015 itself was introduced
under. `scripts/generate_changelog.py` groups by whichever prefix a commit
actually carries (`AB#` going forward); it does not retroactively relabel
old `SF<NNN>` groups already written to `CHANGELOG.md`.

## Consequences

- `scripts/next-sf-id.sh` is deleted — there is no local id space left to
  suggest a next value for.
- `CONTRIBUTING.md`, `.githooks/README.md`, `.githooks/commit-msg`,
  `.github/PULL_REQUEST_TEMPLATE.md`, and `CLAUDE.md`'s commit-format bullet
  all point at this ADR instead of ADR-015 going forward.
- A contributor who skips creating the Azure Boards work item first has
  nothing to put in the prefix — unlike `SF<NNN>`, there is no local
  fallback counter to generate one from.
- `scripts/generate_changelog.py`'s per-run grouping label changed from
  `SF{story_id}` to `AB#{story_id}`; this only affects entries written after
  this change, not `CHANGELOG.md`'s existing `## SF0NN` headings.
