#!/bin/bash
# Daily sync, run by the com.pfc.daily-sync launch agent and runnable by hand.
# The agent fires every hour from 5:00 AM to 10:00 PM. automations/scripts/daily_sync_gate.py
# turns that into one run a day: it waits (no log line but one WAIT) while github.com or
# api.trello.com is unreachable, which is what a 5:00 AM firing on a sleeping Mac finds;
# after a run with a failed step, the next firings redo only the steps that have not
# logged OK today, up to 3 runs a day; after a run with no failure, it is silent until
# tomorrow. `daily-sync.sh --force` runs every step now, whatever today's log says.
# It runs the syncs that need no person:
#   1. Trello completions to the repo   (what pfc-sync-trello does)
#   2. Gmail inbox to task reconcile    (Step 0 of pfc-email-triage; needs Claude for the Gmail connector)
#   3. Calendar cache                   (Step 1 of pfc-render-trello; writes data/calendar-cache.json
#                                        for the TRMNL pfc-week screen and the Trello Week list)
#   4. Calendar-derived habits          (derive_calendar_habits.py reads that cache; no Claude)
# Steps 2 and 3 each run claude -p, need Claude for a connector, and commit only their own file.
#
# Opt-in: it runs headless Claude, so it does nothing unless PFC_DAILY_SYNC=1 is set in
# .env (or the environment). docs/install/daily-sync.md has the install steps.
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
PYTHON="${PFC_PYTHON:-/opt/homebrew/bin/python3}"

log() { printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >>"$LOG"; }

export PFC_DAILY_SYNC_LOG="$LOG"

# Opt-in flag, checked before anything else so an unconfigured clone never runs Claude.
if [ "${PFC_DAILY_SYNC:-}" != "1" ] && ! grep -qE "^PFC_DAILY_SYNC=1" .env 2>/dev/null; then
  [ -t 1 ] && echo "daily sync is off: set PFC_DAILY_SYNC=1 in .env to turn it on"
  exit 0
fi
FORCE=""
[ "${1:-}" = "--force" ] && FORCE="--force"

if [ -z "${PFC_DAILY_SYNC_LOCKED:-}" ]; then
  # Not now: already finished today, out of attempts, or no network. No DONE line is
  # written, so the home page keeps showing the last real result.
  if ! reason="$("$PYTHON" automations/scripts/daily_sync_gate.py should-run $FORCE)"; then
    # Said only to a person at a terminal: launchd sends stdout to the log, and an
    # hourly line there would bury the real runs.
    [ -t 1 ] && echo "daily sync not run: $reason (use --force to run anyway)"
    exit 0
  fi
  # Re-run this script under the web writer's lock (macOS has no flock command), and
  # under caffeinate so the Mac does not go back to sleep halfway through a step.
  export PFC_DAILY_SYNC_LOCKED=1
  awake=()
  [ -x /usr/bin/caffeinate ] && awake=(/usr/bin/caffeinate -i)
  ${awake[@]+"${awake[@]}"} "$PYTHON" automations/scripts/with_write_lock.py --log "$LOG" -- /bin/bash "${BASH_SOURCE[0]}" "$@"
  # with_write_lock.py logs a busy lock or a timeout kill as one FAIL line and no
  # summary; add the DONE line the home page reads (a skipped or killed run is fail=1).
  if tail -n 1 "$LOG" 2>/dev/null | grep -qE ' FAIL (write lock busy|command timed out)'; then
    log "DONE ok=0 fail=1"
  fi
  exit 0
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

# run_once NAME COMMAND...: run_step, unless NAME already logged OK today (an earlier
# run today got that far). A step that is skipped this way still counts as OK, so a
# retry that fixes the one failed step ends the day with fail=0.
run_once() {
  if [ -z "$FORCE" ] && "$PYTHON" automations/scripts/daily_sync_gate.py step-done "$1"; then
    OK_COUNT=$((OK_COUNT + 1))
    return 0
  fi
  run_step "$@"
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

# The guards passed: this is a real run, and it counts toward the day's 3 attempts.
"$PYTHON" automations/scripts/daily_sync_gate.py begin

# Step 1: Trello completions. Writes tasks and habits into the repo and prints a counters block.
run_once "trello sync" "$PYTHON" automations/scripts/trello_writeback.py sync

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
run_once "email reconcile" claude -p \
  "/pfc-email-triage Run only Step 0, the inbox to task reconcile. Commit only the files you changed, by explicit path, with the skill's own commit message, then push. If you changed nothing, commit nothing." \
  --permission-mode auto

# Step 3: calendar cache. Only a live session can read Calendar; the TRMNL builder and
# the Trello timers read this committed snapshot and call it stale after about 26 hours.
run_once "calendar cache" claude -p \
  "/pfc-render-trello Run only Step 1 (not Step 1b): fetch the calendar events and write data/calendar-cache.json exactly as that step says. Do not run the render. If the file changed, commit only data/calendar-cache.json, by explicit path, with the message 'track: refresh calendar cache', then push. If it did not change, commit nothing." \
  --permission-mode auto

# Step 4: habits whose reps are calendar events (auto_derived + calendar: in
# config/habit_schema.yaml, e.g. a weekly class) log themselves from the cache Step 3 just
# wrote. The cache covers yesterday, so last night's class is logged this morning.
habit_logs=(7-habits/_data/habits-daily.ndjson 7-habits/_data/habits-monthly.ndjson)
run_once "calendar habits" "$PYTHON" automations/scripts/derive_calendar_habits.py
if [ -n "$(git status --porcelain -- "${habit_logs[@]}")" ]; then
  today="$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d')"
  run_step "commit calendar habits" commit_paths "habit: calendar log $today" "${habit_logs[@]}"
  run_step "push calendar habits" "$PYTHON" automations/scripts/daily_sync_git.py push
fi

exit 0
