#!/usr/bin/env bash
# SessionStart hook: inject authoritative local-timezone date + active persona.
#
# Why: the server clock is UTC, but the user's wall clock is their local timezone
# (read from $LOCAL_TZ, default America/Denver). After ~5–6 PM local, the system-
# injected `currentDate` is already tomorrow's date in UTC. Without this hook,
# date-stamped writes (task ids, created fields, focus dates, etc.) silently shift
# forward a day. This hook eliminates that failure mode by injecting the correct
# local date as context at session start.
#
# Also injects the active persona (config/persona.yaml + config/personas.md) so the
# assistant adopts the chosen voice for the session.
#
# Output goes to the session as additional context.

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

cat <<EOF
=== AUTHORITATIVE LOCAL DATE ($LOCAL_TZ) ===

Today (in user's timezone, $LOCAL_TZ): $DATE ($DOW)
Current local time: $TIME

Use this date for EVERY date-stamped write:
  - task ids (task-YYYYMMDD-NNN), task created/completed/deadline
  - daily-focus date, day-tracking date, habit dates
  - supplement started/stopped, insight/hypothesis/finding created
  - calendar event dates, commit message dates

DO NOT trust the system-injected \`currentDate\` — it is UTC-based and shifts to tomorrow after ~5 PM in your timezone. This hook overrides it.
EOF

# ── Active persona injection ─────────────────────────────────────────────────
# Look up active persona from config/persona.yaml; pull voice notes from
# config/personas.md. The script runs from the project root via $CLAUDE_PROJECT_DIR.

PERSONA_CFG="$PROJECT_DIR/config/persona.yaml"
PERSONA_REG="$PROJECT_DIR/config/personas.md"

if [ -f "$PERSONA_CFG" ] && [ -f "$PERSONA_REG" ]; then
  ACTIVE=$(grep -E '^active:' "$PERSONA_CFG" | head -1 | sed -E 's/^active:[[:space:]]*//; s/[[:space:]]*#.*//; s/^["'\'']//;s/["'\'']$//')

  if [ -n "$ACTIVE" ] && [ "$ACTIVE" != "none" ]; then
    # Extract the markdown section for the active persona (## <id> ... up to next ## or EOF)
    SECTION=$(awk -v id="$ACTIVE" '
      $0 == "## " id      { capture=1; print; next }
      capture && /^## /   { capture=0 }
      capture             { print }
    ' "$PERSONA_REG")

    if [ -n "$SECTION" ]; then
      cat <<EOF

=== ACTIVE PERSONA: $ACTIVE ===

$SECTION

PERSONA DISCIPLINE — non-negotiable:
- Voice/tone only. Never extend response length to fit the voice. Terseness rules win.
- Skill steps are mechanical and followed verbatim — persona shapes wording, not behavior.
- Status emojis (🔴 🟡 🟢) stay literal in status outputs.
- All memory rules (date derivation, dedup checks, auto-fetched habits, etc.) win over persona impulses.
- Switch via /pfc-persona or set active: none in config/persona.yaml.
EOF
    else
      echo
      echo "⚠️  Active persona '$ACTIVE' not found in config/personas.md — running without persona."
    fi
  fi
fi

# ── Fresh-install welcome banner ───────────────────────────────────────────────
# Emit welcome message for first-run users:
# - onboarding.ndjson exists AND is empty (zero records = fresh install)
# - repo's first commit was within the last 7 days (avoid annoying old users)

ONBOARDING_FILE="${CLAUDE_PROJECT_DIR:-.}/config/onboarding.ndjson"
if [ -f "$ONBOARDING_FILE" ] && [ ! -s "$ONBOARDING_FILE" ]; then
    if [ -d "${CLAUDE_PROJECT_DIR:-.}/.git" ]; then
        first_commit_date=$(git -C "${CLAUDE_PROJECT_DIR:-.}" log --reverse --format=%cs 2>/dev/null | head -1)
        today=$(TZ="$LOCAL_TZ" date '+%Y-%m-%d')
        if [ -n "$first_commit_date" ]; then
            days_old=$(( ( $(date -d "$today" +%s) - $(date -d "$first_commit_date" +%s) ) / 86400 ))
            if [ "$days_old" -le 7 ]; then
                cat <<'WELCOME'

Welcome to PFC. This appears to be a fresh install — run `/pfc-onboarding`
to get oriented. The system has many features but you don't need to learn
them all today.

WELCOME
            fi
        fi
    fi
fi
