#!/bin/bash
# Build the site, serve it on a spare port, request every route, stop the server.
#
# Port 4399 belongs to this script alone. The launch agent serves 4323, so a smoke
# run never disturbs it. The server started here is stopped by the process id this
# script recorded, never by a name pattern: a name pattern can also match other
# servers on the same machine.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

PORT=4399
BASE="http://127.0.0.1:$PORT"
BODY=/tmp/pfc-web-smoke.html
LOG=/tmp/pfc-web-smoke.log

# The scripts under automations/scripts need PyYAML. Set PFC_PYTHON when the
# python3 on PATH is not the interpreter that has it.
export PFC_PYTHON="${PFC_PYTHON:-$(command -v python3)}"

# The chat endpoint runs the fake binary here, never the real claude: a real run
# spends the user's subscription and can change this repo. The list of conversations
# it starts goes to a temporary file, so the one the real server reads is untouched.
export PFC_CLAUDE="$PWD/test/fixtures/fake_claude.sh"
export FAKE_CLAUDE_MODE=ok
export PFC_CHAT_SESSIONS_FILE=/tmp/pfc-web-smoke-sessions.json
rm -f "$PFC_CHAT_SESSIONS_FILE"

# The write routes run the fake writer here, never web_write.py: a real one commits
# to this repo's data. The real script is checked once below, by itself, with
# --dry-run and an id that names nothing.
export PFC_WEB_WRITE="$PWD/test/fixtures/fake_web_write.sh"
export FAKE_WRITE_MODE=ok

if lsof -tiTCP:$PORT -sTCP:LISTEN >/dev/null 2>&1; then
  echo "port $PORT is busy, so this run would talk to someone else's server."
  echo "free it with: kill \$(lsof -tiTCP:$PORT -sTCP:LISTEN)"
  exit 1
fi

npm run build >/dev/null

HOST=127.0.0.1 PORT=$PORT node dist/server/entry.mjs >"$LOG" 2>&1 &
PID=$!
trap 'kill "$PID" 2>/dev/null || true' EXIT

for _ in $(seq 1 40); do
  if curl -s -o /dev/null "$BASE/"; then break; fi
  sleep 0.5
done

fail=0
passed=0

check() {  # check <expected code> <route>
  local want="$1" route="$2" code
  code=$(curl -s -o "$BODY" -w '%{http_code}' "$BASE$route")
  if [ "$code" != "$want" ]; then
    echo "FAIL $code (wanted $want) $route"
    fail=1
    return
  fi
  if [ "$want" = "200" ] && grep -qi 'failed:\|is not valid JSON' "$BODY"; then
    echo "FAIL body reports a broken data call: $route"
    fail=1
    return
  fi
  echo "ok   $want $route"
  passed=$((passed + 1))
}

# Every page the UI serves: the one page, Tasks and the icon.
for route in / /tasks '/tasks?archive=1' /favicon.svg; do
  check 200 "$route"
done

# The pages that used to exist are gone, and a path under them is a miss.
for route in /map /back-on-track /trends /days /habits /focus /projects /records/insights /wiki /search; do
  check 404 "$route"
done

# The chat endpoint. The guard stands in front of a process that can edit and commit
# in this repo, so every way in that must be refused is checked here, against the
# running server rather than against the module.
JSON_HEADER=(-H 'Content-Type: application/json')
CHAT_HEADERS=("${JSON_HEADER[@]}" -H 'X-PFC-Chat: 1')

chat_code() {  # chat_code <expected code> <what it is> [curl arguments...]
  local want="$1" what="$2" code
  shift 2
  code=$(curl -s -o "$BODY" -w '%{http_code}' -X POST "$@" "$BASE/api/chat")
  if [ "$code" = "$want" ]; then
    echo "ok   $want $what"
    passed=$((passed + 1))
  else
    echo "FAIL $code (wanted $want) $what"
    fail=1
  fi
}

# A whole run, streamed, with the fake binary standing in for claude.
STREAM=/tmp/pfc-web-smoke-stream.txt
curl -sN -X POST "${CHAT_HEADERS[@]}" --data '{"message":"hello"}' "$BASE/api/chat" >"$STREAM" || true
if grep -q '"kind":"done"' "$STREAM" && grep -q '^event: run' "$STREAM"; then
  echo "ok   200 POST /api/chat streams a run to its done event"
  passed=$((passed + 1))
