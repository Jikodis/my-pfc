#!/bin/bash
# Serve the PFC web UI as a long-running local service at http://127.0.0.1:4323.
# Used by automations/launchd/com.pfc.web.plist. Also runnable by hand.
# Serves the production build. Rebuilds only when web source is newer than the build.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WEB="$REPO/web"
ENTRY="$WEB/dist/server/entry.mjs"
cd "$WEB"

export HOST="${HOST:-127.0.0.1}"
export PORT="${PORT:-4323}"
# The scripts under automations/scripts need PyYAML, which not every python3 on
# this machine has. The launch agent passes the interpreter that does; a hand
# start falls back to whichever python3 the current PATH resolves.
export PFC_PYTHON="${PFC_PYTHON:-$(command -v python3)}"
# The chat panel's claude. The launch agent names it; a hand start
# falls back to whichever claude the current PATH resolves. claude reads its login
# from the keychain under USER, which a bare environment does not always set.
export PFC_CLAUDE="${PFC_CLAUDE:-$(command -v claude || echo claude)}"
export USER="${USER:-$(id -un)}"

# Install when there is nothing installed, and reinstall when the lockfile has
# changed since the last install (npm writes node_modules/.package-lock.json on
# every install). Without the second test a checkout that gained a dependency
# keeps its old node_modules, the build fails, and the launch agent restarts forever.
if [ ! -d node_modules ]; then
  echo "[pfc-web] installing dependencies"
  npm ci
elif [ ! -f node_modules/.package-lock.json ] || [ package-lock.json -nt node_modules/.package-lock.json ]; then
  echo "[pfc-web] package-lock.json changed, reinstalling dependencies"
  npm ci
fi

if [ ! -f "$ENTRY" ] || [ -n "$(find src astro.config.mjs package.json -newer "$ENTRY" -print -quit 2>/dev/null)" ]; then
  echo "[pfc-web] building"
  npm run build
fi

echo "[pfc-web] serving http://$HOST:$PORT with python $PFC_PYTHON and claude $PFC_CLAUDE"
exec node "$ENTRY"
