#!/usr/bin/env python3
"""Keep the PFC pages on the reMarkable current, and save what is written on them.

    python3 automations/scripts/remarkable_sync.py [--dry-run] [--force-upload]

Run every 10 minutes by the `pfc-remarkable-sync` timer. One run:

1. Ask the reMarkable cloud (`rmapi stat`, no Claude) whether each PFC page changed
   since this script last uploaded it. A page still being written on (changed in the
   last SETTLE_MINUTES) or opened in the last OPEN_MINUTES is left alone until a later
   run. Two or more pages with one name (the tablet kept a page it had open when it was
   redrawn) are each read, then replaced by one (`read_copies`).
2. For a changed page that has writable spots (`marks` from `remarkable_pages.py`):
   download it (`rmapi get`), read the pen strokes (`remarkable_lines.py`), and when
   there is ink, draw it over the page as uploaded and ask Claude (`claude -p`, Read
   only) which spots were marked. No ink means no Claude call, so a page that was
   only opened costs nothing.
3. Save each mark through `web_write.py`, the web page's own writer (lock, commit,
   push): a circled rating, a ticked 2+1 task, a ticked habit, a changed area light
   with its reason. Each note (the inbox page, a page's note box, writing beside a
   task) becomes a card in Trello's 📥 Inbox list, word for word, for
   `/pfc-trello-inbox`. A filled review form runs `/pfc-review <id> answers <json>
   unattended`.
4. Draw the pages fresh from `home_data.build_home` and replace any page whose
   picture changed or that was just read. Replacing a page clears the ink on it; the
   "Agent" strip in each page's top-right corner (remarkable_replies.py) says what was
   saved from it and any question a headless review run asked, so a wrong reading is
   visible. When nothing was read and neither the repo (git HEAD) nor the hour changed
   since the last drawing, this step is skipped: a quiet run is a few `rmapi stat`
   calls, about a second of CPU.

State lives in `data/.remarkable/` (git-ignored): `state.json`, the uploaded pages
as PNG and PDF, downloads and the overlay images Claude read. The pages sit at the
top level of the tablet, never in a folder, so they are the first thing you see. A
page whose name left `PAGE_NAMES` is read one last time, then deleted from the tablet.

Exit 0 on success or a handled problem (logged with 🟡); 1 when the cloud cannot be
reached at all.
"""

import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
REPO = SCRIPT_DIR.parents[1]

import remarkable_lines  # noqa: E402
import remarkable_replies  # noqa: E402
import remarkable_pages  # noqa: E402

STATE_DIR = REPO / "data" / ".remarkable"
SETTLE_MINUTES = 5
# A page opened on the tablet in the last OPEN_MINUTES is neither read nor redrawn:
# replacing a page that is open deletes it under the reader, and the tablet keeps its
# open copy as a second page with the same name.
OPEN_MINUTES = 10
UPLOAD_KEEP_DAYS = 3
MAX_READ_TRIES = 3
RMAPI = os.environ.get("PFC_RMAPI") or shutil.which("rmapi") or str(Path.home() / ".local/bin/rmapi")
CLAUDE = os.environ.get("PFC_CLAUDE") or shutil.which("claude") or str(Path.home() / ".local/bin/claude")
PYTHON = os.environ.get("PFC_PYTHON") or sys.executable
TZ = ZoneInfo(os.environ.get("LOCAL_TZ", "America/Denver"))
# rmapi's copy of the cloud's file tree, refreshed by every rmapi command. `rmapi stat`
# shows neither when a page was opened nor a second page with the same name; this does.
RMAPI_CACHE = Path(os.environ.get("PFC_RMAPI_CACHE") or Path.home() / ".cache/rmapi/tree.cache")


def log(msg):
    print(f"{datetime.now(TZ).strftime('%Y-%m-%d %I:%M %p')} {msg}", flush=True)


# ---------------------------------------------------------------- the cloud
def rmapi(*args, cwd=None, timeout=180):
    p = subprocess.run([RMAPI, *args], cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True,
                       text=True, timeout=timeout)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def cloud_stat(name):
    """The page's metadata, or None when it is not on the tablet."""
    code, out = rmapi("stat", name)
    if code != 0:
        return None
    m = re.search(r"\{.*\}", out, re.S)
    return json.loads(m.group(0)) if m else None


# The pen a page opens with. A redraw is a new document, and rmapi's own PDF upload sets
# the fineliner as its last pen, so the page comes wrapped with this pen instead: the
# ballpoint on medium (sizes are "1" thin, "2" medium, "3" thick). Change it to taste.
PEN = {"LastTool": "Ballpointv2", "LastPen": "Ballpointv2", "LastBallpointv2Size": "2"}