else
  echo "FAIL POST /api/chat did not stream a finished run. See $STREAM and $LOG"
  fail=1
fi

# The run just streamed has ended and is kept for a while, so a page that comes back
# to it can still read its tail. One that names no run it has gets 404.
attach_code() {  # attach_code <expected code> <what it is> [curl arguments...]
  local want="$1" what="$2" code
  shift 2
  code=$(curl -s -o "$BODY" -w '%{http_code}' -X POST "$@" "$BASE/api/chat/attach")
  if [ "$code" = "$want" ]; then
    echo "ok   $want $what"
    passed=$((passed + 1))
  else
    echo "FAIL $code (wanted $want) $what"
    fail=1
  fi
}
RUN_ID=$(sed -n 's/^data: {"id":"\([0-9a-f-]*\)"}$/\1/p' "$STREAM" | head -1)
attach_code 200 'POST /api/chat/attach reads a finished run that is still kept' \
  "${CHAT_HEADERS[@]}" --data "{\"id\":\"$RUN_ID\",\"from\":0}"
if grep -q '"kind":"done"' "$BODY"; then
  echo "ok   POST /api/chat/attach streams that run to its done event"
  passed=$((passed + 1))
else
  echo "FAIL POST /api/chat/attach did not stream the kept run's done event. See $BODY"
  fail=1
fi
attach_code 404 'POST /api/chat/attach naming a run this server does not have' \
  "${CHAT_HEADERS[@]}" --data '{"id":"22222222-2222-4222-8222-222222222222","from":0}'
attach_code 403 'POST /api/chat/attach without the X-PFC-Chat header' \
  "${JSON_HEADER[@]}" --data '{"id":"22222222-2222-4222-8222-222222222222","from":0}'

chat_code 403 'POST /api/chat without the X-PFC-Chat header' \
  "${JSON_HEADER[@]}" --data '{"message":"hello"}'
chat_code 403 'POST /api/chat from another origin' \
  "${CHAT_HEADERS[@]}" -H 'Origin: https://evil.example' --data '{"message":"hello"}'
chat_code 403 'POST /api/chat naming a conversation this server did not start' \
  "${CHAT_HEADERS[@]}" --data '{"message":"hello","sessionId":"11111111-1111-4111-8111-111111111111"}'
# Plain text is one of the three types a browser can post from a form without asking
# permission first, so Astro's own cross-site check refuses it before this app's does.
chat_code 403 'POST /api/chat sent as plain text' \
  -H 'Content-Type: text/plain' -H 'X-PFC-Chat: 1' --data 'hello'
chat_code 415 'POST /api/chat sent as anything else that is not JSON' \
  -H 'Content-Type: application/xml' -H 'X-PFC-Chat: 1' --data '<hello/>'
chat_code 413 'POST /api/chat with a body past the cap' \
  "${CHAT_HEADERS[@]}" --data "{\"message\":\"$(head -c 70000 < /dev/zero | tr '\0' 'x')\"}"
chat_code 400 'POST /api/chat with an empty message' \
  "${CHAT_HEADERS[@]}" --data '{"message":"   "}'

# The write routes, through the fake writer.
write_code() {  # write_code <expected code> <what it is> <route> [curl arguments...]
  local want="$1" what="$2" route="$3" code
  shift 3
  code=$(curl -s -o "$BODY" -w '%{http_code}' -X POST "$@" "$BASE/api/write/$route")
  if [ "$code" = "$want" ]; then
    echo "ok   $want $what"
    passed=$((passed + 1))
  else
    echo "FAIL $code (wanted $want) $what"
    fail=1
  fi
}

write_code 403 'POST /api/write/complete-task without the X-PFC-Chat header' complete-task \
  "${JSON_HEADER[@]}" --data '{"id":"task-20260901-001"}'
write_code 403 'POST /api/write/log-habit from another origin' log-habit \
  "${CHAT_HEADERS[@]}" -H 'Origin: https://evil.example' --data '{"id":"morning-walk"}'
write_code 415 'POST /api/write/park-focus sent as something that is not JSON' park-focus \
  -H 'Content-Type: application/xml' -H 'X-PFC-Chat: 1' --data '<x/>'
write_code 400 'POST /api/write/complete-task with an id of the wrong shape' complete-task \
  "${CHAT_HEADERS[@]}" --data '{"id":"task-1; rm -rf /"}'
