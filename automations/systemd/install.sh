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
    pfc-health-fetch.service
    pfc-health-fetch.timer
    pfc-health-fetch-morning.service
    pfc-health-fetch-morning.timer
    pfc-trello-daily-render.service
    pfc-trello-daily-render.timer
    pfc-repo-sync.service
    pfc-repo-sync.timer
    pfc-remarkable-sync.service
    pfc-remarkable-sync.timer
    pfc-ai-news.service
    pfc-ai-news.timer
    pfc-trmnl-serve.service
)

# Opt-in timers: installed always (so the reconcile pass below keeps them), started only
# when .env turns them on, because each one runs headless Claude and needs a device or
# API key. reMarkable pages: PFC_REMARKABLE_SYNC=1 (docs/remarkable.md). AI News:
# PFC_AI_NEWS=1 (docs/ai-news.md).
opt_in_flag() {
    case "$1" in
        pfc-remarkable-sync.timer) echo PFC_REMARKABLE_SYNC ;;
        pfc-ai-news.timer) echo PFC_AI_NEWS ;;
        *) echo "" ;;
    esac
}

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
    # `|| true`: a .env with no LOCAL_TZ= line makes grep exit 1, which under
    # `set -euo pipefail` (via pipefail) aborts the whole install silently before
    # any unit is written. Swallow it so the America/Denver default below applies.
    LOCAL_TZ_FROM_ENV="$(grep -E '^LOCAL_TZ=' "$REPO_ROOT/.env" | head -1 | sed -E 's/^LOCAL_TZ=//; s/^["'\'']//; s/["'\'']$//' || true)"
    if [ -n "$LOCAL_TZ_FROM_ENV" ]; then
        LOCAL_TZ_VAL="$LOCAL_TZ_FROM_ENV"
    fi
fi
echo "==> Using LOCAL_TZ=$LOCAL_TZ_VAL"

# Reconcile: stop and remove any pfc-*.{service,timer} already deployed in
# $UNIT_DST that's no longer in $UNITS. This auto-cleans orphans left behind
# when an automation is torn out of the repo (the deployed unit otherwise
# survives in $UNIT_DST and can crash-loop under `Restart=on-failure`).
# Stays in sync as long as install.sh is re-run after any teardown commit.
for deployed in "$UNIT_DST"/pfc-*.service "$UNIT_DST"/pfc-*.timer; do
    [ -e "$deployed" ] || continue
    name=$(basename "$deployed")
    if ! printf '%s\n' "${UNITS[@]}" | grep -qxF "$name"; then
        echo "==> Removing orphan unit $name (no template in repo)"
        systemctl --user stop "$name" 2>/dev/null || true
        systemctl --user disable "$name" 2>/dev/null || true
        rm -f "$deployed"
    fi
done

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

# Enable and start timers (every *.timer in UNITS)
for unit in "${UNITS[@]}"; do
    case "$unit" in
        *.timer)
            flag="$(opt_in_flag "$unit")"
            if [ -n "$flag" ] && [ -z "$(grep -E "^${flag}=1" "$REPO_ROOT/.env" 2>/dev/null || true)" ]; then
                systemctl --user disable --now "$unit" 2>/dev/null || true
                echo "==> Skipping $unit — set ${flag}=1 in .env to turn it on"
                continue
            fi
            systemctl --user enable --now "$unit"
            echo "==> $unit enabled and started"
            ;;
    esac
done

# Long-running services have no timer to pull them in, so enable them directly.
# They carry [Install] WantedBy=default.target; a restart picks up code changes.
LONG_RUNNING=(
    pfc-trmnl-serve.service
)
for unit in "${LONG_RUNNING[@]}"; do
    # Only if the unit is actually in UNITS — keeps this list from resurrecting
    # a service whose template was deleted.
    printf '%s\n' "${UNITS[@]}" | grep -qxF "$unit" || continue
    # TRMNL is optional: skip unless the endpoint token is configured.
    if [ -z "$(grep -E '^TRMNL_SERVE_TOKEN=.+' "$REPO_ROOT/.env" 2>/dev/null || true)" ]; then
        echo "==> Skipping $unit — TRMNL_SERVE_TOKEN not set in .env (see docs/install/trmnl-endpoint.md)"
        continue
    fi
    systemctl --user enable "$unit"
    systemctl --user restart "$unit"
    echo "==> $unit enabled and (re)started"
done

echo ""
echo "Done. Verify with:"
echo "  systemctl --user status pfc-health-fetch.timer"
echo "  systemctl --user status pfc-trello-daily-render.timer"
echo "  systemctl --user list-timers"
echo ""
echo "Watch logs with:"
echo "  journalctl --user -u pfc-health-fetch.service -f"
echo "  journalctl --user -u pfc-trello-daily-render.service -f"
