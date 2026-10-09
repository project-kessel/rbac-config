#!/usr/bin/env bash
# Invariant: no ' -- ' (space-dash-dash-space) separators in added prose.
# Scans .md and .py files. Fenced code blocks and inline code spans in markdown
# are excluded, as are POSIX end-of-options markers in shell-like lines.
set -euo pipefail

if [[ "${1:-}" == "--help" ]]; then
  echo "Usage: $0 [worktree_dir] [base_branch]"
  echo "Fails when a line added since origin/<base_branch> uses ' -- ' as a prose separator (.md, .py)."
  exit 0
fi

WORKTREE_DIR="${1:-.}"
BASE_BRANCH="${2:-master}"

changed_files=$(git -C "$WORKTREE_DIR" diff --name-only "origin/$BASE_BRANCH" -- '*.md' '*.py')
[[ -z "$changed_files" ]] && exit 0

# Line numbers inside fenced code blocks. An unclosed fence yields no
# exclusions, so malformed markup cannot hide violations in real prose.
lines_in_code_blocks() {
  local output
  output=$(awk '
    /^[[:space:]]*```/ || /^[[:space:]]*~~~/ {
      if (in_block) { in_block = 0; lines = lines NR "\n"; next }
      else          { in_block = 1; lines = lines NR "\n"; next }
    }
    in_block { lines = lines NR "\n" }
    END { if (!in_block) printf "%s", lines; else exit 1 }
  ' "$1") || output=""
  printf '%s' "$output"
}

# Double-backtick spans may contain single backticks, so strip them first.
strip_inline_code() {
  # shellcheck disable=SC2016
  sed -E 's/``(([^`]|`[^`])*)``//g; s/`[^`]*`//g'
}

is_posix_end_of_opts() {
  echo "$1" | grep -qE '(^|[^[:alnum:]_])(git|grep|sed|awk|find|rm|cp|mv|ls|cat|docker|kubectl|npm|pip|make|bash|sh|xargs|ssh|rsync|curl|tar|diff|python3?)([^[:alnum:]_]).* -- '
}

# Emits "line_number<TAB>content" for every added line of a unified diff.
extract_added_line_numbers() {
  awk '
    /^@@ / {
      s = $0
      sub(/^@@ -[0-9,]* \+/, "", s)
      sub(/[^0-9].*/, "", s)
      cur = s + 0
      if (cur < 1) cur = 1
      next
    }
    /^\+\+\+/ { next }
    /^---/    { next }
    /^\+/     { print cur "\t" substr($0, 2); cur++ ; next }
    /^-/      { next }
    { cur++ }
  '
}

violations=""
while IFS= read -r f; do
  [[ -f "$WORKTREE_DIR/$f" ]] || continue

  diff_output=$(git -C "$WORKTREE_DIR" diff "origin/$BASE_BRANCH" -- "$f" || true)
  [[ -z "$diff_output" ]] && continue

  is_md=false
  [[ "$f" == *.md ]] && is_md=true

  code_block_lines=""
  if $is_md; then
    code_block_lines=$(lines_in_code_blocks "$WORKTREE_DIR/$f")
  fi

  while IFS=$'\t' read -r line_num content; do
    [[ -z "$line_num" ]] && continue

    if $is_md && echo "$code_block_lines" | grep -qxF "$line_num"; then
      continue
    fi

    cleaned=$(echo "$content" | strip_inline_code)

    if echo "$cleaned" | grep -qF ' -- '; then
      if ! $is_md && is_posix_end_of_opts "$cleaned"; then
        continue
      fi
      violations+="  $f:$line_num: $content"$'\n'
    fi
  done <<< "$(echo "$diff_output" | extract_added_line_numbers)"
done <<< "$changed_files"

if [[ -n "$violations" ]]; then
  echo "FAIL: ' -- ' separator found in prose (use a colon, comma, period, or parentheses):"
  echo "$violations"
  exit 1
fi
exit 0