def rmdoc_for(pdf, out_dir):
    """The PDF packaged as `<name>.rmdoc`, its `.content` set to open with PEN."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = str(uuid.uuid4())
    content = {"dummyDocument": False, "extraMetadata": dict(PEN), "fileType": "pdf",
               "fontName": "", "lastOpenedPage": 0, "lineHeight": -1, "margins": 180,
               "orientation": "", "pageCount": 0, "pages": None, "pageTags": None, "tags": None,
               "redirectionPageMap": None, "textScale": 1}
    pkg = out_dir / f"{Path(pdf).stem}.rmdoc"
    with zipfile.ZipFile(pkg, "w") as z:
        z.writestr(f"{doc}.content", json.dumps(content))
        z.write(pdf, f"{doc}.pdf")
    return pkg


def cloud_remove_all(name, limit=10):
    """Delete every top-level page called `name` (`rmapi rm` removes one per call)."""
    for _ in range(limit):
        if cloud_stat(name) is None:
            return
        code, out = rmapi("rm", name)
        if code != 0:
            raise RuntimeError(f"rmapi rm {name}: {out.strip()[-200:]}")
    raise RuntimeError(f"rmapi rm {name}: still there after {limit} deletes")


def cloud_replace(name, pdf):
    """Delete every copy of the page, then upload the new one to the top level.
    Returns (the cloud's modified time, the new document's id)."""
    cloud_remove_all(name)
    pkg = rmdoc_for(pdf, Path(pdf).parent / "rmdoc")
    with zipfile.ZipFile(pkg) as z:
        doc_id = Path(z.namelist()[0]).stem
    code, out = rmapi("put", str(pkg))
    if code != 0:
        raise RuntimeError(f"rmapi put {name}: {out.strip()[-200:]}")
    st = cloud_stat(name)
    return (st.get("ModifiedClient") if st else None), doc_id


def _ms_time(v):
    try:
        return datetime.fromtimestamp(int(v) / 1000, timezone.utc) if v else None
    except (TypeError, ValueError):
        return None


def cloud_copies(names):
    """Every top-level page with one of `names`, from rmapi's tree cache:
    {name: [{"id", "modified", "opened"}]}, newest change first. {} when the cache
    cannot be read, and the run falls back to `rmapi stat` alone."""
    try:
        docs = json.loads(RMAPI_CACHE.read_text()).get("Docs") or []
    except (OSError, ValueError, AttributeError):
        return {}
    out = {n: [] for n in names}
    for d in docs:
        m = d.get("Metadata") or {}
        n = m.get("visibleName")
        if n in out and not m.get("parent") and not m.get("deleted") and m.get("type") == "DocumentType":
            out[n].append({"id": d.get("DocumentID"), "modified": _ms_time(m.get("lastModified")),
                           "opened": _ms_time(m.get("lastOpened"))})
    for copies in out.values():
        copies.sort(key=lambda c: c["modified"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return out


def busy(copies, now_utc, own_id=None):
    """'writing' (a copy changed in the last SETTLE_MINUTES), 'opened' (a copy opened in
    the last OPEN_MINUTES) or None: a busy page is neither read nor redrawn this run.
    The copy this script uploaded last (`own_id`) is left to `page_changed`, which
    tells new writing from the upload itself."""
    def within(t, mins):
        return t is not None and (now_utc - t).total_seconds() < mins * 60
    if any(within(c.get("modified"), SETTLE_MINUTES) for c in copies if own_id is None or c.get("id") != own_id):
        return "writing"
    if any(within(c.get("opened"), OPEN_MINUTES) for c in copies):
        return "opened"
    return None


def cloud_download_id(doc_id, dest_dir):
    dest_dir.mkdir(parents=True, exist_ok=True)
    for old in dest_dir.glob("*"):
        old.unlink()
    code, out = rmapi("get", "--id", doc_id, cwd=dest_dir)
    zips = list(dest_dir.glob("*.zip")) + list(dest_dir.glob("*.rmdoc"))
    if code != 0 or not zips:
        raise RuntimeError(f"rmapi get --id {doc_id}: {out.strip()[-200:]}")
    return zips[0]


def pdf_page_images(pdf_bytes, out_dir):
    """Each page's picture from a PDF this script uploaded (Pillow writes one JPEG image
    per page, in page order), saved as PNGs in `out_dir`."""
    from PIL import Image
    import io
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = []
    for m in re.finditer(rb"/Subtype /Image.*?/Filter /DCTDecode.*?/Length (\d+)\s*>>\s*stream\r?\n",
                         pdf_bytes, re.S):
        jpeg = pdf_bytes[m.end():m.end() + int(m.group(1))]
        png = out_dir / f"p{len(out)}.png"
        Image.open(io.BytesIO(jpeg)).convert("RGB").save(png)
        out.append(png)
    return out


def drop_sent(plans, sent):
    """The plans minus inbox notes already sent from this copy of the page."""
    return [(cmd, summary) for cmd, summary in plans
            if not (cmd and cmd[0] == "trello-inbox" and cmd[1] in sent)]


def cloud_download(name, dest_dir):
    dest_dir.mkdir(parents=True, exist_ok=True)
    for old in dest_dir.glob("*"):
        old.unlink()
    code, out = rmapi("get", name, cwd=dest_dir)
    zips = list(dest_dir.glob("*.zip")) + list(dest_dir.glob("*.rmdoc"))
    if code != 0 or not zips:
        raise RuntimeError(f"rmapi get {name}: {out.strip()[-200:]}")
    return zips[0]


# ---------------------------------------------------------------- state
def load_state():
    try:
        return json.loads((STATE_DIR / "state.json").read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {"docs": {}, "last_read": None}


def save_state(state):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_DIR / "state.json.tmp"
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(STATE_DIR / "state.json")


def _parse_utc(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def page_changed(doc_state, stat, now_utc):
    """'no' (untouched), 'writing' (changed, not settled yet) or 'yes'."""
    if not stat or not doc_state or stat.get("ModifiedClient") == doc_state.get("modified"):
        return "no"
    mod = _parse_utc(stat.get("ModifiedClient"))
    if mod and (now_utc - mod).total_seconds() < SETTLE_MINUTES * 60:
        return "writing"
    return "yes"


# ---------------------------------------------------------------- reading marks
def build_prompt(image, page_name, marks):
    lines = []
    for i, m in enumerate(marks):
        x0, y0, x1, y1 = m["box"]
        lines.append(f"{i}. [{m['kind']}] {m['label']} (around x {x0}-{x1}, y {y0}-{y1})")
    spots = "\n".join(lines)
    return f"""Read the image file {image} with the Read tool. It is the page "{page_name}" from a
