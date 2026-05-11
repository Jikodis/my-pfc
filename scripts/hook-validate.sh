#!/usr/bin/env bash
# PostToolUse hook — runs scripts/validate.sh after edits to structured files.
#
# Claude Code invokes this with a JSON payload on stdin describing the tool call.
# We filter for edits to data/*.ndjson, config/*_schema.yaml, and SKILL.md files
# (anything the validator actually checks) so we don't run on every text edit.
#
# Exits 2 on validation failure to surface output back to Claude. Silent on success.

set -u

payload=$(cat)
file_path=$(jq -r '.tool_input.file_path // empty' <<<"$payload" 2>/dev/null)

case "$file_path" in
  */data/*.ndjson|*/config/*_schema.yaml|*/.agents/skills/*/SKILL.md|*/.claude/skills/*/SKILL.md)
    project_dir="${CLAUDE_PROJECT_DIR:-$(git -C "$(dirname "$file_path")" rev-parse --show-toplevel 2>/dev/null)}"
    [ -n "$project_dir" ] || exit 0
    [ -x "$project_dir/scripts/validate.sh" ] || exit 0

    if ! output=$("$project_dir/scripts/validate.sh" 2>&1); then
      {
        echo "❌ Repo validation failed after editing $file_path:"
        echo "$output"
        echo ""
        echo "Fix the issues above before continuing."
      } >&2
      exit 2
    fi
    ;;
esac

exit 0
