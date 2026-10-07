#!/usr/bin/env bash
# Runs every scripts/invariants/*.sh check against the current branch.
set -euo pipefail

if [[ "${1:-}" == "--help" ]]; then
  echo "Usage: $0 [base_branch]"
  echo "Runs all invariant checks against origin/<base_branch> (default: master)."
  exit 0
fi

BASE_BRANCH="${1:-master}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Without the base ref every check would scan nothing and pass.
if ! git -C "$REPO_ROOT" rev-parse --verify --quiet "origin/$BASE_BRANCH" >/dev/null; then
  echo "origin/$BASE_BRANCH not found; fetch it first (git fetch origin $BASE_BRANCH)." >&2
  exit 2
fi

failed=0
for script in "$REPO_ROOT"/scripts/invariants/*.sh; do
  name=$(basename "$script" .sh)
  if bash "$script" "$REPO_ROOT" "$BASE_BRANCH"; then
    echo "PASS: $name"
  else
    echo "FAIL: $name"
    failed=$((failed + 1))
  fi
done

if [[ "$failed" -gt 0 ]]; then
  echo "$failed invariant check(s) failed."
  exit 1
fi
echo "All invariant checks passed."