reMarkable tablet, 1620 x 2160 pixels: a printed form with handwriting and pen marks
drawn over it in colour. Report only marks you can actually see. A spot with no
mark on it is not in your answer. Never guess.

The spots that can be marked, numbered:
{spots}

How to read each kind:
- rating: which single number 1-5 in that row is circled, ticked or crossed. If two
  numbers are marked or it is unclear, give null for that row. The Hyperfocused row
  is "yes" or "no" (which word is circled), else null.
- task, habit, swap, pick, park, drop, review-skip: a checkbox. Ticked, crossed, filled or
  scribbled in = marked; put its spot number in "ticked". Each row may have two boxes
  (done at the left, swap at the right edge): report only the one marked.
- area: which letter G, Y or R at the right of that row is circled (green, yellow,
  red). A row highlighted or scribbled in a colour also counts: green = green,
  yellow/orange = yellow, red/pink = red. Writing in the page's "Note for the agent"
  box that explains an area change (it names the area, or only one area changed) is
  that area's "why", not a note; writing next to the row also counts.

- review-row: which option word in the rounded outlines on that row is circled
  (exact word as printed) into "review"."choices" under its spot number, and the
  writing on its "note:" line (or, for a row with no options, the writing that answers
  it) into "review"."notes". Nothing marked on the row = leave it out.
- review-prompt: the writing on those lines, word for word, into "review"."prompts".
- task-note: writing on or right beside that task's row that is not a tick in its
  boxes (a correction, "next week", "call first"...): word for word into
  "task_notes" under the row's spot number.
