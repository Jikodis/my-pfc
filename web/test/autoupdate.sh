#!/bin/bash
# Run automations/scripts/run-web.sh on a spare port and check that it keeps itself
# current: a source change is built and swapped in, a broken build leaves the old one
# serving, and a swap waits while a chat reply is running.
#
# Port 4397 and the build folder dist-test belong to this script alone, so it never
# disturbs the launch agent's server (4323, dist) or web/test/smoke.sh (4399). It
# changes no source file's content: it only touches modification times and adds one
# broken page for a few seconds, then removes it.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

PORT=4397
BASE="http://127.0.0.1:$PORT"
LOG=/tmp/pfc-web-autoupdate.log
STREAM=/tmp/pfc-web-autoupdate-stream.txt
BROKEN=src/pages/autoupdate-broken-test.astro

export PFC_PYTHON="${PFC_PYTHON:-$(command -v python3)}"
export PFC_CLAUDE="$PWD/test/fixtures/fake_claude.sh"
export FAKE_CLAUDE_MODE=hang
export PFC_CHAT_SESSIONS_FILE=/tmp/pfc-web-autoupdate-sessions.json
export PFC_WEB_WRITE="$PWD/test/fixtures/fake_web_write.sh"
export PFC_WEB_DIST=dist-test
export PFC_WEB_CHECK_SECONDS=1
export HOST=127.0.0.1
export PORT
rm -f "$PFC_CHAT_SESSIONS_FILE"

if lsof -tiTCP:$PORT -sTCP:LISTEN >/dev/null 2>&1; then
  echo "port $PORT is busy, so this run would talk to someone else's server."
  exit 1
fi

bash ../automations/scripts/run-web.sh >"$LOG" 2>&1 &
RUNNER=$!
cleanup() {
  rm -f "$BROKEN"
  kill "$RUNNER" 2>/dev/null || true
  wait "$RUNNER" 2>/dev/null || true
  rm -rf dist-test dist-test-next .dist-test-served .dist-test-started .dist-test-failed
}
trap cleanup EXIT

fail=0
passed=0
ok() { echo "ok   $1"; passed=$((passed + 1)); }
bad() { echo "FAIL $1 (log: $LOG)"; fail=1; }

build_id() { curl -s --max-time 2 "$BASE/api/build" | sed -n 's/.*"build":"\([^"]*\)".*/\1/p'; }

wait_for_new_build() {  # wait_for_new_build <old id> <seconds>: prints the new id
  local old="$1" id=""
  for _ in $(seq 1 $(($2 * 2))); do
    id=$(build_id)
    if [ -n "$id" ] && [ "$id" != "$old" ]; then echo "$id"; return 0; fi
    sleep 0.5
  done
  return 1
}

first=$(wait_for_new_build none 60) && ok "serves a first build ($first)" || { bad "never served a first build"; exit 1; }

touch src/lib/format.ts
second=$(wait_for_new_build "$first" 30) && ok "rebuilds and swaps in after a source change" || bad "no new build after a source change"

printf -- '---\nimport Missing from "./does-not-exist-autoupdate"\n---\n<Missing />\n' >"$BROKEN"
for _ in $(seq 1 60); do
  grep -q 'build failed; still serving' "$LOG" && break
  sleep 0.5
done
if grep -q 'build failed; still serving' "$LOG" && [ "$(build_id)" = "${second:-}" ]; then
  ok "a broken build leaves the previous build serving"
else
  bad "a broken build did not leave the previous build serving"
fi
sleep 3
if [ "$(grep -c 'web source changed' "$LOG")" -eq 2 ]; then
  ok "a failed build is not retried until the source changes again"
else
  bad "a failed build was retried with no new change"
fi
rm -f "$BROKEN"

third=$(wait_for_new_build "${second:-}" 30) && ok "builds again once the broken file is gone" || bad "no build after the broken file was removed"

# A chat reply that hangs keeps the server busy; the new build must wait for it.
curl -sN -X POST -H 'Content-Type: application/json' -H 'X-PFC-Chat: 1' \
  --data '{"message":"hello"}' "$BASE/api/chat" >"$STREAM" 2>/dev/null &
CHAT=$!
for _ in $(seq 1 20); do
  curl -s "$BASE/api/build" | grep -q '"busy":true' && break
  sleep 0.5
done
touch src/lib/format.ts
for _ in $(seq 1 40); do
  grep -q 'waiting for a chat reply' "$LOG" && break
  sleep 0.5
done
if grep -q 'waiting for a chat reply' "$LOG" && [ "$(build_id)" = "${third:-}" ]; then
  ok "holds the new build back while a chat reply is running"
else
  bad "did not hold the new build back during a chat reply"
fi
run=$(sed -n 's/^data: {"id":"\([^"]*\)"}$/\1/p' "$STREAM" | head -1)
curl -s -o /dev/null -X POST -H 'Content-Type: application/json' -H 'X-PFC-Chat: 1' \
  --data "{\"id\":\"$run\"}" "$BASE/api/chat/stop" || true
wait "$CHAT" 2>/dev/null || true
wait_for_new_build "${third:-}" 30 >/dev/null && ok "swaps the new build in once the reply ends" || bad "no swap after the reply ended"

echo "$passed passed"
exit "$fail"