write_code 200 'POST /api/write/complete-task with the headers' complete-task \
  "${CHAT_HEADERS[@]}" --data '{"id":"task-20260901-001"}'
write_code 200 'POST /api/write/log-habit with the headers' log-habit \
  "${CHAT_HEADERS[@]}" --data '{"id":"morning-walk"}'
write_code 200 'POST /api/write/park-focus with the headers' park-focus \
  "${CHAT_HEADERS[@]}" --data '{"id":"focus-20260706-001","parked":true}'

# The real writer, once, dry and with an id that names nothing: it must refuse with
# exit 2 and a JSON error, and leave the working tree exactly as it was.
BEFORE=$(git -C .. status --short)
set +e
DRY=$("$PFC_PYTHON" ../automations/scripts/web_write.py --dry-run complete-task task-00000000-000 2>/dev/null)
DRY_EXIT=$?
set -e
AFTER=$(git -C .. status --short)
if [ "$DRY_EXIT" = "2" ] && [ "$(jq -r '.ok' <<<"$DRY" 2>/dev/null)" = "false" ] && [ "$BEFORE" = "$AFTER" ]; then
  echo "ok   web_write.py --dry-run refuses an unknown task and changes nothing"
  passed=$((passed + 1))
else
  echo "FAIL web_write.py --dry-run: exit $DRY_EXIT, output $DRY, tree changed: $([ "$BEFORE" = "$AFTER" ] && echo no || echo yes)"
  fail=1
fi

# The skills list, which the drawer reads once to build its buttons.
SKILL_COUNT=$(curl -s "$BASE/api/chat/skills" | jq 'length' 2>/dev/null || echo 0)
if [ "$SKILL_COUNT" -gt 20 ]; then
  echo "ok   200 GET /api/chat/skills listed $SKILL_COUNT skills"
  passed=$((passed + 1))
else
  echo "FAIL GET /api/chat/skills listed $SKILL_COUNT skills, wanted more than 20"
  fail=1
fi

# Headers, not meta tags: a browser ignores frame-ancestors in a meta tag, and the
# chat drawer can start a process in this repo, so no page of this app may be framed.
for route in / /api/chat/skills; do
  HEAD=$(curl -s -D - -o /dev/null "$BASE$route")
  if grep -qi '^x-frame-options: DENY' <<<"$HEAD" \
    && grep -qi "^content-security-policy:.*frame-ancestors 'none'" <<<"$HEAD" \
    && grep -qi '^x-content-type-options: nosniff' <<<"$HEAD" \
    && grep -qi '^referrer-policy: no-referrer' <<<"$HEAD"; then
    echo "ok   headers on $route"
    passed=$((passed + 1))
  else
    echo "FAIL $route is missing a security header"
    fail=1
  fi
done

# A panel whose Python call failed renders this sentence instead of its data.
curl -s -o "$BODY" "$BASE/"
if grep -q 'Could not load this panel\.' "$BODY"; then
  echo "FAIL a panel on / could not load. Check PFC_PYTHON and $LOG"
  fail=1
else
  echo "ok   every panel on / loaded"
  passed=$((passed + 1))
fi

# The one page: the eleven bands in VAVFPTH order, by their headings, and the tour's
# bar and buttons. Tour-only bands (data-tour-only) are left out of the order.
HEADINGS=$(perl -0777 -ne 'while (/<section\b([^>]*)>\s*<h2[^>]*>([^<]*)<\/h2>/g) { my ($a, $t) = ($1, $2); print "$t|" unless $a =~ /data-tour-only/ }' "$BODY")
WANT='Values|Areas|Visions|Focuses|Projects|Body first|Tasks|Habits|Trends|Front of mind|Week|'
if [ "$HEADINGS" = "$WANT" ] \
  && grep -q 'id="tour-bar"' "$BODY" && grep -q 'id="tour-start"' "$BODY" && grep -q 'data-band="tour-music"' "$BODY" \
  && grep -q '<title>PFC</title>' "$BODY" && ! grep -q '<summary>More</summary>' "$BODY"; then
  echo "ok   / has the eleven bands in order and the tour markup"
  passed=$((passed + 1))
else
  echo "FAIL / band headings were '$HEADINGS', or the tour bar, Walk me through, music step or title is wrong, or the More menu is still there"
  fail=1
fi

if [ "$fail" = "0" ]; then
  echo "$passed checks passed"
else
  echo "$passed checks passed, and at least one failed"
fi
exit $fail
