#!/usr/bin/env bash
# Process the Trello 📥 Inbox list unattended: /pfc-trello-inbox unattended.
#
# Run every 10 minutes (:05, :15...) by the pfc-trello-inbox timer, so notes the
# reMarkable sync (:00, :10...) just sent are processed within minutes. Claude
# starts only when the list holds a card that is not already waiting for you
# (title starting with ❓), so an empty inbox costs no tokens. What the skill may
# and may not do on its own is in .agents/skills/pfc-trello-inbox/SKILL.md
# § Unattended mode.
#
# Opt-in: it runs headless Claude with no one watching, so it does nothing unless
# PFC_TRELLO_INBOX=1 is set in .env (or the environment). install.sh starts the timer
# only with that flag too.

set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT" || exit 1

PYTHON="${PFC_PYTHON:-python3}"
CLAUDE="${PFC_CLAUDE:-$(command -v claude || echo "$HOME/.local/bin/claude")}"
TZ_NAME="${LOCAL_TZ:-America/Denver}"
log() { printf '%s %s\n' "$(TZ="$TZ_NAME" date '+%Y-%m-%d %I:%M %p')" "$*"; }

if [ "${PFC_TRELLO_INBOX:-}" != "1" ] && ! grep -qE "^PFC_TRELLO_INBOX=1" .env 2>/dev/null; then
  log "unattended inbox is off: set PFC_TRELLO_INBOX=1 in .env to turn it on"
  exit 0
fi

if [ -z "${CLAUDE_CODE_OAUTH_TOKEN:-}" ] && [ -f .env ]; then
  token="$(grep -E '^CLAUDE_CODE_OAUTH_TOKEN=.+' .env | head -1 | cut -d= -f2- | tr -d "\"'")"
  if [ -n "$token" ]; then export CLAUDE_CODE_OAUTH_TOKEN="$token"; fi
fi

if ! cards="$("$PYTHON" automations/scripts/trello_helper.py list 2>&1)"; then
  log "🟡 Trello inbox fetch failed: $cards"
  exit 0
fi
open="$(printf '%s\n' "$cards" | jq -r 'select(.name | startswith("❓") | not) | .name' 2>/dev/null | grep -c . || true)"
if [ "${open:-0}" -eq 0 ]; then
  log "🟢 inbox has nothing new"
  exit 0
fi

log "START processing $open inbox card(s)"
# Its per-card lines become the agent's replies on the reMarkable page each note came
# from (automations/scripts/remarkable_replies.py), drawn by the next sync.
out="$(timeout 900 "$CLAUDE" -p "/pfc-trello-inbox unattended" --permission-mode auto < /dev/null)"
code=$?
printf '%s\n' "$out"
printf '%s\n' "$out" | "$PYTHON" automations/scripts/remarkable_replies.py from-inbox
if [ "$code" -eq 0 ]; then
  log "DONE"
else
  log "🟡 Claude failed (exit $code); cards stay in the inbox for the next run"
fi
exit 0
