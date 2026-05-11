#!/usr/bin/env bash
# Tests for the date-grounding safeguards.
#
# Verifies:
#   1. scripts/hook-session-date.sh outputs the correct local-timezone date.
#   2. scripts/validate.sh detects future-dated records in each guarded file.
#
# Usage: scripts/test-date-guards.sh
# Exit 0 = all tests pass; exit 1 = any test failed.
#
# Safety: each future-date test backs up the target NDJSON file, injects a
# bad record, runs the validator, then restores the original. If any step
# fails, the trap restores all backups before exiting.

set -u
cd "$(dirname "$0")/.."

PASS=0
FAIL=0
BACKUPS=()

cleanup() {
  for backup in "${BACKUPS[@]:-}"; do
    [ -z "$backup" ] && continue
    original="${backup%.test-bak}"
    if [ -f "$backup" ]; then
      mv "$backup" "$original"
    fi
  done
}
trap cleanup EXIT

backup_and_inject() {
  local file="$1"
  local injected_record="$2"
  cp "$file" "$file.test-bak"
  BACKUPS+=("$file.test-bak")
  echo "$injected_record" >> "$file"
}

restore() {
  local file="$1"
  if [ -f "$file.test-bak" ]; then
    mv "$file.test-bak" "$file"
    # Remove from BACKUPS array
    local new=()
    for b in "${BACKUPS[@]}"; do
      [ "$b" != "$file.test-bak" ] && new+=("$b")
    done
    BACKUPS=("${new[@]:-}")
  fi
}

pass() { echo "  ✓ $*"; PASS=$((PASS+1)); }
fail() { echo "  ✗ $*" >&2; FAIL=$((FAIL+1)); }

# ── Test 1: hook outputs the local-timezone date ──────────────────────────────
LOCAL_TZ="${LOCAL_TZ:-America/Denver}"
echo "[1/4] hook-session-date.sh outputs local date in $LOCAL_TZ"
EXPECTED_DATE=$(TZ="$LOCAL_TZ" date '+%Y-%m-%d')
HOOK_OUT=$(scripts/hook-session-date.sh)
if echo "$HOOK_OUT" | grep -qF "$EXPECTED_DATE"; then
  pass "hook output contains today's local date ($EXPECTED_DATE)"
else
  fail "hook output missing expected date $EXPECTED_DATE"
  echo "$HOOK_OUT" >&2
fi
if echo "$HOOK_OUT" | grep -qF "$LOCAL_TZ"; then
  pass "hook output mentions $LOCAL_TZ"
else
  fail "hook output should mention timezone $LOCAL_TZ"
fi

# ── Test 2: validator catches future-dated tasks ──────────────────────────────
echo "[2/4] validator catches future-dated tasks.ndjson record"
FUTURE=$(TZ="${LOCAL_TZ:-America/Denver}" date -d '+3 days' '+%Y-%m-%d')
FUTURE_ID="task-$(echo "$FUTURE" | tr -d '-')-999"
BAD_TASK="{\"id\":\"$FUTURE_ID\",\"status\":\"open\",\"description\":\"test future-dated record\",\"size\":\"S\",\"location\":\"PC\",\"impact\":\"low\",\"urgency\":\"low\",\"project\":\"none\",\"deadline\":null,\"created\":\"$FUTURE\",\"completed\":null,\"source\":\"test\"}"
backup_and_inject 5-actions/_data/tasks.ndjson "$BAD_TASK"
if scripts/validate.sh 2>&1 | grep -qE "future-dated.*$FUTURE_ID"; then
  pass "validator flagged future-dated task as expected"
else
  fail "validator did NOT flag future-dated task ($FUTURE_ID, created=$FUTURE)"
fi
restore 5-actions/_data/tasks.ndjson

# ── Test 3: validator catches future-dated daily-focus record ────────────────
echo "[3/4] validator catches future-dated daily-focus.ndjson record"
EXISTING_TASK_ID=$(jq -r 'select(.status=="open") | .id' 5-actions/_data/tasks.ndjson | head -1)
BAD_FOCUS="{\"date\":\"$FUTURE\",\"critical\":[\"$EXISTING_TASK_ID\",\"$EXISTING_TASK_ID\"],\"bonus\":null,\"completed\":[],\"bonus_completed\":false}"
backup_and_inject 5-actions/_data/daily-focus.ndjson "$BAD_FOCUS"
if scripts/validate.sh 2>&1 | grep -qE "daily-focus.ndjson.*future-dated.*$FUTURE"; then
  pass "validator flagged future-dated daily-focus as expected"
else
  fail "validator did NOT flag future-dated daily-focus ($FUTURE)"
fi
restore 5-actions/_data/daily-focus.ndjson

# ── Test 4: validator catches unknown active persona ─────────────────────────
echo "[4/4] validator catches unresolvable active persona"
if [ -f config/persona.yaml ]; then
  cp config/persona.yaml config/persona.yaml.test-bak
  BACKUPS+=("config/persona.yaml.test-bak")
  echo "active: nonexistent-test-persona-zzz" > config/persona.yaml
  if scripts/validate.sh 2>&1 | grep -qE "active persona 'nonexistent-test-persona-zzz' has no"; then
    pass "validator flagged unresolvable persona as expected"
  else
    fail "validator did NOT flag unresolvable persona"
  fi
  restore config/persona.yaml
else
  echo "  (skipped — config/persona.yaml not present)"
fi

# ── Result ────────────────────────────────────────────────────────────────────
echo
if [ "$FAIL" -eq 0 ]; then
  echo "✅ All $PASS date-guard tests passed."
  exit 0
else
  echo "❌ $FAIL of $((PASS+FAIL)) tests failed."
  exit 1
fi
