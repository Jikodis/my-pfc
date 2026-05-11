#!/usr/bin/env bash
# UserPromptSubmit hook: re-inject authoritative local-timezone date on every prompt.
#
# Why: SessionStart only fires once. For long-lived sessions that cross local
# midnight (common when evening check-ins run past 11 PM or morning planning
# picks up a conversation started the night before), the SessionStart-injected
# date goes stale. Without re-injection, the model keeps referring to
# "yesterday" relative to the SessionStart moment, not the current wall clock.
#
# This hook runs before every user prompt is processed and adds a fresh date
# block to the conversation context. Cheap (one date call) and idempotent.
#
# The persona block is intentionally NOT re-injected here — personas don't
# change mid-session, and re-emitting the voice rules every turn is noise.

# Source .env if present so LOCAL_TZ (and other vars) take effect.
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
if [ -f "$PROJECT_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$PROJECT_DIR/.env"
  set +a
fi
LOCAL_TZ="${LOCAL_TZ:-America/Denver}"

DATE=$(TZ="$LOCAL_TZ" date '+%Y-%m-%d')
TIME=$(TZ="$LOCAL_TZ" date '+%I:%M %p %Z')
DOW=$(TZ="$LOCAL_TZ" date '+%A')
YDAY=$(TZ="$LOCAL_TZ" date -d 'yesterday' '+%Y-%m-%d')

cat <<EOF
=== CURRENT LOCAL DATE ($LOCAL_TZ — re-checked this turn) ===

Today:     $DATE ($DOW)
Yesterday: $YDAY
Time now:  $TIME

Use this, not the injected \`currentDate\` (UTC). If this conflicts with an
earlier SessionStart-injected date, THIS value wins — the session may have
crossed local midnight.
EOF
