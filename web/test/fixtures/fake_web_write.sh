#!/bin/bash
# Stands in for automations/scripts/web_write.py so the write routes' tests never
# touch a repo. FAKE_WRITE_MODE picks the behavior; each mode prints what the real
# script prints for that case and exits with its code. The argv is echoed back as
# the action and first argument (an id, a day, or an area or room key), and
# the whole argv is written to FAKE_WRITE_ARGS_FILE when that is set, one entry per
# line, which is how the day routes' tests check what each route sends.
#
#   ok        a saved change, pushed, exit 0
#   unpushed  a saved change the push could not deliver, exit 0
#   unchanged nothing to change, exit 0
#   unknown   no record with that id, exit 2
#   refused   a record the action may not change, exit 2
#   locked    the lock is held, exit 3
#   invalid   the validator failed, exit 4
#   crash     a traceback on stderr, exit 1
#   junk      text that is not JSON, exit 0
#   slow      sleeps 3 seconds, then as ok
#   stubborn  starts a 30 second sleep it does not clean up after, writes
#             "<own pid> <sleep pid>" to FAKE_WRITE_PIDS_FILE, and waits for it
#   branch    the repo is on another branch, exit 3
#   nohook    the repo's pre-commit hook is not installed, exit 3
#   late      the commit exists and the push hangs; on SIGTERM prints the saved
#             commit as not pushed and exits 0, the way the real script does
set -u

action="${1:-}"
id="${2:-}"
[ -n "${FAKE_WRITE_ARGS_FILE:-}" ] && printf '%s\n' "$@" > "$FAKE_WRITE_ARGS_FILE"

saved() {  # saved <pushed> <push_error json> <message>
  printf '{"ok": true, "action": "%s", "id": "%s", "title": "Call the dentist", "email_linked": true, "commit": "abc1234", "pushed": %s, "push_error": %s, "changed": true, "message": "%s"}\n' \
    "$action" "$id" "$1" "$2" "$3"
}

case "${FAKE_WRITE_MODE:-ok}" in
  ok) saved true null 'Saved.' ;;
  unpushed) saved false '"fatal: No configured push destination."' 'Saved. Not pushed yet.' ;;
  unchanged)
    printf '{"ok": true, "action": "%s", "id": "%s", "title": "Call the dentist", "email_linked": false, "commit": null, "pushed": false, "push_error": null, "changed": false, "message": "Already done."}\n' "$action" "$id"
    ;;
  unknown) echo '{"ok": false, "reason": "not_found", "error": "No open task with that id."}'; exit 2 ;;
  refused) echo '{"ok": false, "reason": "refused", "error": "That focus is retired."}'; exit 2 ;;
  branch) echo '{"ok": false, "reason": "wrong_branch", "error": "The repo is on branch feature, not main; nothing was changed."}'; exit 3 ;;
  nohook) echo '{"ok": false, "reason": "no_precommit_hook", "error": "The repo'"'"'s pre-commit hook is not installed; see docs/install/web-ui.md."}'; exit 3 ;;
  locked) echo '{"ok": false, "reason": "busy", "error": "Another change is still being saved."}'; exit 3 ;;
  invalid) echo '{"ok": false, "reason": "invalid", "error": "tasks.ndjson: record task-x violates schema"}'; exit 4 ;;
  crash)
    echo 'Traceback (most recent call last): /Users/someone/secret/path.py' >&2
    echo '{"ok": false, "reason": "error", "error": "The change could not be saved."}'
    exit 1
    ;;
  junk) echo 'this is not json'; exit 0 ;;
  slow)
    # The sleep is stopped with the script, or it would hold stdout open after it.
    sleep 3 &
    naptime=$!
    trap 'kill "$naptime" 2>/dev/null; exit 143' TERM
    wait "$naptime"
    saved true null 'Saved.'
    ;;
  late)
    sleep 30 &
    naptime=$!
    late_exit() {
      kill "$naptime" 2>/dev/null
      saved false '"The push timed out; the commit is saved and will push next time."' 'Saved. Not pushed yet.'
      exit 0
    }
    trap late_exit TERM
    wait "$naptime"
    ;;
  stubborn)
    # No trap: only a signal to the whole process group stops the sleep.
    sleep 30 &
    [ -n "${FAKE_WRITE_PIDS_FILE:-}" ] && echo "$$ $!" > "$FAKE_WRITE_PIDS_FILE"
    wait
    saved true null 'Saved.'
    ;;
esac
