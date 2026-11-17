#!/usr/bin/env bash
# SessionStart hook: flag recent days that never got a day rating.
#
# Why: a day that is not written down within about a day is hard to recall
# accurately later. Without a prompt, a missed rating stays silent until
# someone happens to notice the gap in the data.
#
# So: say it early and say it once. The hook prints only when there IS a gap,
# most recent first, because yesterday is the day still worth recovering.
#
# SessionStart, not UserPromptSubmit: once per session is a reminder, every
# turn is nagging, and a nag soon gets ignored.
#
# Today is never flagged: the day isn't over. Yesterday is the first candidate.
# The fix is /pfc-log-day in chat, for that date.
#
# Window is 1 day (yesterday only) because older days are rarely recalled
# well enough to rate. Set PFC_CHECKIN_LOOKBACK_DAYS higher to also list older
# days for records-based reconstruction.
#
# Quiet until day tracking has started: if data/day-tracking.ndjson has no
# rated day yet, the hook prints nothing.

set -uo pipefail

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
if [ -f "$PROJECT_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$PROJECT_DIR/.env"
  set +a
fi
LOCAL_TZ="${LOCAL_TZ:-America/Denver}"
TRACKING="$PROJECT_DIR/data/day-tracking.ndjson"
LOOKBACK="${PFC_CHECKIN_LOOKBACK_DAYS:-1}"

# Fail safe: no data file, no jq, no output. Never block a session.
[ -f "$TRACKING" ] || exit 0
command -v jq >/dev/null 2>&1 || exit 0

# Dates that already carry a rating (the marker that the day was rated).
RATED=$(jq -r 'select(.rating != null) | .date' "$TRACKING" 2>/dev/null) || exit 0
[ -n "$RATED" ] || exit 0

# GNU date takes -d; macOS date takes -v and -j -f. Try GNU first.
days_ago() { TZ="$LOCAL_TZ" date -d "$1 days ago" '+%Y-%m-%d' 2>/dev/null || TZ="$LOCAL_TZ" date -v-"$1"d '+%Y-%m-%d' 2>/dev/null; }
fmt_date() { TZ="$LOCAL_TZ" date -d "$1" "$2" 2>/dev/null || TZ="$LOCAL_TZ" date -j -f '%Y-%m-%d %H:%M:%S' "$1 00:00:00" "$2" 2>/dev/null; }

MISSING=()
for (( i = 1; i <= LOOKBACK; i++ )); do
  D=$(days_ago "$i") || continue
  grep -qxF "$D" <<< "$RATED" || MISSING+=("$D")
done

[ "${#MISSING[@]}" -eq 0 ] && exit 0

echo "=== UNRATED DAYS (last $LOOKBACK days) ==="
echo
for D in "${MISSING[@]}"; do
  DOW=$(fmt_date "$D" '+%A')
  AGE=$(( ( $(TZ="$LOCAL_TZ" date '+%s') - $(fmt_date "$D" '+%s') ) / 86400 ))
  case "$AGE" in
    1) NOTE="yesterday" ;;
    *) NOTE="$AGE days ago, listed only because PFC_CHECKIN_LOOKBACK_DAYS was raised; do not ask the user to rate it" ;;
  esac
  echo "  $D ($DOW): $NOTE"
done
cat <<'EOF'

Surface this ONCE, early in your first reply, as a single soft line, e.g.
"Yesterday never got a rating. Want to rate it now while you still remember?"
Then drop it. Do not repeat it later in the session, do not stack it with
other asks, and do not moralize about the gap.

If the user says yes: rate it in chat with /pfc-log-day for that date.
Never ask about a day older than yesterday unless the lookback was raised.
If the user says no: let it go; it shows again next session.

Never fabricate energy / mood / focus for a day the user cannot recall. Leave
the ratings null and write what the records actually show to notes, labeled
as reconstructed.
EOF
