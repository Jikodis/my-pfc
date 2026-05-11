#!/usr/bin/env bash
# Install PFC systemd user units.
# Run this once from the VPS as the claude user.
# Safe to re-run — it reloads and restarts cleanly.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
UNIT_SRC="$REPO_ROOT/automations/systemd"
UNIT_DST="$HOME/.config/systemd/user"

echo "==> Installing PFC systemd units from $UNIT_SRC"

mkdir -p "$UNIT_DST"

# Install unit files (substituting placeholders from .template sources)
UNITS=(
    pfc-habit-autolog.service
    pfc-habit-autolog.timer
    pfc-trello-daily-render.service
    pfc-trello-daily-render.timer
)

REPO_URL="$(git -C "$REPO_ROOT" remote get-url origin 2>/dev/null | sed -E 's#git@github.com:#https://github.com/#; s#\.git$##' || true)"
if [ -z "$REPO_URL" ]; then
    echo "ERROR: no 'origin' git remote configured for $REPO_ROOT" >&2
    echo "  systemd unit Documentation= URL would be empty/broken." >&2
    echo "  Set a remote (e.g. 'git remote add origin <url>') or hardcode REPO_URL above." >&2
    exit 1
fi

# Local timezone: read from .env (LOCAL_TZ) if present, else fall back to America/Denver.
LOCAL_TZ_VAL="America/Denver"
if [ -f "$REPO_ROOT/.env" ]; then
    LOCAL_TZ_FROM_ENV="$(grep -E '^LOCAL_TZ=' "$REPO_ROOT/.env" | head -1 | sed -E 's/^LOCAL_TZ=//; s/^["'\'']//; s/["'\'']$//')"
    if [ -n "$LOCAL_TZ_FROM_ENV" ]; then
        LOCAL_TZ_VAL="$LOCAL_TZ_FROM_ENV"
    fi
fi
echo "==> Using LOCAL_TZ=$LOCAL_TZ_VAL"

for unit in "${UNITS[@]}"; do
    src="$UNIT_SRC/${unit}.template"
    dst="$UNIT_DST/${unit}"
    if [ ! -f "$src" ]; then
        echo "ERROR: $src not found" >&2
        exit 1
    fi
    sed -e "s#__REPO_ROOT__#$REPO_ROOT#g" \
        -e "s#__REPO_URL__#$REPO_URL#g" \
        -e "s#__LOCAL_TZ__#$LOCAL_TZ_VAL#g" \
        "$src" > "$dst"
    echo "    Installed $unit (substituted from $(basename "$src"))"
done

# Enable linger so user units run without an active login session
loginctl enable-linger
echo "==> Linger enabled for $USER"

# Reload systemd user daemon
systemctl --user daemon-reload
echo "==> Daemon reloaded"

# Enable and start timers
systemctl --user enable --now pfc-habit-autolog.timer
echo "==> pfc-habit-autolog.timer enabled and started"

systemctl --user enable --now pfc-trello-daily-render.timer
echo "==> pfc-trello-daily-render.timer enabled and started"

echo ""
echo "Done. Verify with:"
echo "  systemctl --user status pfc-habit-autolog.timer"
echo "  systemctl --user status pfc-trello-daily-render.timer"
echo "  systemctl --user list-timers"
echo ""
echo "Watch logs with:"
echo "  journalctl --user -u pfc-habit-autolog.service -f"
echo "  journalctl --user -u pfc-trello-daily-render.service -f"
