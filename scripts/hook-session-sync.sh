#!/usr/bin/env bash
# SessionStart hook: bring this clone level with origin before the session edits anything.
#
# Why: when more than one clone commits to main (a laptop and a server, say), whichever
# pushes second is rejected, and commits can sit unpushed on one clone unnoticed. The
# automated writers level with origin before they push (automations/scripts/repo_sync.py);
# this hook does the same when a Claude session starts, so the session edits the newest
# copy of every file and its first push lands.
#
# Same rules as repo_sync.py: no prompts, no stash, never abort someone else's rebase:
#   clean tree          -> git pull --rebase (a conflict is aborted and reported)
#   uncommitted edits   -> git fetch + fast-forward only (the edits are never touched)
#   rebase in progress  -> reported and left alone
# Prints only when there is something to say; a clone already level stays silent.

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$PROJECT_DIR" || exit 0
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0

export GIT_TERMINAL_PROMPT=0
export GIT_SSH_COMMAND="${GIT_SSH_COMMAND:-ssh -o BatchMode=yes -o ConnectTimeout=10}"

say() { printf '=== REPO SYNC (origin) ===\n%s\n' "$1"; }
in_rebase() {
  [ -d "$(git rev-parse --git-path rebase-merge)" ] || [ -d "$(git rev-parse --git-path rebase-apply)" ]
}
branch_line() { git status -sb 2>/dev/null | head -1; }

if in_rebase; then
  say "A git rebase is in progress in this clone. Finish it (git rebase --continue) or abort it (git rebase --abort) before committing anything."
  exit 0
fi
git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' >/dev/null 2>&1 || exit 0

BEFORE=$(git rev-parse HEAD)
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  if ! OUT=$(git fetch --quiet 2>&1); then
    say "Could not reach origin: $(printf '%s\n' "$OUT" | head -1). Working on the copy already here."
    exit 0
  fi
  if ! OUT=$(git merge --ff-only --quiet '@{upstream}' 2>&1); then
    say "Origin has commits this clone lacks, and the uncommitted edits here mean it could not fast-forward ($(branch_line)). Nothing was changed. Commit or set aside the edits, then run: git pull --rebase"
    exit 0
  fi
else
  if ! OUT=$(git pull --rebase --quiet 2>&1); then
    if in_rebase; then git rebase --abort >/dev/null 2>&1; fi
    LINE=$(printf '%s\n' "$OUT" | grep -m1 CONFLICT || printf '%s\n' "$OUT" | head -1)
    say "Could not bring this clone level with origin: $LINE — the clone is unchanged ($(branch_line)). Resolve by hand: git pull --rebase, fix the conflict, git rebase --continue."
    exit 0
  fi
fi

AFTER=$(git rev-parse HEAD)
if [ "$BEFORE" != "$AFTER" ]; then
  N=$(git rev-list --count "$BEFORE..$AFTER" 2>/dev/null || echo "?")
  SUBJECTS=$(git log --format='%s' "$BEFORE..$AFTER" 2>/dev/null | head -3 | tr '\n' ';' | sed 's/;$//; s/;/; /g')
  say "Pulled $N commit(s) from origin; now at $(git rev-parse --short HEAD). Latest: $SUBJECTS"
fi
