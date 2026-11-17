# reMarkable pages

Optional. An inbox page, the web home page drawn as three pages, the one due review and the task list on a reMarkable Paper Pro (or a reMarkable 2), so the system goes wherever the tablet goes. Each page is a separate document at the top level of the tablet, never in a folder, so it is the first thing you see. The one folder is `AI News`, if you turn that on ([`ai-news.md`](ai-news.md)).

| Page | Web group | What a pen can change |
|---|---|---|
| `0 - Inbox` | Not on the web page: a ruled page for free notes | Write anything for the system. Each note becomes a card in Trello's 📥 Inbox list, word for word, for `/pfc-trello-inbox` to process |
| `1 - Today` | Today: Body first, the rating, Habits, The 2+1, Week | Circle 1–5 for Energy, Mood and Focus (while the day is unrated), optionally Hyperfocused Yes/No; tick a 2+1 task done; tick **swap** to drop a pick (it stays open); tick a suggested task to pick it (tomorrow's from about 6 PM); tick a daily or monthly habit (watch-logged habits are marked *); the Why line and What needs you, as on the web; **Note for the agent** box |
| `2 - This quarter` | This quarter: Focuses, Projects, Trends | Tick **park** on a focus; **Note for the agent** box for focus changes and project updates (name the project) |
| `3 - Always` | Always: Areas, Values, Visions, Front of mind (household rooms only when not parked: `household_parked` in `config/automation_config.yaml`) | Circle G, Y or R on an area you set by hand (or highlight the row), with the why in the note box; an area lit by its items shows why instead and cannot be circled; **Note for the agent** box |
| `4 - Review` | The web Review page (`/review`) | The one due review (`review_forms.py`), as a form: circle an option per row, write on the note and prompt lines, or tick **skip this review**. The answers run `/pfc-review <id> answers <json> unattended`, which carries out every answer and stamps the review; a review with more rows than one page holds stays due and the next page carries on after the rows done |
| `5 - Tasks` | The web Tasks page (`/tasks`), several pages | Every open task in priority order (AA first), about 16 a page. Tick a task done; tick **drop** to remove it; write on or beside a task for a note about it (sent to the inbox as `Note on task "…": …`); a note box on each page |

Notes from a "Note for the agent" box go to the Trello inbox tagged with their page (`From the Today page: …`), so "make reading 20 minutes" is read as the habit. Free writing anywhere else on a page that is not an answer to a printed spot is a note too, and any other handwriting arrives as `Also written on the … page: …`. No handwriting is dropped. Inbox notes wait in Trello until you run `/pfc-trello-inbox`.

## How it runs

The `pfc-remarkable-sync` timer runs `automations/scripts/remarkable_sync.py` every 10 minutes on the server. A quiet run (no ink, no new commit in the hour) is a few cloud checks, about a second of CPU, and no Claude tokens; a page with ink costs one Claude read. One run:

1. Asks the reMarkable cloud whether each page changed since it was uploaded (`rmapi stat`). A page changed in the last 5 minutes, or opened in the last 10 (`OPEN_MINUTES`, from rmapi's tree cache), is left alone until you have finished with it.
2. For a changed page with writable spots: downloads it, reads the pen strokes from the `.rm` files (`remarkable_lines.py`, the v6 format), draws them over the page as uploaded, and only when there is ink asks Claude (`claude -p`, Read only) which spots are marked.
3. Saves each mark through `web_write.py`, the web page's writer (lock, commit, push): `rate-day` (only when Energy, Mood and Focus are all circled), `complete-task`, `drop-task`, `drop-pick`, `set-picks`, `log-habit` for the page's date, `park-focus`, `set-area` with the reason as its note. Notes go to Trello's 📥 Inbox list (`trello_helper.create_card`). Then renders Trello once.
4. Draws the pages fresh from `home_data.build_home` (`remarkable_pages.py`) and replaces each one whose picture changed or that was just read. Replacing a page clears the ink. A page that was only opened is not redrawn.

Pages are named with a number first so they sort together. A name dropped from `PAGE_NAMES` is read one last time, then deleted from the tablet. A page that cannot be read is kept with its ink and retried on the next two runs, then redrawn with an agent reply saying it could not be read.

**Trello must be set up** (`TRELLO_API_KEY`, `TRELLO_API_TOKEN`, `TRELLO_INBOX_LIST_ID` in `.env`) for notes to go anywhere. A note that could not be sent is named in the page's agent strip ("Could not send 1 note…"); the page is still redrawn, so write it again.

### Duplicate pages

Redrawing a page deletes it and uploads a new one. If the tablet has the page open at that moment, it keeps its open copy, and two pages with the same name appear. Two guards:

1. **Prevent:** a page opened in the last 10 minutes is not redrawn.
2. **Heal:** when the cloud holds two or more top-level pages with one name, the run downloads each by id, reads its ink against its own picture and its own spots (kept per uploaded document in `state.json` `uploads` for 3 days), saves what it finds, deletes every copy and uploads one fresh page. Inbox notes already sent from a copy are not sent again.

State lives in `data/.remarkable/` (git-ignored): `state.json`, the uploaded PNG and PDF, the last download and the overlay image Claude read.

## Agent replies

Every page's top-right corner shows the agent's last few replies on that page from the last 36 hours, newest first (`automations/scripts/remarkable_replies.py`, stored in `data/.remarkable/replies.ndjson`):

| Reply | Written by |
|---|---|
| `Saved: …`, what the sync saved from the page | `remarkable_sync.py` after it reads a page |
| `Sent N notes to the Trello inbox`, or `Could not send N notes…` | the sync |
| `Saved your <review> answers`, then each question the review asked as `Asked: … I went with: …` | `run_review` in `remarkable_sync.py`, from the open-questions table of the headless `/pfc-review` |
| `Could not read what you wrote here …` | the sync, after three failed reads |

Answering is writing anywhere on the page: the note goes to the inbox with that page's recent replies in the card's description, so the agent reading it knows which question it answers.

## Setup (once, on the server)

1. Install `rmapi` (the maintained [ddvk fork](https://github.com/ddvk/rmapi/releases)) into `~/.local/bin`.
2. Sign in: get a one-time code at https://my.remarkable.com/device/browser/connect, then `echo CODE | ~/.local/bin/rmapi ls`. The token is saved in `~/.config/rmapi/rmapi.conf`; it never goes in the repo.
3. `pip3 install --user pillow` (the pages are drawn with Pillow; DejaVu fonts are used when installed).
4. Claude runs headless with `CLAUDE_CODE_OAUTH_TOKEN` from `.env`.
5. Set `PFC_REMARKABLE_SYNC=1` in `.env`, then run `automations/systemd/install.sh`, which installs and starts the timer.

The free reMarkable cloud sync is enough: it covers files opened or synced in the last 50 days, and these pages are replaced every day.

## Running it by hand

- `python3 automations/scripts/remarkable_pages.py OUT_DIR`: draw the pages to files without uploading (a safe first check).
- `python3 automations/scripts/remarkable_sync.py --dry-run`: read marks and log what would be saved; writes and uploads nothing.
- `python3 automations/scripts/remarkable_sync.py`: one run. `--force-upload` replaces every page now.
- `journalctl --user -u pfc-remarkable-sync -n 50`: the last runs.

Optional settings in `.env`: `PFC_RMAPI` (path to rmapi), `PFC_CLAUDE`, `PFC_PYTHON`, `PFC_RM_WIDTH` (stroke coordinate width: 1620 on the Paper Pro, 1404 on a reMarkable 2). The pen a redrawn page opens with is `PEN` in `remarkable_sync.py`.

## Changing what the pages show

The pages mirror the web home page's groups and bands in the page's order. A band added to or removed from `web/src/pages/index.astro` gets the same change in `remarkable_pages.py`. A writable spot is added with `page.mark(...)` and handled in `plan_writes` in `remarkable_sync.py`, through a `web_write.py` command. Tests: `pytest automations/scripts/tests/test_remarkable.py` (skipped when Pillow is not installed).
