# Web UI launch agent (macOS)

Runs the PFC web UI as a background service at `http://127.0.0.1:4323`, starting at
login and restarting if it exits. It serves the production build; `run-web.sh` rebuilds
first whenever `web/src`, `astro.config.mjs`, or `package.json` is newer than the build,
and runs `npm ci` first when `package-lock.json` is newer than the last install.

**Tier:** local only. Nothing here touches a server you may run other automations on, and the web server never leaves `127.0.0.1`.

Rules for working on the app itself: [`web/AGENTS.md`](../../web/AGENTS.md).
The daily Trello and Gmail syncs run from a second launch agent: [`daily-sync.md`](daily-sync.md).

## Prerequisites

- The repo cloned on your Mac. Copy the two plists in `automations/launchd/` and replace
  `/Users/YOUR_USER/path/to/your-pfc` with that path and `YOUR_USER` with your account name.
- Node and npm, git, gh (optional), and jq. The plist puts Homebrew's `/opt/homebrew/bin` on
  `PATH`; change it if yours live elsewhere.
- A python3 with PyYAML (`pip install -r automations/requirements.txt`). The plist passes it
  as `PFC_PYTHON`; `/usr/bin/python3` does not have PyYAML.
- Claude Code logged in for this repo, for the chat panel. The plist passes the binary as
  `PFC_CLAUDE` (`/Users/YOUR_USER/.local/bin/claude` by default), puts its folder on `PATH`,
  and sets `USER`, which claude needs to find its login in the keychain. Check it with the
  environment the agent gets:
  `cd <your-repo> && env -i HOME=$HOME USER=$USER PATH=$HOME/.local/bin:/opt/homebrew/bin:/usr/bin:/bin $HOME/.local/bin/claude auth status`
  should print `"loggedIn": true`.
- Push credentials that work without a prompt (a credential helper or an SSH key), since
  the launch agent cannot answer one. Or set `PFC_PUSH_GH_USER` in the plist to a GitHub
  account gh is logged in as: the writer then pushes with that account's token, read from
  the gh keyring per push and never stored, whichever gh account is active.
  `gh auth token --user <that account>` must print a token.

## Chat panel files

- `web/.chat-sessions.json` holds the ids of the conversations this server started,
  the only ones the chat panel may resume. It is ignored by git. Deleting it only means
  older conversations start fresh. `PFC_CHAT_SESSIONS_FILE` moves it.
- `PFC_CHAT_MODEL` pins every chat run to one model (for example `sonnet`) whatever the
  page asks for. Unset, the page's choice or claude's default is used.
- Chat tuning, none set in the plist: `PFC_CHAT_TIMEOUT_MS` stops a chat run after that long
  (default 30 minutes), `PFC_CHAT_KILL_MS` is how long a stopped run gets before it is
  killed (default 5 seconds), `PFC_CHAT_KEEPALIVE_MS` is the quiet time before a
  keepalive frame goes out (default 15 seconds, never under 1 second), and
  `PFC_CHAT_KEEP_MS` is how long a finished run stays readable for a page that comes
  back to it (default 10 minutes).
- Writer overrides, none set in the plist: `PFC_WRITE_TIMEOUT_MS` is how long the server
  waits for `web_write.py` (default 2 minutes), `PFC_WRITE_COMMIT_TIMEOUT` is the writer's
  commit limit in seconds (default 60), `PFC_WEB_LOG` moves the writer's render log (default
  `/tmp/pfc-web.log`), and the tests use `PFC_WEB_WRITE` and `PFC_TRELLO_RENDER` to swap in
  a fake writer and a fake Trello render.

## Install

```bash
cp <your-repo>/automations/launchd/com.pfc.web.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.pfc.web.plist
sleep 20 && curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:4323/ && tail -5 /tmp/pfc-web.log
open http://127.0.0.1:4323/
```

Expected: `200`, and a `[pfc-web] serving http://127.0.0.1:4323` line in the log. The
first start is slow because it builds.

## Restart

**After a code change only** (anything under `web/src`, or a dependency change in
`web/package-lock.json`), with no change to the plist, restart the loaded job so
`run-web.sh` reinstalls when the lockfile changed, rebuilds, and serves the new code:

```bash
launchctl kickstart -k gui/$(id -u)/com.pfc.web
```

**After a plist change** (`com.pfc.web.plist` itself, such as `PFC_CLAUDE`, `USER`, `PFC_PUSH_GH_USER`, or
`PATH`), `kickstart -k` is not enough: it reuses the job definition already loaded and
never reads the new environment. Copy the plist again, then unload and load it:

