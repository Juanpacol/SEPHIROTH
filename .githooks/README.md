# Git hooks

Version-controlled hooks, since `.git/hooks/` itself is never committed.

**One-time setup** (per clone):

```bash
git config core.hooksPath .githooks
```

- `commit-msg` — validates the commit subject against the `SF<NNN> <body> [<type>]` format via `scripts/validate_commit_msg.py`. See [CONTRIBUTING.md](../CONTRIBUTING.md#commit-message-format) for the full rule and [ADR-015](../docs/08-decisions/ADR-015-commit-message-format.md) for the rationale.

This hook is a fast local check, not the enforcement mechanism — it can be bypassed with `--no-verify` or simply never installed. The `commit-lint` job in `.github/workflows/ci.yml`, required on every pull request, is the real gate.
