# Web UI install guide (local, optional)

The web UI is a one-page home for the system, served on your own machine at `http://127.0.0.1:4323`: today's 2+1, habits with Log buttons, the rating card, life areas, focuses, projects, the week, the one due rolling review (`/review`), and a chat panel that runs Claude Code skills in this repo. Every button writes the repo through one program, `automations/scripts/web_write.py`, which commits and pushes the change the same way a skill would.

It is optional. Every job it does also has a chat skill (`/pfc-log-day`, `/pfc-log-habit`, `/pfc-pick-tasks`, `/pfc-review`, the evening check-in), so Tier 1 users can skip this page entirely.

**Where it runs:** on the machine that has your clone. The server listens on `127.0.0.1` only and is never exposed to the network. The instructions below install it as a macOS launch agent; on Linux, run `automations/scripts/run-web.sh` under a systemd user service the same way (`Restart=always`, the same environment variables).

Rules for working on the app itself: [`web/AGENTS.md`](../../web/AGENTS.md).

---

## Prerequisites

- Tier 1 done: the repo cloned, Claude Code logged in, the git hooks installed (`cp .githooks/* .git/hooks/ && chmod +x .git/hooks/{pre,post}-commit`). **The writer refuses to commit without the pre-commit hook**, because `scripts/validate.sh` runs there.
- Node 22.12 or later and npm (the version Astro requires).
- A `python3` with PyYAML (`pip install -r automations/requirements.txt`, or the `.venv` from [`local-automations.md`](local-automations.md)).
- `git`, `jq`, and `claude` (for the chat panel) on the `PATH` you give the launch agent.
- The repo on the branch the buttons write to: `main` by default (`PFC_WRITE_BRANCH` changes it).

Check the pieces from the repo root:

```bash
node --version && npm --version
python3 -c 'import yaml; print(yaml.__version__)'
python3 automations/scripts/web_data.py --home | head -c 200; echo
python3 automations/scripts/web_write.py --dry-run log-habit morning-walk
```

The last line prints one JSON object and changes nothing (`"dry_run": true`). Use one of your own habit ids.

## Try it by hand first

```bash
bash automations/scripts/run-web.sh
```

The first start runs `npm ci` and builds, which takes a minute. Then open `http://127.0.0.1:4323/`. Stop it with Ctrl-C.

## Install as a macOS launch agent

`automations/launchd/com.pfc.web.plist` is a template. Fill in its four placeholders and load it:

```bash
REPO="$(pwd)"
sed -e "s#__REPO_ROOT__#$REPO#g" -e "s#__USER__#$(id -un)#g" \
    -e "s#__PATH__#$(dirname "$(command -v claude)"):$(dirname "$(command -v node)"):/usr/bin:/bin:/usr/sbin:/sbin#g" \
    -e "s#__PYTHON__#$(command -v python3)#g" \
    automations/launchd/com.pfc.web.plist > ~/Library/LaunchAgents/com.pfc.web.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.pfc.web.plist
sleep 30 && curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:4323/ && tail -5 /tmp/pfc-web.log
```

Expected: `200`, and a `[pfc-web] serving http://127.0.0.1:4323` line in the log. Edit `LOCAL_TZ` in the installed plist if you are not on `America/Denver`. Make sure the `PATH` you wrote also finds `git`, `jq` and `npm`.

Check that the chat panel's `claude` can see its login under the agent's bare environment:

```bash
env -i HOME=$HOME USER=$USER PATH="<the PATH from the plist>" claude auth status
```

It should print `"loggedIn": true`.

## What the buttons write

Every button runs one `web_write.py` action. The writer refuses unless the repo is on `PFC_WRITE_BRANCH`, takes the lock `data/.web-write.lock`, pulls first (`repo_sync.py`: a rebase on a clean tree, a fast-forward with uncommitted edits, never a stash), changes only the records the action needs, commits only those paths (the pre-commit hook validates), pushes, and starts a Trello render in the background (without Trello credentials it only logs a missing-credentials line to `/tmp/pfc-web.log`; `--no-render` skips it).