```bash
cp <your-repo>/automations/launchd/com.pfc.web.plist ~/Library/LaunchAgents/
launchctl bootout gui/$(id -u)/com.pfc.web
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.pfc.web.plist
```

**Verify:** open `http://127.0.0.1:4323`, send one chat message in the drawer, and expect
a reply.

The daily summary opens the page itself as its last step,
through `scripts/open-web-ui.sh`. It opens nothing when the server is not answering, so
`Web UI not opened: nothing is answering at http://127.0.0.1:4323.` at the end of the
daily summary means the launch agent is down: restart it as above.

## Logs

```bash
tail -f /tmp/pfc-web.log
```

Both stdout and stderr land there.

## Uninstall

```bash
launchctl bootout gui/$(id -u)/com.pfc.web
rm ~/Library/LaunchAgents/com.pfc.web.plist
```

## Troubleshooting

- **A panel reads `Could not load this panel.`** The interpreter running the Python
  scripts lacks PyYAML. Check `PFC_PYTHON` in the plist; `/usr/bin/python3` does not
  have it. Verify the one in the plist with
  `env -i PATH=/usr/bin:/bin <PFC_PYTHON from the plist> -c 'import yaml; print(yaml.__version__)'`.
- **A page is blank.** Three causes, in the order to check them.
  - **After a code change:** the agent is still serving the old build. Restart it with
    the kickstart command above so `run-web.sh` rebuilds.
  - **A page reads `This page could not load` with a file name and a line number:** that
    line of that NDJSON file is not valid JSON, and every page reading the file answers
    the same way. Fix or remove the line, then reload. `scripts/validate.sh` finds it too.
  - **A page reads `This page could not load` and names `PFC_REPO_ROOT`:** the variable
    points somewhere that is not a PFC repo. Unset it to let the server find the repo by
    walking up from its working directory, or point it at the repo root.
- **Port 4323 answers nothing.** Read `/tmp/pfc-web.log` for the build error, and check
  the agent is loaded with `launchctl print gui/$(id -u)/com.pfc.web | head`.
- **The agent keeps restarting.** Read `/tmp/pfc-web.log`. A failing `npm run build` in
  there means the code does not compile, so fix it, or run `cd web && npm run build` by
  hand to see the full error. The agent waits 30 seconds between starts
  (`ThrottleInterval` in the plist), so a broken build loops slowly rather than every
  10 seconds.
- **The chat panel says `Could not start claude. The server log has the details.`**
  The file named by `PFC_CLAUDE` could not be started. Read the `[pfc-chat]` lines in
  `/tmp/pfc-web.log`: `ENOENT` means no file at that path, `EACCES` means it is not
  executable. Check the path in the plist against `ls -l "$(command -v claude)"`.
- **A chat reply ends with `claude stopped without a reply`.** claude started and quit.
  The same log line quotes its error output. Exit code 127 means a program claude needs
  is missing from `PATH` in the plist. A message about logging in means claude cannot see its login: run the `auth status`
  check under Prerequisites and check that `USER` is in the plist. After fixing the
  plist, copy it again, then bootout and bootstrap.
- **A button says `Saved. Not pushed yet.`** The change is committed on `main` locally;
  only the push failed. Read the `[pfc-write]` and git lines in `/tmp/pfc-web.log`. The
  usual cause is credentials (git cannot ask for a password from the launch agent).
  `remote: Repository not found.` means the push used a GitHub account that cannot see
  the repo: set `PFC_PUSH_GH_USER` in the plist and check that `gh auth status` lists
  that account. `gh is not on PATH; cannot read the push token.`
  means the folder that holds gh is missing from `PATH` in the plist. The next successful
  push, from the page or a terminal, sends the commit.
- **A button says `The repo is on branch ..., not main; nothing was changed.`** The launch
  agent's checkout was switched to another branch. Switch it back to `main`, or set
  `PFC_WRITE_BRANCH` in the plist to the branch the buttons should write to.
- **A button says `The repo's pre-commit hook is not installed; see docs/install/web-ui.md.`**
  The writer leaves validation to `.git/hooks/pre-commit` (it runs `scripts/validate.sh`),
  so it refuses to commit without it. Install both hooks from the repo root:
  `cp .githooks/* .git/hooks/ && chmod +x .git/hooks/{pre,post}-commit`.
- **A button says `Another change is still being saved.`** Another write holds the lock.
  `data/.web-write.lock` is released when the writing process exits, so a lock that
  stays means a writer is still running: check with `pgrep -fl web_write.py`, and wait
  for it (the server stops a writer after two minutes).
- **Stopping a server by hand.** Always by port: `kill $(lsof -tiTCP:4323 -sTCP:LISTEN)`.
  A name pattern can also match an unrelated server on the same machine.
