#!/usr/bin/env bash
# Invariant: no AI co-author trailers or AI branding in commit messages.
set -euo pipefail

if [[ "${1:-}" == "--help" ]]; then
  echo "Usage: $0 [worktree_dir] [base_branch]"
  echo "Fails when a commit in origin/<base_branch>..HEAD carries an AI co-author or AI branding."
  exit 0
fi

WORKTREE_DIR="${1:-.}"
BASE_BRANCH="${2:-master}"

commits=$(git -C "$WORKTREE_DIR" log --format="%h %s%n%b" "origin/$BASE_BRANCH..HEAD")
[[ -z "$commits" ]] && exit 0

ai_names='claude|anthropic|copilot|openai|chatgpt|gpt-[0-9]|gemini|cursor|codex|devin'
# A co-author is flagged by its email, or when the display name is a tool name
# followed only by model or product words. Matching a bare name anywhere would
# flag human co-authors such as "Devin Lee".
ai_emails='@anthropic\.com|@openai\.com|@cursor\.(com|sh)|copilot|devin-ai|gemini|codex'
model_words='ai|agent|assistant|code|opus|sonnet|haiku|fable|pro|flash|[0-9][0-9.]*'
coauthor_email="co-authored-by:[^<]*<[^>]*($ai_emails)[^>]*>"
coauthor_name="co-authored-by:[[:space:]]*($ai_names)([[:space:]]+($model_words))*[[:space:]]*(<|$)"
violations=$(echo "$commits" | grep -iE "$coauthor_email|$coauthor_name|generated (with|by) .*($ai_names)" || true)

if [[ -n "$violations" ]]; then
  echo "FAIL: AI co-author or AI branding found in commit messages:"
  echo "$violations"
  exit 1
fi
exit 0
