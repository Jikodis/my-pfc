# Daily sync launch agent (macOS)

Runs `scripts/daily-sync.sh` every day at 5:00 AM local (a Mac that is asleep then runs
it on wake). It runs three syncs that need no person:

1. **Trello completions:** `python3 automations/scripts/trello_writeback.py sync`, the same call `pfc-sync-trello` makes. The script then commits exactly the paths that sync changed, by explicit path, as `track: trello sync <YYYY-MM-DD>`, and pushes.
2. **Gmail inbox to task reconcile:** `claude -p "/pfc-email-triage Run only Step 0 ..." --permission-mode auto`. The prompt tells Claude to commit only the files it changed, by explicit path, and push. This step needs Claude because it uses the Gmail connector.
3. **Calendar cache:** `claude -p "/pfc-render-trello Run only Step 1 ..." --permission-mode auto`. Fetches the next 7 days from Calendar and writes `data/calendar-cache.json` the way that step does, then commits only that file, by explicit path, as `track: refresh calendar cache`, and pushes. The TRMNL `pfc-week` screen and the Trello timers read this snapshot; the screen calls it stale after about 26 hours, so it needs a writer every day.

Steps 2 and 3 each run as their own `claude -p`, so each logs its own `START` / `OK` / `FAIL` line.

Every run ends with one summary line, `<timestamp> DONE ok=<n> fail=<n>`, counting the steps that logged `OK` and `FAIL`. A run that a guard skipped is `DONE ok=0 fail=1`, including a busy lock or a timeout kill (`with_write_lock.py` writes that line itself). The web UI home page reads the last `DONE` line (`daily_sync` in `automations/scripts/home_data.py`, log path from `PFC_DAILY_SYNC_LOG`) and shows one line at the bottom of the page: green `Daily sync ran Mon 5:00 AM` when `fail=0` and the run is under 30 hours old; red `Daily sync failed <day, time>` when `fail` is above 0; red `Daily sync last OK <day, time>` when the last run is over 30 hours old; red `Daily sync has not run` when the log has no `DONE` line.

## Guards

Before step 1 the script checks the following, in order. Each failed check logs one line and exits 0 without changing anything, so a skipped day is visible in the log and never a half-run:

| Check | Log line | Why |
| --- | --- | --- |
| The web writer's lock `data/.web-write.lock` is free (the script holds it for the whole run, through `automations/scripts/with_write_lock.py`) | `FAIL write lock busy, skipped` | The job never races a button press in the web UI |
| The repo is on `PFC_WRITE_BRANCH` (default `main`) | `FAIL not on main (on <branch>), skipped` | Data never lands on a feature branch |
| `git status --porcelain` shows nothing | `FAIL dirty tree, skipped` | Someone's in-progress edits never get swept into a bot commit; everything the job commits is something it changed |
| `git pull --rebase` succeeds (`automations/scripts/daily_sync_git.py sync`, the same sync and GitHub credentials as `web_write.py`) | `FAIL sync with origin: <reason>, skipped` | The job edits the newest copy and its push is not rejected |

After the guards, a failing step is logged as `FAIL <step>` and the next step still runs. Each step logs a timestamped `START`, `OK` or `FAIL` line.

The whole run holds the web writer's lock, so a hung `claude -p` would block every web write. `with_write_lock.py` kills the run, with its whole process group, after `PFC_LOCK_TIMEOUT_SECONDS` (default 1200, 20 minutes), logs `FAIL command timed out after <n> seconds, killed`, and exits 0, which frees the lock.

## Prerequisites

Same as the web UI ([`web-ui.md`](web-ui.md)): the repo path filled into the plist, a python3 with PyYAML (the plist passes it as `PFC_PYTHON`), Claude Code logged in for this repo (the plist sets `PATH` and `USER` the same way), and `TRELLO_*` values in `.env`. Run it from the `main` checkout. If the web UI's plist sets `PFC_PUSH_GH_USER`, set the same value here, so both push as the same GitHub account.

Steps 2 and 3 need the Gmail and Google Calendar connectors; without them those two steps log `FAIL` and the Trello step still runs. Drop a step from `scripts/daily-sync.sh` if you do not use that integration.

## Install

```bash
cp <your-repo>/automations/launchd/com.pfc.daily-sync.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.pfc.daily-sync.plist
launchctl print gui/$(id -u)/com.pfc.daily-sync | head
```

Run it once now instead of waiting for 5:00 AM: `launchctl kickstart gui/$(id -u)/com.pfc.daily-sync`, or `<your-repo>/scripts/daily-sync.sh`.

After a plist change, copy it again, then `launchctl bootout gui/$(id -u)/com.pfc.daily-sync` and bootstrap again.

## Log

```bash
tail -f /tmp/pfc-daily-sync.log
```

`PFC_DAILY_SYNC_LOG` moves the script's own log lines; the plist sends launchd's stdout and stderr to the same default file.

## Uninstall

```bash
launchctl bootout gui/$(id -u)/com.pfc.daily-sync
rm ~/Library/LaunchAgents/com.pfc.daily-sync.plist
```