- note: the "Note for the agent" box: transcribe like the inbox below into "notes"
  (minus any text that is an area's "why"). On a page with a note box, free writing
  ANYWHERE else on the page that is not the answer to a numbered spot (in a margin,
  between cards, over blank space) is also a note: put it in "notes" too, not "other".
- inbox: free handwritten notes. Transcribe each note word for word, in order, into
  "notes". A new line, a gap, a bullet or a dash starts a new note; a note that
  wraps onto the next line without a gap is one note. Keep the writer's words and
  spelling of names; fix nothing, add nothing. Crossed-out writing is left out. A word you
  cannot make out becomes [?].

Anything else handwritten on the page goes in "other", word for word.

Answer with ONLY one JSON object, no prose, no code fence:
{{"ratings": {{"energy": null, "mood": null, "focus": null, "hyperfocused": null}},
  "ticked": [<spot numbers of marked task/habit checkboxes>],
  "areas": [{{"spot": <number>, "light": "green|yellow|red", "why": "<text or empty>"}}],
  "notes": ["<inbox or note-box note>", ...],
  "task_notes": {{"<spot>": "<text>"}},
  "review": {{"choices": {{"<spot>": "<option>"}}, "notes": {{"<spot>": "<text>"}},
              "prompts": {{"<spot>": "<text>"}}}},
  "other": "<other handwriting or empty>"}}"""


def claude_env():
    env = dict(os.environ)
    if not env.get("CLAUDE_CODE_OAUTH_TOKEN") and (REPO / ".env").exists():
        for line in (REPO / ".env").read_text().splitlines():
            if line.startswith("CLAUDE_CODE_OAUTH_TOKEN=") and line.split("=", 1)[1].strip():
                env["CLAUDE_CODE_OAUTH_TOKEN"] = line.split("=", 1)[1].strip().strip("\"'")
    return env


def ask_claude(prompt, cwd):
    p = subprocess.run([CLAUDE, "-p", prompt, "--allowedTools", "Read", "--output-format", "text"],
                       cwd=cwd, capture_output=True, text=True, timeout=600, env=claude_env(),
                       stdin=subprocess.DEVNULL)
    if p.returncode != 0:
        raise RuntimeError(f"claude exit {p.returncode}: {(p.stderr or p.stdout).strip()[-300:]}")
    return parse_reading(p.stdout)


def parse_reading(text):
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError(f"no JSON in Claude's answer: {text.strip()[:200]}")
    r = json.loads(m.group(0))
    return {"ratings": r.get("ratings") or {}, "ticked": r.get("ticked") or [],
            "areas": r.get("areas") or [],
            "notes": [str(n).strip() for n in r.get("notes") or [] if str(n).strip()],
            "review": r.get("review") or {},
            "task_notes": {str(k): str(v).strip() for k, v in (r.get("task_notes") or {}).items() if str(v).strip()},
            "other": (r.get("other") or "").strip()}


def plan_writes(reading, marks, page_name=None):
    """The `web_write.py` commands one reading asks for, and a plain summary of each.
    No handwriting is dropped: notes and anything else written go to the Trello inbox."""
    cmds = []
    rating_rows = {m["field"]: m for m in marks if m["kind"] == "rating"}
    vals = {}
    for field in ("energy", "mood", "focus"):
        v = reading["ratings"].get(field)
        if isinstance(v, int) and 1 <= v <= 5 and field in rating_rows:
            vals[field] = v
    if rating_rows and len(vals) == 3:
        day = next(iter(rating_rows.values()))["date"]
        name = datetime.strptime(day, "%Y-%m-%d").strftime("%A")
        cmd = ["rate-day", day, str(vals["energy"]), str(vals["mood"]), str(vals["focus"])]
        summary = f"rated {name} {vals['energy']}/{vals['mood']}/{vals['focus']}"
        hyper = str(reading["ratings"].get("hyperfocused") or "").lower()
        if "hyperfocused" in rating_rows and hyper in ("yes", "no"):
            cmd.append(f"hyper:{hyper}")
            summary += f", hyperfocused {hyper}"
        cmds.append((cmd, summary))
    elif vals:
        cmds.append((None, f"rating not saved: only {', '.join(vals)} circled"))
    for i in reading["ticked"]:
        if not isinstance(i, int) or not 0 <= i < len(marks):
            continue
        m = marks[i]
        title = m["label"].split(": ", 1)[-1]
        if m["kind"] == "task":
            cmds.append((["complete-task", m["id"]], f"done: {title}"))
        elif m["kind"] == "habit":
            cmds.append((["log-habit", m["id"], m["date"]], f"habit: {title}"))
        elif m["kind"] == "swap":
            cmds.append((["drop-pick", m["date"], m["id"]], f"swapped out: {title}"))
        elif m["kind"] == "park":
            cmds.append((["park-focus", m["id"], "on"], f"parked focus: {title}"))
        elif m["kind"] == "drop":
            cmds.append((["drop-task", m["id"]], f"dropped: {title}"))
    cmds += _plan_picks(reading, marks)
    for a in reading["areas"]:
        i = a.get("spot")
        light = (a.get("light") or "").lower()
        if not isinstance(i, int) or not 0 <= i < len(marks) or marks[i]["kind"] != "area":
            continue
        if light not in ("green", "yellow", "red"):
            continue
        cmd = ["set-area", marks[i]["id"], light]
        why = (a.get("why") or "").strip()
        if why:
            cmd.append(f"note:{why}")
        area = marks[i]["label"].split(" row", 1)[0]
        cmds.append((cmd, f"{area} → {light}" + (f" ({why})" if why else "")))
    for k, text in (reading.get("task_notes") or {}).items():
        i = int(k) if str(k).isdigit() else -1
        if 0 <= i < len(marks) and marks[i]["kind"] == "task-note":
            note = f"Note on task \"{marks[i]['title']}\" ({marks[i]['id']}): {text}"
            cmds.append((["trello-inbox", note], f"inbox: {note[:40]}"))
    page = next((m["page"] for m in marks if m["kind"] == "note"), None) or (
        None if any(m["kind"] == "inbox" for m in marks) else page_name)
    for note in reading.get("notes") or []:
        text = f"From the {page} page: {note}" if page else note
        cmds.append((["trello-inbox", text], f"inbox: {text[:40]}"))
    if reading.get("other"):
        text = f"Also written on the {page or page_name or 'inbox'} page: {reading['other']}"
        cmds.append((["trello-inbox", text], f"inbox: {text[:40]}"))
    cmds += _plan_review(reading, marks)
    return cmds


def _plan_picks(reading, marks):
    """Ticked suggestions become picks: the day's picks (minus any swapped out this
    read) plus each ticked one, critical first up to two, then the bonus."""
    ticked = {i for i in reading["ticked"] if isinstance(i, int) and 0 <= i < len(marks)}
    swapped = {marks[i]["id"] for i in ticked if marks[i]["kind"] == "swap"}
    by_day = {}
    for i in sorted(ticked):
        m = marks[i]
        if m["kind"] != "pick":
            continue
        day = by_day.setdefault(m["date"], {"critical": [t for t in m["critical"] if t not in swapped],
                                            "bonus": m["bonus"] if m["bonus"] not in swapped else None,
                                            "titles": []})
        if m["id"] in day["critical"] or m["id"] == day["bonus"]:
            continue
        if len(day["critical"]) < 2:
            day["critical"].append(m["id"])
        elif not day["bonus"]:
            day["bonus"] = m["id"]
        else:
            continue
        day["titles"].append(m["label"].split(": ", 1)[-1])
    cmds = []
    for day, d in by_day.items():
        if not d["titles"]:
            continue
        cmd = ["set-picks", day, *d["critical"]] + ([f"bonus:{d['bonus']}"] if d["bonus"] else [])
        cmds.append((cmd, "picked: " + ", ".join(d["titles"])))
    return cmds


def _plan_review(reading, marks):
    """The review page: its answers go to /pfc-review as one form; a ticked skip box
    with no answers stamps it."""
    rows = {i: m for i, m in enumerate(marks) if m["kind"] in ("review-row", "review-prompt")}
    if not rows and not any(m["kind"] == "review-skip" for m in marks):
        return []
    rv = reading.get("review") or {}
    answers = {"choices": {}, "notes": {}, "prompts": {}}
    for part in ("choices", "notes", "prompts"):
        for k, v in (rv.get(part) or {}).items():
            i = int(k) if str(k).isdigit() else -1
            v = str(v or "").strip()
            if i not in rows or not v:
                continue
            m = rows[i]
            if part == "choices" and v not in (m.get("options") or []):
                continue  # a word the row does not offer: a misread, never guessed
            answers[part][m["id"]] = v
    review_id = next((m["review"] for m in rows.values()), None) or next(
        (m["id"] for m in marks if m["kind"] == "review-skip"), None)
    if any(answers.values()):
        shown = [m["id"] for m in rows.values() if m["kind"] == "review-row"]
        answers = {"review": review_id, **{k: v for k, v in answers.items() if v}}
        if shown:
            answers["shown"] = shown
        n = sum(len(v) for k, v in answers.items() if k not in ("review", "shown"))
        return [(["review", review_id, json.dumps(answers, ensure_ascii=False)], f"review {review_id}: {n} answers")]
    skip = [i for i in reading["ticked"] if isinstance(i, int) and 0 <= i < len(marks)
            and marks[i]["kind"] == "review-skip"]
    if skip:
        return [(["stamp-review", marks[skip[0]]["id"]], f"review {marks[skip[0]]['id']}: skipped this cycle")]
    return []


def send_to_trello_inbox(text, stamp):
    """One inbox note as a card in Trello's 📥 Inbox list (`trello_helper.create_card`)."""
    import trello_helper
    env = trello_helper._resolve_env()
    if not trello_helper._need_env(env):
        raise RuntimeError("Trello credentials missing")
    name = text if len(text) <= 250 else text[:247] + "..."
    desc = f"From the reMarkable, read {stamp}.\n\n{text}"
    f = remarkable_replies.FROM.match(text)
    said = remarkable_replies.recent(remarkable_replies.page_of(f.group(1)) or "", limit=6) if f else []
    if said:  # the note may answer one of these: the agent reading it needs them
        desc += "\n\nThe agent's recent replies on that page (the note may answer one):\n" + "\n".join(
            f"- {remarkable_replies.stamp(r)}: {r['text']}" for r in said)
    trello_helper.create_card(env["TRELLO_API_KEY"], env["TRELLO_API_TOKEN"], env["TRELLO_INBOX_LIST_ID"],
                              name, desc=desc)


