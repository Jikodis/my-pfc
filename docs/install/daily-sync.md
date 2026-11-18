# Daily sync launch agent on the Mac

Optional. Runs `scripts/daily-sync.sh` once a day, at 5:00 AM local when the Mac is awake with a
working network, and otherwise at the first hourly firing after that (see "When it runs").
It runs four syncs that need no person:

1. **Trello completions:** `python3 automations/scripts/trello_writeback.py sync`, the same call `pfc-sync-trello` makes. The script then commits exactly the paths that sync changed, by explicit path, as `track: trello sync <YYYY-MM-DD>`, and pushes.
2. **Gmail inbox to task reconcile:** `claude -p "/pfc-email-triage Run only Step 0 ..." --permission-mode auto`. The prompt tells Claude to commit only the files it changed, by explicit path, and push. This step needs Claude because it uses the Gmail connector.
3. **Calendar cache:** `claude -p "/pfc-render-trello Run only Step 1 (not Step 1b) ..." --permission-mode auto`. Fetches Calendar from yesterday through 7 days after today and writes `data/calendar-cache.json` the way that step does, then commits only that file, by explicit path, as `track: refresh calendar cache`, and pushes. The TRMNL `pfc-week` screen and the Trello timers read this snapshot; the screen calls it stale after about 26 hours, so it needs a writer every day.
4. **Calendar-derived habits:** `python3 automations/scripts/derive_calendar_habits.py`, no Claude. Logs every `auto_derived` habit with a `calendar:` rule in `config/habit_schema.yaml` from the cache step 3 just wrote: one rep per date with a matching event that has started, so last night's class is logged this morning. If `7-habits/_data/habits-daily.ndjson` or `habits-monthly.ndjson` changed, the script commits only those, by explicit path, as `habit: calendar log <YYYY-MM-DD>`, and pushes.

Steps 2 and 3 each run as their own `claude -p`; every step logs its own `START` / `OK` / `FAIL` line. Without the Gmail or Calendar connector ([`connectors.md`](connectors.md)), that step fails and the others still run.

Every run ends with one summary line, `<timestamp> DONE ok=<n> fail=<n>`, counting the steps that logged `OK` and `FAIL`. A run that a guard skipped is `DONE ok=0 fail=1`, including a busy lock or a timeout kill. The web UI home page reads the last `DONE` line (`daily_sync` in `automations/scripts/home_data.py`, log path from `PFC_DAILY_SYNC_LOG`) and shows one line at the bottom of the Today band: green `Daily sync ran Mon 5:00 AM` when `fail=0` and the run is under 30 hours old; red `Daily sync failed <day, time>` when `fail` is above 0; red `Daily sync last OK <day, time>` when the last run is over 30 hours old; red `Daily sync has not run` when the log has no `DONE` line.

## Turn it on

The job runs headless Claude, so it is off until you opt in: add `PFC_DAILY_SYNC=1` to `.env`. Without it the script exits at once and writes nothing.

## When it runs

The launch agent fires every hour from 5:00 AM to 10:00 PM. `automations/scripts/daily_sync_gate.py` decides what each firing does, before the script takes the lock or writes anything:

| Today's log says | This firing |
| --- | --- |
| No run yet, and `github.com` and `api.trello.com` both answer | Runs every step |
| No run yet, and either host is unreachable | Exits. Logs `WAIT no network` once a day and no `DONE` line |
| The last `DONE` has `fail=0` | Exits silently until tomorrow |
| The last `DONE` has a failure | Runs again, skipping every step that already logged `OK` today, so a retry that fixes the one failed step ends with `fail=0` |
| Three `RUN attempt` lines already | Exits silently. A step that fails for a reason other than the network is not retried all day, because each retry of a Claude step costs tokens |

A run a guard stopped (dirty tree, busy lock, wrong branch) logs no `RUN attempt` line, so it does not use up one of the three attempts and the next hour tries again.

