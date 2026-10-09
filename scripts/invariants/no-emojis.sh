#!/usr/bin/env bash
# Invariant: no emojis in lines added to code, configs, or documentation.
set -euo pipefail

if [[ "${1:-}" == "--help" ]]; then
  echo "Usage: $0 [worktree_dir] [base_branch]"
  echo "Fails when a line added since origin/<base_branch> contains an emoji."
  exit 0
fi

WORKTREE_DIR="${1:-.}"
BASE_BRANCH="${2:-master}"

file_globs=('*.md' '*.py' '*.sh' '*.yml' '*.yaml' '*.json' '*.ksl' '*.txt')

changed_files=$(git -C "$WORKTREE_DIR" diff --name-only "origin/$BASE_BRANCH" -- "${file_globs[@]}")
[[ -z "$changed_files" ]] && exit 0

# perl rather than `grep -P`, which BSD grep on macOS does not support.
emoji_re='[\x{1F000}-\x{1FAFF}\x{2600}-\x{27BF}\x{2B00}-\x{2BFF}\x{FE0F}]'

violations=""
while IFS= read -r f; do
  [[ -f "$WORKTREE_DIR/$f" ]] || continue
  result=$(git -C "$WORKTREE_DIR" diff "origin/$BASE_BRANCH" -- "$f" \
    | perl -CSD -ne "print if /^\+(?!\+\+)/ && /$emoji_re/" || true)
  if [[ -n "$result" ]]; then
    violations+="  $f: $result"$'\n'
  fi
done <<< "$changed_files"

if [[ -n "$violations" ]]; then
  echo "FAIL: Emoji characters found in added lines:"
  echo "$violations"
  exit 1
fi
exit 0
