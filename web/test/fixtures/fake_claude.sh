#!/bin/bash
# Stands in for the claude binary so the runner's tests never spend the user's
# subscription quota. FAKE_CLAUDE_MODE picks the behavior; the argv is ignored.
#
#   ok           the captured sample stream, a line at a time, exit 0
#   crash        one init line, "boom" on stderr, exit 2
#   hang         one init line, then sleep, so a test can stop or time out a live run
#   stubborn     as hang, but it ignores SIGTERM, so only SIGKILL ends it
#   bigline      one line over the reader's 1 MB limit, then a normal stream
#   stderrflood  more stderr than the runner keeps, exit 3
#   leaky        a failure whose error output names a path and an environment value
#   flood        more text events than the runner will hold, then a result line
#   envcheck     writes the value of PFC_WEB_CHAT to FAKE_CLAUDE_ENV_FILE, then as ok
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SAMPLE="$HERE/chat/sample.jsonl"
INIT='{"type":"system","subtype":"init","session_id":"00000000-0000-4000-8000-000000000000","model":"claude-sonnet-5"}'

case "${FAKE_CLAUDE_MODE:-ok}" in
  ok)
    while IFS= read -r line; do
      printf '%s\n' "$line"
      sleep 0.05
    done < "$SAMPLE"
    exit 0
    ;;
  crash)
    printf '%s\n' "$INIT"
    printf 'boom\n' >&2
    exit 2
    ;;
  hang)
    printf '%s\n' "$INIT"
    # The sleep runs in the background and this waits on it, so the signal is acted
    # on at once instead of after the sleep, the way a program that means to stop does.
    trap 'kill "$naptime" 2>/dev/null; exit 143' TERM
    sleep 60 &
    naptime=$!
    wait "$naptime"
    exit 0
    ;;
  stubborn)
    printf '%s\n' "$INIT"
    trap '' TERM
    sleep 60 &
    naptime=$!
    wait "$naptime"
    exit 0
    ;;
  bigline)
    printf '%s\n' "$INIT"
    # Two million characters on one line, which no reader should hold.
    head -c 2000000 < /dev/zero | tr '\0' 'x'
    printf '\n'
    cat "$SAMPLE"
    exit 0
    ;;
  stderrflood)
    printf '%s\n' "$INIT"
    head -c 10000 < /dev/zero | tr '\0' 'E' >&2
    printf '\nthe last words\n' >&2
    exit 3
    ;;
  leaky)
    printf '%s\n' "$INIT"
    printf 'Error: Cannot find module /opt/homebrew/lib/node_modules/@anthropic-ai/claude-code/cli.js\n' >&2
    printf 'env was TOKEN=hunter2\n' >&2
    exit 7
    ;;
  envcheck)
    printf '%s' "${PFC_WEB_CHAT:-}" > "$FAKE_CLAUDE_ENV_FILE"
    cat "$SAMPLE"
    exit 0
    ;;
  flood)
    printf '%s\n' "$INIT"
    awk 'BEGIN { for (i = 0; i < 6000; i++) print "{\"type\":\"stream_event\",\"event\":{\"type\":\"content_block_delta\",\"index\":0,\"delta\":{\"type\":\"text_delta\",\"text\":\"x\"}}}" }'
    grep '"type":"result"' "$SAMPLE"
    exit 0
    ;;
  *)
    printf 'unknown FAKE_CLAUDE_MODE: %s\n' "${FAKE_CLAUDE_MODE:-}" >&2
    exit 64
    ;;
esac