Why hourly: a 5:00 AM firing on a Mac asleep on battery runs inside short wakes with no usable network, so a single fixed time can skip the whole run or time out a step. The real run also holds a `caffeinate -i` assertion so the Mac does not go back to sleep between steps.

`scripts/daily-sync.sh --force` runs every step now, whatever today's log says (the opt-in flag still applies).

## Guards

Before step 1 the script checks the following, in order. Each failed check logs one line and exits 0 without changing anything, so a skipped day is visible in the log and never a half-run:

| Check | Log line | Why |
| --- | --- | --- |
| The web writer's lock `data/.web-write.lock` is free (the script holds it for the whole run, through `automations/scripts/with_write_lock.py`) | `FAIL write lock busy, skipped` | The job never races a button press in the web UI |
| The repo is on `PFC_WRITE_BRANCH` (default `main`) | `FAIL not on main (on <branch>), skipped` | Data never lands on a feature branch |
| `git status --porcelain` shows nothing | `FAIL dirty tree, skipped` | In-progress edits never get swept into a bot commit; everything the job commits is something it changed |
| `git pull --rebase` succeeds (`automations/scripts/daily_sync_git.py sync`, the same sync and GitHub credentials as `web_write.py`) | `FAIL sync with origin: <reason>, skipped` | The job edits the newest copy and its push is not rejected |

After the guards, a failing step is logged as `FAIL <step>` and the next step still runs.

The whole run holds the web writer's lock, so a hung `claude -p` would block every web write. `with_write_lock.py` kills the run, with its whole process group, after `PFC_LOCK_TIMEOUT_SECONDS` (default 1200, 20 minutes), logs `FAIL command timed out after <n> seconds, killed`, and frees the lock.

## Prerequisites

Same as the web UI ([`web-ui.md`](web-ui.md)): a python3 with PyYAML, Claude Code logged in for this repo, `gh` able to push the repo, and `TRELLO_*` values in `.env`. Run it from the `main` checkout. If the active `gh` account is not the one that can push, uncomment `PFC_PUSH_GH_USER` in the plist, as for the web UI.

## Install

`automations/launchd/com.pfc.daily-sync.plist` is a template with the same four placeholders as the web UI's. From the repo root:

```bash
REPO="$(pwd)"
sed -e "s#__REPO_ROOT__#$REPO#g" -e "s#__USER__#$(id -un)#g" \
    -e "s#__PATH__#$(dirname "$(command -v claude)"):$(dirname "$(command -v gh)"):/usr/bin:/bin:/usr/sbin:/sbin#g" \
    -e "s#__PYTHON__#$(command -v python3)#g" \
    automations/launchd/com.pfc.daily-sync.plist > ~/Library/LaunchAgents/com.pfc.daily-sync.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.pfc.daily-sync.plist
launchctl print gui/$(id -u)/com.pfc.daily-sync | head
```

Edit `LOCAL_TZ` in the installed plist if you are not on `America/Denver`. Run it once now instead of waiting for the next hour: `launchctl kickstart gui/$(id -u)/com.pfc.daily-sync`, or `scripts/daily-sync.sh` from the repo root. Both follow the table under "When it runs"; add `--force` to the script to run every step regardless.

After a plist change, write it again, then `launchctl bootout gui/$(id -u)/com.pfc.daily-sync` and bootstrap again.

## Second clone on a server: keep the Mac current

If a server (a VPS running the systemd timers) also commits to the repo, `automations/launchd/com.pfc.repo-sync.plist` pulls `main` into the Mac clone every 5 minutes, fast-forward only, so the web UI shows what the server saved. It never stashes, rebases or touches local commits.

```bash
sed -e "s#__REPO_ROOT__#$(pwd)#g" automations/launchd/com.pfc.repo-sync.plist > ~/Library/LaunchAgents/com.pfc.repo-sync.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.pfc.repo-sync.plist
```

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