| Action | Writes |
|---|---|
| `complete-task`, `drop-task` | `6-tasks/_data/tasks.ndjson`, `task_events.ndjson`, the day's `daily-focus.ndjson` record (a dropped task that was ever picked or skipped moves to `tasks-archive.ndjson`) |
| `log-habit` (today or up to 7 days back) | `7-habits/_data/habits-daily.ndjson` or `habits-monthly.ndjson`, one row per habit and date |
| `rate-day` (today or yesterday) | `data/day-tracking.ndjson`: energy, mood, focus, the derived `rating`, optional `hyperfocused` |
| `set-picks`, `skip-suggestion` (today or tomorrow) | `6-tasks/_data/daily-focus.ndjson`: the 2+1, and `skipped` for suggestions you turned down |
| `park-focus` | `4-focus/_data/focus.ndjson` `parked` |
| `set-area`, `set-room` | a new snapshot in `2-areas/_data/life-wheel.ndjson` or `household-status.ndjson` |
| `retire-anchor` | `data/grounding.ndjson` |
| `set-project` | `5-projects/_data/projects.ndjson` `active` / `status` |
| `stamp-review`, `review-seen` | `data/review-ledger.ndjson` `last_done`, and `seen` for a review answered over several sittings |

A scheduled job of your own that commits to the repo can run under the same lock so it never races a button press: `python3 automations/scripts/with_write_lock.py -- <command>` skips the run (exit 0, one line in `/tmp/pfc-locked-jobs.log`) while a write is in progress.

## Settings

Set these in the plist's `EnvironmentVariables`, none required:

| Variable | What it does |
|---|---|
| `PFC_WRITE_BRANCH` | The branch the buttons commit to (default `main`) |
| `PFC_PUSH_GH_USER` | A gh account to push as when the active one cannot push this repo; its token is read from the gh keyring per push, never stored |
| `PFC_WRITE_TIMEOUT_MS`, `PFC_WRITE_COMMIT_TIMEOUT` | How long the server waits for a write (default 2 minutes), and the commit's own limit in seconds (default 60) |
| `PFC_CHAT_MODEL` | Pin every chat run to one model |
| `PFC_CHAT_TIMEOUT_MS` | Stop a chat run after this long (default 30 minutes) |
| `PFC_WEB_CHECK_SECONDS` | How often `run-web.sh` checks for a source change (default 20) |
| `PFC_WEB_LOG` | Where the writer's background render logs go (default `/tmp/pfc-web.log`) |

`web/.chat-sessions.json` holds the ids of the conversations this server started, the only ones the chat panel may resume. It is ignored by git.

## Updates

A code change needs no restart. Every 20 seconds `run-web.sh` checks whether `web/src`, `web/public`, `astro.config.mjs`, `package.json` or `package-lock.json` is newer than the build it serves. If so it builds beside the old build, waits until no chat reply or save is running, and swaps the new one in with about a second of downtime. Open pages reload themselves. A failed build leaves the old one serving. A changed `package-lock.json` makes the script exit once idle, so launchd restarts it and it reinstalls.

After editing `run-web.sh` itself: `launchctl kickstart -k gui/$(id -u)/com.pfc.web`. After editing the installed plist, `kickstart` is not enough; unload and load it:

```bash
launchctl bootout gui/$(id -u)/com.pfc.web
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.pfc.web.plist
```

## Logs and uninstall

```bash
tail -f /tmp/pfc-web.log
launchctl bootout gui/$(id -u)/com.pfc.web && rm ~/Library/LaunchAgents/com.pfc.web.plist   # uninstall
```

## Troubleshooting

- **A panel reads `Could not load this panel.`** The interpreter running the Python scripts lacks PyYAML. Check `PFC_PYTHON` in the plist.
- **A page reads `This page could not load` with a file name and line number.** That line of that NDJSON file is not valid JSON. Fix it; `scripts/validate.sh` finds it too.
- **Port 4323 answers nothing.** Read `/tmp/pfc-web.log` for the build error, and check the agent is loaded: `launchctl print gui/$(id -u)/com.pfc.web | head`.
- **A button says `Saved. Not pushed yet.`** The change is committed locally; only the push failed, usually credentials (git cannot prompt from a launch agent). Set `PFC_PUSH_GH_USER`, or fix the credential helper. The next successful push sends the commit.
- **A button says `The repo is on branch ..., not main; nothing was changed.`** Switch the checkout back, or set `PFC_WRITE_BRANCH`.
- **A button says `The repo's pre-commit hook is not installed`.** Install the hooks: `cp .githooks/* .git/hooks/ && chmod +x .git/hooks/{pre,post}-commit`.
- **A button says `Another change is still being saved.`** Another write holds the lock; `pgrep -fl web_write.py` shows it. The server stops a writer after two minutes.
- **A button says `A file this change needs has edits that are not committed yet.`** A skill or an editor left that data file modified. Commit or discard the edit, then press again.
- **The chat panel says `Could not start claude.`** The `PATH` in the plist does not find `claude`, or `USER` is missing. Run the `auth status` check above.
- **Stopping a server by hand:** by port, `kill $(lsof -tiTCP:4323 -sTCP:LISTEN)`.
