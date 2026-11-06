#!/bin/bash
# Opens the local web UI in the browser. The daily summary runs this as its last
# step, because a page that has to be remembered tends to go unopened within a few
# days: the skill that is already running opens it instead.
#
#   scripts/open-web-ui.sh [--background] [/path]
#
# --background opens the page behind the current window, for a skill whose own
# output is still being read. The path defaults to / (the home page).
#
# Fail-safe: it prints one line saying what it did and always exits 0, so it can
# never fail the skill that called it. It opens nothing when this is not macOS,
# when the server is not answering, and when the run was started from the web
# page's own chat (the page is already open there; web/src/lib/chat/runner.ts sets
# PFC_WEB_CHAT=1).
set -u

BASE="http://127.0.0.1:4323"
background=""
path="/"
for arg in "$@"; do
  case "$arg" in
    --background) background="-g" ;;
    *) path="$arg" ;;
  esac
done

skip() { echo "Web UI not opened: $1"; exit 0; }

# One page on this server, nothing else: a leading slash, plain path characters, no
# second slash that would make it another host, and no parent-folder step.
[[ "$path" =~ ^/([A-Za-z0-9._?=\&-]+(/[A-Za-z0-9._?=\&-]+)*/?)?$ ]] || skip "that is not a page path."
[[ "$path" == *..* ]] && skip "that is not a page path."

[ "${PFC_WEB_CHAT:-}" = "1" ] && skip "this run was started from the web page."
[ "$(uname 2>/dev/null)" = "Darwin" ] || skip "it runs only on macOS."
command -v open >/dev/null 2>&1 || skip "it runs only on macOS."
curl -s -o /dev/null --max-time 2 "$BASE/favicon.svg" 2>/dev/null || skip "nothing is answering at $BASE."

if [ -n "$background" ]; then
  open -g "$BASE$path" 2>/dev/null || skip "the browser could not be started."
else
  open "$BASE$path" 2>/dev/null || skip "the browser could not be started."
fi
echo "Opened $BASE$path in the browser."
exit 0
