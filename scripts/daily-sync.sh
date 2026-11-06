#!/bin/bash
# Daily sync, run by the com.pfc.daily-sync launch agent at 5:00 AM and runnable by hand.
# It runs the syncs that need no person:
#   1. Trello completions to the repo   (what pfc-sync-trello does)
#   2. Gmail inbox to task reconcile    (Step 0 of pfc-email-triage; needs Claude for the Gmail connector)
#   3. Calendar cache                   (Step 1 of pfc-render-trello; writes data/calendar-cache.json
#                                        for the TRMNL pfc-week screen and the Trello Week list)
# Steps 2 and 3 each run claude -p, need Claude for a connector, and commit only their own file.
#
# Guards, in order. Each logs one line to /tmp/pfc-daily-sync.log and exits 0 without
# changing anything:
#   - the web writer's lock (data/.web-write.lock) is held for the whole run, so this
#     never races the web UI's buttons;
#   - the repo must be on PFC_WRITE_BRANCH (default main);
#   - the working tree must be clean, so no one's in-progress edits get committed;
#   - the branch must sync with origin (git pull --rebase, as web_write.py does).
# After the guards, each step's failure is logged and the next step still runs.
set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT" || exit 1

LOG="${PFC_DAILY_SYNC_LOG:-/tmp/pfc-daily-sync.log}"
# The scripts need PyYAML; the launch agent passes a python3 that has it.
PYTHON="${PFC_PYTHON:-python3}"

log() { printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >>"$LOG"; }

# Re-run this script under the web writer's lock (macOS has no flock command).
if [ -z "${PFC_DAILY_SYNC_LOCKED:-}" ]; then
  export PFC_DAILY_SYNC_LOCKED=1
  exec "$PYTHON" automations/scripts/with_write_lock.py --log "$LOG" -- /bin/bash "${BASH_SOURCE[0]}" "$@"
fi

OK_COUNT=0
FAIL_COUNT=0

# Every exit path writes the one summary line the web UI home page reads: a skipped
# run is DONE ok=0 fail=1 (the guard that skipped it already counted as a failure).
# shellcheck disable=SC2329  # called through the EXIT trap
finish() {
  log "DONE ok=$OK_COUNT fail=$FAIL_COUNT"
}
trap finish EXIT

# skip MESSAGE: log a guard failure and end the run.
skip() {
  log "FAIL $1, skipped"
  FAIL_COUNT=1
  exit 0
}

run_step() {
  local name="$1"
  shift
  log "START $name"
  if "$@" >>"$LOG" 2>&1; then
    log "OK $name"
    OK_COUNT=$((OK_COUNT + 1))
  else
    log "FAIL $name (exit $?)"
    FAIL_COUNT=$((FAIL_COUNT + 1))
  fi
}

# commit_paths MESSAGE PATH...: stage and commit only the named paths.
# shellcheck disable=SC2329  # called through run_step
commit_paths() {
  local msg="$1"
  shift
  git add -- "$@" && git commit -q -m "$msg" -- "$@"
}

branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null)"
if [ "$branch" != "${PFC_WRITE_BRANCH:-main}" ]; then
  skip "not on ${PFC_WRITE_BRANCH:-main} (on $branch)"
fi

if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
  skip "dirty tree"
fi

if ! sync_out="$("$PYTHON" automations/scripts/daily_sync_git.py sync 2>&1)"; then
  skip "sync with origin: $sync_out"
fi

# Step 1: Trello completions. Writes tasks and habits into the repo and prints a counters block.
run_step "trello sync" "$PYTHON" automations/scripts/trello_writeback.py sync

# Commit exactly the paths the sync changed (the tree was clean before it), then push.
changed=()
while IFS= read -r line; do
  [ -n "$line" ] && changed+=("${line:3}")
done < <(git status --porcelain)
if [ "${#changed[@]}" -gt 0 ]; then
  today="$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d')"
  run_step "commit trello sync" commit_paths "track: trello sync $today" "${changed[@]}"
  run_step "push trello sync" "$PYTHON" automations/scripts/daily_sync_git.py push
else
  log "OK trello sync changed nothing"
  OK_COUNT=$((OK_COUNT + 1))
fi

# Step 2: inbox to task reconcile. Auto permission mode, never a bypass mode.
run_step "email reconcile" claude -p \
  "/pfc-email-triage Run only Step 0, the inbox to task reconcile. Commit only the files you changed, by explicit path, with the skill's own commit message, then push. If you changed nothing, commit nothing." \
  --permission-mode auto

# Step 3: calendar cache. Only a live session can read Calendar; the TRMNL builder and
# the Trello timers read this committed snapshot and call it stale after about 26 hours.
run_step "calendar cache" claude -p \
  "/pfc-render-trello Run only Step 1: fetch the calendar events and write data/calendar-cache.json exactly as that step says. Do not run the render. If the file changed, commit only data/calendar-cache.json, by explicit path, with the message 'track: refresh calendar cache', then push. If it did not change, commit nothing." \
  --permission-mode auto

exit 0
