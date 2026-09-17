#!/usr/bin/env bash
# Suggests the next SF<NNN> commit id by scanning history for the highest
# existing one. Purely informational: never writes files, never fails the
# build, and does NOT guarantee global uniqueness across unmerged branches
# (see docs/08-decisions/ADR-015-commit-message-format.md).
set -euo pipefail

if git rev-parse --verify origin/main >/dev/null 2>&1; then
  ref="origin/main"
elif git rev-parse --verify main >/dev/null 2>&1; then
  ref="main"
else
  echo "SF001"
  exit 0
fi

max=0
while IFS= read -r line; do
  if [[ "$line" =~ ^SF([0-9]+) ]]; then
    n=$((10#${BASH_REMATCH[1]}))
    if (( n > max )); then
      max=$n
    fi
  fi
done < <(git log "$ref" --format=%s)

next=$((max + 1))
printf "SF%03d\n" "$next"
