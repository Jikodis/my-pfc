#!/bin/bash
# Serve the PFC web UI as a long-running local service at http://127.0.0.1:4323.
# Used by automations/launchd/com.pfc.web.plist (macOS). Also runnable by hand.
#
# Serves the production build, and keeps it current by itself: every
# PFC_WEB_CHECK_SECONDS (default 20) it checks whether the web source changed since
# the build being served. When it did, it builds into a second folder while the old
# build keeps serving, waits until GET /api/build says no chat reply or save is
# running, then stops the server, swaps the new build in, and starts it again (about
# a second of downtime). Open pages see the new build id and reload themselves.
# A failed build leaves the old one serving and is not retried until the source
# changes again. A changed package-lock.json makes this script exit once the server
# is idle, so launchd starts it again and the install below runs.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WEB="$REPO/web"
# PFC_WEB_DIST moves the served build, so web/test/autoupdate.sh can run this script
# without touching the build the launch agent serves.
DIST="${PFC_WEB_DIST:-dist}"
NEXT="$DIST-next"
ENTRY="$WEB/$DIST/server/entry.mjs"
# The source a build is made from. A file newer than the build being served means
# the server runs old code.
SOURCES=(src public astro.config.mjs package.json package-lock.json)
# Stamps, by modification time: when the served build started (served), when the
# build now running started (started), and when the last failed one started (failed).
SERVED="$WEB/.$DIST-served"
STARTED="$WEB/.$DIST-started"
FAILED="$WEB/.$DIST-failed"
CHECK_SECONDS="${PFC_WEB_CHECK_SECONDS:-20}"
cd "$WEB"

export HOST="${HOST:-127.0.0.1}"
export PORT="${PORT:-4323}"
# The scripts under automations/scripts need PyYAML, which not every python3 has.
# The launch agent passes the interpreter that does; a hand start falls back to
# whichever python3 the current PATH resolves.
export PFC_PYTHON="${PFC_PYTHON:-$(command -v python3)}"
# The chat panel's claude. The launch agent can name a specific binary; a hand start
# falls back to whichever claude the current PATH resolves. claude reads its login
# from the keychain under USER, which a bare environment does not always set.
export PFC_CLAUDE="${PFC_CLAUDE:-$(command -v claude || echo claude)}"
export USER="${USER:-$(id -un)}"

# Install when there is nothing installed, and reinstall when the lockfile has
# changed since the last install (npm writes node_modules/.package-lock.json on
# every install). Without the second test a checkout that gained a dependency
# keeps its old node_modules, the build fails, and the launch agent restarts forever.
lockfile_changed() {
  [ ! -f node_modules/.package-lock.json ] || [ package-lock.json -nt node_modules/.package-lock.json ]
}

if [ ! -d node_modules ]; then
  echo "[pfc-web] installing dependencies"
  npm ci
elif lockfile_changed; then
  echo "[pfc-web] package-lock.json changed, reinstalling dependencies"
  npm ci
fi

newer_than() {  # newer_than <stamp>: some source file changed after the stamp
  [ -n "$(find "${SOURCES[@]}" -newer "$1" -print -quit 2>/dev/null)" ]
}

# The source changed since the served build, and not only since a build that failed.
needs_build() {
  [ ! -f "$ENTRY" ] && return 0
  [ -f "$SERVED" ] || touch -r "$ENTRY" "$SERVED"
  newer_than "$SERVED" || return 1
  [ ! -f "$FAILED" ] || newer_than "$FAILED"
}

# Builds into $NEXT. The stamp is taken before the build reads anything, so a file
# saved while it runs counts as newer than this build.
build_next() {
  touch "$STARTED"
  rm -rf "$NEXT"
  if PFC_WEB_OUT_DIR="./$NEXT" npm run build; then
    return 0
  fi
  mv "$STARTED" "$FAILED"
  rm -rf "$NEXT"
  return 1
}

swap_in() {
  rm -rf "$DIST"
  mv "$NEXT" "$DIST"
  mv "$STARTED" "$SERVED"
  rm -f "$FAILED"
}

NODE=""

start_server() {
  echo "[pfc-web] serving http://$HOST:$PORT with python $PFC_PYTHON and claude $PFC_CLAUDE"
  node "$ENTRY" &
  NODE=$!
}

stop_server() {
  if [ -n "$NODE" ]; then
    kill "$NODE" 2>/dev/null || true
    wait "$NODE" 2>/dev/null || true
    NODE=""
  fi
}

# Waits while a chat reply is being written or a change saved. A server that does
# not answer has nothing running to protect.
wait_idle() {
  local said=""
  while curl -s --max-time 5 "http://$HOST:$PORT/api/build" | grep -q '"busy":true'; do
    if [ -z "$said" ]; then
      echo "[pfc-web] new build ready; waiting for a chat reply or a save to finish"
      said=1
    fi
    sleep 5
  done
}

if needs_build; then
  echo "[pfc-web] building"
  if build_next; then
    swap_in
  elif [ ! -f "$ENTRY" ]; then
    echo "[pfc-web] build failed and there is no earlier build to serve"
    exit 1
  else
    echo "[pfc-web] build failed; serving the previous build until the source changes again"
  fi
fi

trap 'stop_server; exit 0' TERM INT HUP
start_server

while true; do
  sleep "$CHECK_SECONDS" &
  wait $! || true
  if ! kill -0 "$NODE" 2>/dev/null; then
    status=0
    wait "$NODE" || status=$?
    echo "[pfc-web] server exited with status $status"
    exit "$status"
  fi
  if lockfile_changed; then
    echo "[pfc-web] package-lock.json changed; restarting to reinstall"
    wait_idle
    stop_server
    exit 0
  fi
  if needs_build; then
    echo "[pfc-web] web source changed; building the new version"
    if build_next; then
      wait_idle
      stop_server
      swap_in
      start_server
    else
      echo "[pfc-web] build failed; still serving the previous build until the source changes again"
    fi
  fi
done
