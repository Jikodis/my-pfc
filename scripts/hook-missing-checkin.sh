#!/usr/bin/env bash
# SessionStart hook: flag recent days that never got a day rating.
#
# Why this exists: a day that isn't written down within about a day is easy to
# lose entirely — and nothing else in the system says so; the gap sits silent
# until someone happens to ask.
#
# So: say it early and say it once. The hook prints only when there IS a gap,
# most-recent-first, because yesterday is the one still recoverable.
#
# Deliberately SessionStart and not UserPromptSubmit — once per session is a
# reminder, every turn is nagging, and nagging is how a signal goes invisible.
#
# Today is never flagged: the day isn't over. Yesterday is the first candidate.
# The fix is the home page's tour (`Walk me through` on http://127.0.0.1:4323/),
# whose first step rates yesterday before about 6 PM.
#
# Window is 2 days. Past about two days a day is hard to recall, so older
# entries only produce an ask that has to be declined — and an offer that can't
# be accepted is noise. Set PFC_CHECKIN_LOOKBACK_DAYS higher only if you want
# records-based reconstruction of older days.

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
LOOKBACK="${PFC_CHECKIN_LOOKBACK_DAYS:-2}"

# Fail safe: no data file, no jq, no output. Never block a session.
[ -f "$TRACKING" ] || exit 0
command -v jq >/dev/null 2>&1 || exit 0

# Dates that already carry a rating (the marker that the day was rated).
RATED=$(jq -r 'select(.rating != null) | .date' "$TRACKING" 2>/dev/null) || exit 0

# GNU date (Linux) takes -d; macOS date takes -v and -j -f. Try GNU first.
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
    1) NOTE="yesterday — still fresh, ask about this one first" ;;
    2) NOTE="2 days ago — recoverable with prompting" ;;
    *) NOTE="$AGE days ago — likely unrecoverable; offer records-based reconstruction, do not invent ratings" ;;
  esac
  echo "  $D ($DOW) — $NOTE"
done
cat <<'EOF'

Surface this ONCE, early in your first reply, as a single soft line — e.g.
"Friday never got a rating. Want to rate it now while you still remember?"
Then drop it. Do not repeat it later in the session, do not stack it with
other asks, and do not moralize about the gap.

If the user says yes and the day is yesterday: point them at the tour (`Walk me through`
on http://127.0.0.1:4323/), whose first step rates yesterday before about 6 PM.
For the day before, or after 6 PM, rate it in chat with /pfc-log-day for that date.
If they say no: let it go; it re-surfaces next session.

Never fabricate energy / mood / focus for a day the user cannot recall. Leave the
ratings null and write what the records actually show to evening_notes,
labelled as reconstructed.
EOF