def run_review(review_id, answers_json):
    """Apply a filled review form: /pfc-review Mode B, headless, carrying out every answer."""
    prompt = f"/pfc-review {review_id} answers {answers_json} unattended"
    p = subprocess.run([CLAUDE, "-p", prompt, "--permission-mode", "auto"], cwd=REPO, capture_output=True,
                       text=True, timeout=1200, env=claude_env(), stdin=subprocess.DEVNULL)
    tail = (p.stdout or p.stderr or "").strip()[-300:]
    log(f"   review apply exit {p.returncode}: {tail}")
    if p.returncode != 0:
        remarkable_replies.add("4 - Review", f"Could not save the {review_id} answers (Claude exit {p.returncode}); "
                               "fill the form again")
        return p.returncode
    remarkable_replies.add("4 - Review", f"Saved your {review_id} answers")
    for _, q, default in remarkable_replies.questions(p.stdout):
        remarkable_replies.add("4 - Review", f"Asked: {q} I went with: {default}. To change it, write here.")
    return p.returncode


def run_write(cmd, dry_run):
    if cmd[0] == "review":
        if dry_run:
            return 0, {"changed": False}, ""
        code = run_review(cmd[1], cmd[2])
        return (0, {"changed": True}, "") if code == 0 else (1, {"reason": f"claude exit {code}"}, "")
    if cmd[0] == "trello-inbox":
        if dry_run:
            return 0, {"changed": False}, ""
        try:
            send_to_trello_inbox(cmd[1], datetime.now(TZ).strftime("%a %b %d %I:%M %p"))
            return 0, {"changed": True}, ""
        except Exception as e:  # noqa: BLE001
            return 1, {"reason": str(e)[:200]}, ""
    argv = [PYTHON, str(SCRIPT_DIR / "web_write.py")] + (["--dry-run"] if dry_run else []) + ["--no-render", *cmd]
    p = subprocess.run(argv, cwd=REPO, capture_output=True, text=True, timeout=180)
    try:
        out = json.loads(p.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        out = {}
    return p.returncode, out, (p.stderr or "").strip()


def state_bases(name, n):
    """The pictures of the page as last uploaded, one per page."""
    out = []
    for k in range(n):
        base = STATE_DIR / f"{name}-p{k}.png"
        out.append(base if base.exists() else STATE_DIR / f"{name}.png")  # drawn before multi-page documents
    return out


def read_page(name, doc, dry_run, sent=None):
    """Download, overlay, ask Claude, save. Returns a list of summary strings."""
    work = STATE_DIR / "read"
    archive = cloud_download(name, work / "download")
    page_marks = page_marks_of(doc)
    return read_archive(name, archive, page_marks, state_bases(name, len(page_marks)), work, dry_run, sent)


def read_copies(name, copies, state, dry_run):
    """Two or more pages called `name`: the tablet kept a page it had open when it was
    redrawn. Read each copy against its own picture and spots, then the caller
    replaces them all with one page. Returns a list of summary strings."""
    doc = state["docs"].get(name) or {}
    uploads = state.setdefault("uploads", {})
    log(f"🟡 {name}: {len(copies)} copies on the tablet; reading each, then keeping one")
    done = []
    for c in copies:
        work = STATE_DIR / "read" / c["id"]
        archive = cloud_download_id(c["id"], work / "download")
        rec = uploads.setdefault(c["id"], {"name": name, "uploaded": datetime.now(TZ).isoformat(timespec="seconds")})
        page_marks = rec.get("page_marks") or page_marks_of(doc)
        with zipfile.ZipFile(archive) as z:
            pdf = next((n for n in z.namelist() if n.endswith(".pdf")), None)
            bases = pdf_page_images(z.read(pdf), work / "bases") if pdf else []
        fallback = state_bases(name, len(page_marks))
        bases = [bases[k] if k < len(bases) else fallback[k] for k in range(len(page_marks))]
        done += read_archive(name, archive, page_marks, bases, work, dry_run, rec.setdefault("sent", []))
    if not dry_run:
        remarkable_replies.add(name, f"Found {len(copies)} copies of this page (it was redrawn while open); "
                                     "read what was written on each and kept one")
    return done


def read_archive(name, archive, page_marks, bases, work, dry_run, sent=None):
    """Overlay the ink on each page's picture, ask Claude, save. `sent` holds the inbox
    notes already sent from this copy; new ones are added to it."""
    sent = [] if sent is None else sent
    order = remarkable_lines.page_order(archive)
    pages = remarkable_lines.strokes_from_zip(archive)
    if not order:
        order = list(pages)
    plans = []
    for k, pid in enumerate(order[:len(page_marks)]):
        strokes = pages.get(pid) or []
        if not strokes or not page_marks[k]:
            continue
        base = bases[k]
        image = work / f"{name}-p{k}.png"
        remarkable_lines.overlay(base, strokes, image)
        label = name if len(page_marks) == 1 else f"{name}, page {k + 1}"
        log(f"   {label}: {len(strokes)} strokes, asking Claude")
        reading = ask_claude(build_prompt(image, label, page_marks[k]), cwd=work)
        log(f"   reading: {json.dumps(reading)}")
        plans += plan_writes(reading, page_marks[k], label)
    plans = drop_sent(plans, sent)
    if not plans:
        log(f"🟢 {name}: opened, no ink")
        return []
    done = []
    for cmd, summary in plans:
        if cmd is None:
            done.append(summary)
            continue
        code, out, err = run_write(cmd, dry_run)
        if code == 0 and cmd[0] == "trello-inbox" and not dry_run:
            sent.append(cmd[1])
        if code == 0:
            done.append(summary if out.get("changed", True) else summary + " (already saved)")
            log(f"🟢 {summary}")
        else:
            reason = out.get("reason") or out.get("error") or err[-200:]
            done.append(f"{summary}: not saved ({reason})")
            log(f"🟡 {summary}: web_write exit {code} {reason}")
    if not dry_run:
        saved = [d for d in done if not d.startswith(("inbox: ", "review "))]
        sent = sum(1 for d in done if d.startswith("inbox: ") and "not saved" not in d)
        unsent = sum(1 for d in done if d.startswith("inbox: ") and "not saved" in d)
        if saved:
            remarkable_replies.add(name, "Saved: " + "; ".join(saved))
        if sent:
            remarkable_replies.add(name, f"Sent {sent} note{'s' if sent > 1 else ''} to the Trello inbox")
        if unsent:  # the page is redrawn either way, so say so: the ink is gone
            remarkable_replies.add(name, f"Could not send {unsent} note{'s' if unsent > 1 else ''} to the Trello "
                                         "inbox (is Trello set up?); please write it again")
    return done


def prune_uploads(state):
    cutoff = datetime.now(TZ).timestamp() - UPLOAD_KEEP_DAYS * 86400
    ups = state.get("uploads") or {}
    for doc_id in [i for i, u in ups.items()
                   if not u.get("uploaded") or datetime.fromisoformat(u["uploaded"]).timestamp() < cutoff]:
        del ups[doc_id]


def page_marks_of(doc):
    """The writable spots per page of a document (older state kept one page's `marks`)."""
    return doc.get("page_marks") or [doc.get("marks") or []]


# ---------------------------------------------------------------- one run
def run(dry_run=False, force_upload=False):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state = load_state()
    now_utc = datetime.now(timezone.utc)
    if not Path(RMAPI).exists():
        log(f"🔴 rmapi not found at {RMAPI}; see docs/remarkable.md")
        return 1
    if rmapi("ls")[0] != 0:
        log("🔴 the reMarkable cloud did not answer (rmapi ls failed); sign-in may have expired")
        return 1

    legacy = [n for n in state["docs"] if n not in remarkable_pages.PAGE_NAMES]
    names = remarkable_pages.PAGE_NAMES + legacy
    stats = {name: cloud_stat(name) for name in names}
    copies = cloud_copies(names)
    writing, read_now, summaries = set(), set(), []
    for name in names:
        doc = state["docs"].get(name)
        why = busy(copies.get(name) or [], now_utc, (doc or {}).get("id"))
        if why:
            writing.add(name)
            log(f"🟡 {name}: {'changed' if why == 'writing' else 'opened'} in the last "
                f"{SETTLE_MINUTES if why == 'writing' else OPEN_MINUTES} min, left until you are done")
            continue
        if len(copies.get(name) or []) > 1:
            try:
                summaries += read_copies(name, copies[name], state, dry_run)
                read_now.add(name)
            except Exception as e:  # noqa: BLE001 — keep every copy until it can be read
                writing.add(name)
                log(f"🟡 {name}: could not read the copies ({e}); left for the next run")
            save_state(state)
            continue
        changed = page_changed(doc, stats[name], now_utc)
        if changed == "writing":
            writing.add(name)
            log(f"🟡 {name}: changed in the last {SETTLE_MINUTES} min, left until you are done")
        elif changed == "yes":
            if not any(page_marks_of(doc)):
                log(f"🟢 {name}: written on, but nothing on this page is read; redrawing it")
                read_now.add(name)
                continue
            try:
                rec = state.setdefault("uploads", {}).get(doc.get("id")) if doc.get("id") else None
                got = read_page(name, doc, dry_run, rec.setdefault("sent", []) if rec is not None else None)
                doc.pop("tries", None)
                if got:
                    summaries += got
                    read_now.add(name)
                elif not dry_run:  # only opened: no redraw, or the tablet keeps its open copy as a duplicate
                    doc["modified"] = stats[name].get("ModifiedClient")
            except Exception as e:  # noqa: BLE001 — one failed read must not stop the run
                doc["tries"] = doc.get("tries", 0) + 1
                log(f"🟡 {name}: could not read the marks ({e}); try {doc['tries']} of {MAX_READ_TRIES}")
                if doc["tries"] >= MAX_READ_TRIES:
                    summaries.append(f"could not read {name}; marks cleared, please redo")
                    if not dry_run:
                        remarkable_replies.add(name, "Could not read what you wrote here after three tries; "
                                                     "the page was redrawn, please write it again")
                    read_now.add(name)
                    doc.pop("tries", None)
                else:
                    writing.add(name)  # keep the ink on the tablet for the next try
            save_state(state)

    read = [s for s in summaries if not s.startswith("inbox: ")]
    stamp = datetime.now(TZ).strftime("%a %I:%M %p").replace(" 0", " ")
    if read:
        state["last_read"] = f"{stamp}: " + "; ".join(read)
    if summaries:
        if not dry_run:
            subprocess.run([PYTHON, str(SCRIPT_DIR / "trello_render.py")], cwd=REPO, timeout=600,
                           capture_output=True)

    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip()
    stamp_now = f"{head}|{datetime.now(TZ).strftime('%Y-%m-%d %H')}"
    unchanged = (not read_now and not force_upload and stamp_now == state.get("drawn")
                 and all(stats.get(n) is not None and n in state["docs"] for n in remarkable_pages.PAGE_NAMES))
    if unchanged:
        save_state(state)
        return 0
    home = remarkable_pages.load_home()
    for name in legacy:
        if name in writing or dry_run:
            continue
        try:
            cloud_remove_all(name)
        except (RuntimeError, subprocess.TimeoutExpired) as e:
            log(f"🟡 {name}: old page not deleted ({str(e)[-120:]})")
            continue
        state["docs"].pop(name, None)
        for f in STATE_DIR.glob(f"{name}*.p*"):
            f.unlink(missing_ok=True)
        log(f"🟢 {name}: old page deleted from the tablet")
    save_state(state)

    for page in remarkable_pages.build_pages(home):
        name = page.name
        if name in writing:
            continue
        pdf, pngs = remarkable_pages.save(page, STATE_DIR / "next")
        digest = hashlib.sha256(b"".join(p.read_bytes() for p in pngs)).hexdigest()
        doc = state["docs"].get(name) or {}
        missing = stats.get(name) is None
        if not (force_upload or missing or name in read_now or digest != doc.get("hash")):
            continue
        if dry_run:
            log(f"🟢 {name}: would upload (dry run)")
            continue
        try:
            modified, doc_id = cloud_replace(name, pdf)
        except (RuntimeError, subprocess.TimeoutExpired) as e:
            log(f"🟡 {name}: upload failed ({e})")
            continue
        for old in STATE_DIR.glob(f"{name}*.png"):
            old.unlink()
        for png in pngs:
            shutil.copy(png, STATE_DIR / png.name)
        shutil.copy(pdf, STATE_DIR / f"{name}.pdf")
        uploaded = datetime.now(TZ).isoformat(timespec="seconds")
        page_marks = [p.marks for p in page.pages]
        state["docs"][name] = {"id": doc_id, "modified": modified, "hash": digest,
                               "page_marks": page_marks, "uploaded": uploaded}
        # Kept per document so a stray copy the tablet holds on to is read against its own spots.
        state.setdefault("uploads", {})[doc_id] = {"name": name, "page_marks": page_marks, "uploaded": uploaded}
        prune_uploads(state)
        save_state(state)
        log(f"🟢 {name}: uploaded")
    if not dry_run:
        state["drawn"] = stamp_now
    save_state(state)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="read marks and plan writes, change nothing")
    ap.add_argument("--force-upload", action="store_true", help="replace every page now")
    args = ap.parse_args(argv)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(STATE_DIR / "lock", "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log("🟡 another run is still going; skipped")
            return 0
        log("START reMarkable sync")
        code = run(args.dry_run, args.force_upload)
        log(f"DONE exit {code}")
        return code


if __name__ == "__main__":
    sys.exit(main())
