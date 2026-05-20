#!/usr/bin/env bash
# Stop hook — session ledger.
#
# Fires at end of every assistant turn. Prints a concise ledger of uncommitted
# canonical-state files so the assistant has an external check it can reconcile
# against its closing session summary — and so the user can see at a glance
# whether any work from this turn is still uncommitted.
#
# Silent when there are no uncommitted changes in canonical paths.
#
# Output goes to stdout and is fed back to the assistant as additional context
# for the next turn.

set -u
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"

cd "$PROJECT_DIR" 2>/dev/null || exit 0
[ -d .git ] || exit 0

# Canonical-state paths whose uncommitted state should be visible at end of
# every turn. Mirror the post-commit hook's mirrored-file list plus structural
# files (skills, agents, settings, docs).
canonical_paths=(
  "AGENTS.md"
  "CLAUDE.md"
  ".claude/skills"
  ".claude/agents"
  ".claude/settings.json"
  "1-values"
  "2-areas"
  "3-visions"
  "4-projects"
  "5-actions"
  "6-habits"
  "data"
  "0-me"
  "config"
  "docs"
  "scripts"
  "automations"
)

# Filter to paths that actually exist so git doesn't error.
existing_paths=()
for p in "${canonical_paths[@]}"; do
  [ -e "$p" ] && existing_paths+=("$p")
done

[ ${#existing_paths[@]} -gt 0 ] || exit 0

uncommitted=$(git status --porcelain -- "${existing_paths[@]}" 2>/dev/null)
[ -n "$uncommitted" ] || exit 0

count=$(printf '%s\n' "$uncommitted" | wc -l | tr -d ' ')

cat <<EOF
=== SESSION LEDGER (Stop hook) ===

$count uncommitted file(s) in canonical paths. Reconcile any closing session
summary against this list — every uncommitted change should be accounted for
(Done / In progress / Pending / Blocked).

EOF

printf '%s\n' "$uncommitted" | sed 's/^/  /'

cat <<EOF

If a file above is missing from the session summary, add it. If a row in the
summary is not in this ledger or in this turn's tool calls, drop it.
EOF
