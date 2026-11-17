#!/usr/bin/env python3
"""The one due rolling review, as a fill-in form every surface can show.

    python3 automations/scripts/review_forms.py [--today YYYY-MM-DD] [--id REVIEW_ID]

Reviews run one at a time, everywhere: the web Review page (`/review`), the
optional reMarkable `4 - Review` page (`remarkable_pages.py`) and `/pfc-review` in a
Claude Code session show the same review, picked by `current_review` (never done
first, then most overdue, the order `home_data._due_review` uses), as the same
form. Answers from any of them go to
`/pfc-review <id> answers <json>`, which applies them with the owning procedure and
stamps the review; the next due review then takes its place.

A due review whose form has nothing to ask (no project is missing values, no task is
missing an area) is skipped and stays due: this is the gate that decides whether a
review surfaces at all.

A form is a list of sections:

- `choices`: rows (a task, a habit, a focus...) each with the same options to pick
  one of, and an optional one-line note per row;
- `prompt`: a question with room to write, for the reviews that need thinking.

Answers, whatever surface they came from:

    {"review": "<id>", "choices": {"<row id>": "<option>"},
     "notes": {"<row id>": "<text>"}, "prompts": {"<prompt id>": "<text>"}}

A row or prompt left blank is not an answer; the procedure leaves that item alone.
Answers also carry `"shown": [<row ids the form showed>]`.

Rows are capped (`MAX_ROWS`) so a form stays short enough to answer in one sitting
(and a long row that would run off the tablet page waits for the next form). A review with more rows
than that is done over several sittings: `--finish <id> --shown <ids>` records the
rows answered (`seen` on its ledger row) and leaves it due, so the next form starts
after them; once no rows are left it is stamped and `seen` is cleared.
"""

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
REPO = SCRIPT_DIR.parents[1]

MAX_ROWS = 14
# Rows answered earlier this round (the ledger row's `seen`), left out of the form so a
# review too long for one form carries on where it stopped.
_SEEN = set()


def _ndjson(rel):
    p = REPO / rel
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def due_reviews(today):
    """Every due review, never done first, then most overdue: [(overdue or None, row)]."""
    due = []
    for r in _ndjson("data/review-ledger.ndjson"):
        if not r.get("last_done"):
            due.append((None, r))
            continue
        overdue = (date.fromisoformat(today) - date.fromisoformat(r["last_done"])).days - r["cadence_days"]
        if overdue >= 0:
            due.append((overdue, r))
    due.sort(key=lambda x: (x[0] is not None, -(x[0] or 0)))
    return due


def _choices(title, options, rows, note=False, hint=None):
    rows = [r for r in rows if r and r["id"] not in _SEEN]
    more = max(0, len(rows) - MAX_ROWS)
    return {"kind": "choices", "title": title, "options": options, "rows": rows[:MAX_ROWS], "note": note,
            "hint": hint, "more": more}


def _prompt(pid, question, lines=4):
    return {"kind": "prompt", "id": pid, "question": question, "lines": lines}


def _row(rid, title, detail=""):
    return {"id": rid, "title": str(title), "detail": str(detail or "")}


def _habit_rate(habit_id, logs, days, today):
    start = date.fromisoformat(today) - timedelta(days=days)
    done = {r["date"] for r in logs if r.get("habit_id") == habit_id and r.get("completed")
            and start.isoformat() < r.get("date", "") <= today}
    return len(done)


def _monthly_done(habit_id, logs, today):
    month = today[:7]
    return sum(1 for r in logs if r.get("habit_id") == habit_id and r.get("completed")
               and str(r.get("date", "")).startswith(month))


# ---------------------------------------------------------------- one builder per review
def build_form(review_id, h, today):
    """The sections for one review, from the home page dict `h` plus a few files."""
    tasks = {t["id"]: t for t in _ndjson("6-tasks/_data/tasks.ndjson")}
    projects = {p["id"]: p for p in _ndjson("5-projects/_data/projects.ndjson")}
    focus_rows = [f for rows in (h.get("focuses") or {}).values() for f in rows]

    if review_id == "stale-task-triage":
        import revive_watchlist
        try:
            items = revive_watchlist.build(REPO, today) if hasattr(revive_watchlist, "build") else None
        except Exception:  # noqa: BLE001
            items = None
        if items is None:
            import subprocess
            out = subprocess.run([sys.executable, str(SCRIPT_DIR / "revive_watchlist.py"), "--today", today],
                                 capture_output=True, text=True, cwd=REPO).stdout
            items = json.loads(out or "[]")
        rows = []
        for it in items:
            rec = tasks.get(it["item_id"]) or projects.get(it["item_id"]) or {}
            name = rec.get("description") or rec.get("title") or rec.get("name") or it["item_id"]
            rows.append(_row(it["item_id"], f"{it['item_type'].title()}: {name}", it.get("detail")))
        return [_choices("Slipped tasks and projects", ["Keep", "This week", "Park", "Drop"], rows, note=True,
                         hint="Keep: leave as is. This week: schedule it now. Park: pause it. Drop: remove it.")]

    if review_id == "tasks-missing-area":
        areas = [r["key"] for r in (h.get("areas") or {}).get("rows") or []]
        rows = [_row(t["id"], t.get("description") or t["id"]) for t in tasks.values()
                if t.get("status") == "open" and not t.get("area") and (t.get("project") or "none") == "none"]
        return [_choices("Open tasks with no area: write the area on the line", [], rows, note=True,
                         hint="Areas: " + ", ".join(areas))]

    if review_id in ("focus-accuracy", "focus-repick"):
        rows = [_row(f["focus_id"], f["title"],
                     f"{f.get('light')}, " + (f"{f['primary']['completed']} of {f['primary']['target']} this window"
                                              if f.get("primary") else "no habit")
                     + (f", red {f['weeks_red']} weeks" if f.get("weeks_red") else ""))
                for f in focus_rows]
        opts = (["Keep", "Re-land", "Lower", "Park", "Retire"] if review_id == "focus-accuracy"
                else ["Keep", "Park", "Retire", "Graduate"])
        hint = ("Re-land: a new first step. Lower: a smaller target. Park: pause. Retire: done with it. "
                "Write the new landing or target on the line." if review_id == "focus-accuracy"
                else "Park: pause. Retire: done with it. Graduate: it became a foundation.")
        sections = [_choices("Your focuses", opts, rows, note=True, hint=hint)]
        if review_id == "focus-repick":
            sections.append(_prompt("new-focuses", "What new focus do you want this quarter, if any? "
                                    "Name it and its area.", 4))
        return sections

    if review_id in ("habit-rate", "monthly-habits"):
        cadence = "daily" if review_id == "habit-rate" else "monthly"
        logs = _ndjson("7-habits/_data/habits-daily.ndjson" if cadence == "daily"
                       else "7-habits/_data/habits-monthly.ndjson")
        rows = []
        for hb in h.get("habits") or []:
            if hb.get("cadence") != cadence:
                continue
            n = _habit_rate(hb["id"], logs, 7, today) if cadence == "daily" else _monthly_done(hb["id"], logs, today)
            rows.append(_row(hb["id"], hb["title"], f"{n} of the last 7 days" if cadence == "daily" else f"{n} this month"))
        return [_choices(f"{cadence.title()} habits", ["Keep", "Reword", "Easier", "Drop"], rows, note=True,
                         hint="Reword or Easier: write the new wording or target on the line.")]

    if review_id == "values-alignment":
        values = h.get("values") or []
        rows = [_row(p["id"], p["name"]) for p in projects.values() if p.get("active") and not p.get("values")]
        return [_choices("Active projects with no values: write the values on the line", [], rows, note=True,
                         hint="Values: " + ", ".join(values))]

    if review_id == "project-progress":
        rows = [_row(p["id"], p["name"], f"{p.get('pct', 0)}% done"
                     + (f", idle {p['days_idle']} days" if p.get("stalled") else "")
                     + (f". Next: {p['next_task']['title']}" if p.get("next_task") else ""))
                for p in (h.get("projects") or {}).get("active") or []]
        return [_choices("Active projects", ["On track", "Stuck", "Park", "Done"], rows, note=True,
                         hint="Write a one-line update on the line: what moved, or what is in the way.")]

    if review_id == "life-wheel":
        items = {i["id"]: i for i in _ndjson("2-areas/_data/area-items.ndjson")}
        rows = []
        for area in (h.get("areas") or {}).get("rows") or []:
            for it in area.get("items") or []:
                q = (items.get(it["id"]) or {}).get("question")
                if it.get("source") or it.get("ended") or not q:
                    continue
                rows.append(_row(it["id"], f"{area['label']}: {q}", it.get("why")))
        if rows or items:
            return [_choices("Your life areas, worst first", ["Good", "Okay", "Rough"], rows, note=True)]
        # No area items yet: rate each area by hand, the manual life-wheel light. With no
        # snapshot at all the areas are the 2-areas/ folders, so a fresh repo can start.
        manual = [_row(r["key"], r["label"], r.get("light") or "") for r in (h.get("areas") or {}).get("rows") or []]
        if not manual:
            manual = [_row(d.name, d.name.replace("-", " ").title())
                      for d in sorted((REPO / "2-areas").glob("*/")) if not d.name.startswith(("_", "."))]
        return [_choices("Your life areas: rate each one", ["Green", "Yellow", "Red"], manual, note=True,
                         hint="Write what is behind a yellow or red on the line.")]

    if review_id in ("vision-activation", "vision-relevance"):
        visions = h.get("visions") or []
        if review_id == "vision-relevance":
            # Every vision in one sitting, so the review moves through the whole set.
            return [_choices("Your visions", ["Still fits", "Reword", "Retire"],
                             [_row(v["id"], v["title"]) for v in visions], note=True,
                             hint="Reword: write the new wording on the line.")]
        rows = [_row(v["id"], v["title"]) for v in visions]
        return [_choices("Visions", ["Lean in", "Let rest"], rows, note=False,
                         hint="Lean in: give it a focus or project now. Let rest: it waits, which is fine.")]

    if review_id == "insights-review":
        # Full text, never cut: a clipped insight can't be judged. Rows past MAX_ROWS
        # aren't marked shown, so they carry to the next form.
        rows = [_row(i["id"], i.get("insight", "")) for i in _ndjson("data/insights.ndjson")
                if i.get("status") == "active"]
        return [_choices("Active insights", ["Keep", "Archive", "Make a task"], rows, note=True)]

    if review_id == "hypotheses-review":
        rows = [_row(x["id"], x.get("hypothesis", ""), f"last looked at {x.get('last_reviewed') or 'never'}")
                for x in _ndjson("data/hypotheses.ndjson") if x.get("status") == "active"]
        rows.sort(key=lambda r: r["detail"])
        return [_choices("Active hypotheses, oldest look first", ["Still testing", "It holds", "Doesn't hold"],
                         rows, note=True, hint="It holds: graduate it to a finding. Nothing is archived without you.")]

    if review_id == "household-status":
        rows = [_row(r["key"], r["label"], f"{r['light']}" + (f": {r['note']}" if r.get("note") else ""))
                for r in (h.get("household") or {}).get("rows") or []]
        if not rows:
            return [_prompt("rooms", "No house areas rated yet. Name each one (kitchen, garage, yard...) with its "
                            "light, green, yellow or red, and what is behind a yellow or red.", 6)]
        return [_choices("House areas, worst first", ["Green", "Yellow", "Red"], rows, note=True,
                         hint="Write what is behind a yellow or red on the line; a red gets a task.")]

    if review_id == "findings-alignment":
        rows = [_row(x["id"], x.get("finding", ""), x.get("domain") or "")
                for x in _ndjson("data/findings.ndjson") if x.get("status") == "active"]
        return [_choices("Active findings", ["Still holds", "Superseded"], rows, note=True,
                         hint="Superseded: write what replaced it on the line.")]

    if review_id == "day-trend-peek":
        days = [d for d in _ndjson("data/day-tracking.ndjson") if d.get("rating") is not None][-7:]
        lines = ", ".join(f"{date.fromisoformat(d['date']).strftime('%a')} {d['rating']}" for d in days)
        return [_prompt("stands-out", f"Last rated days: {lines or 'none'}. What stands out, and what helped "
                        "the good ones?", 4)]

    if review_id == "trend-analysis":
        trends = "; ".join(f"{t['name']} {t['why']}" for t in h.get("trends") or [])
        return [_prompt("pattern", f"Last 30 days: {trends}. What pattern do you see?", 4),
                _prompt("try", "What one thing will you try for the next month?", 3)]

    if review_id == "revive-outcomes":
        return [_prompt("revived", "Things you revived a month or more ago: which stuck, which slipped again, "
                        "and why?", 6)]

    if review_id == "usage-audit":
        return [_prompt("not-using", "Which part of the system are you not using, or using but getting nothing "
                        "from?", 4),
                _prompt("change", "What should change: use it, change how often, or change or cut it?", 4)]

    if review_id == "vision-brainstorm":
        return [_prompt("wants", "Everything you want out of life right now. No filter, no order. One per line.", 14)]

    if review_id == "strengths-refresh":
        return [_prompt("worked", "Where did your strengths carry you this quarter?", 5),
                _prompt("drained", "What drained you more than it should have?", 5)]

    return [_prompt("notes", "What do you want to change here?", 6)]


def current_review(h, today, review_id=None, repo=None):
    """The one review to show now, with its form; None when nothing is due or asks
    anything. `review_id` picks a review by id, due or not (a surface asking again).
    `repo` reads another checkout (home_data passes its own, so tests can point it)."""
    global REPO
    if repo is not None and Path(repo) != REPO:
        saved, REPO = REPO, Path(repo)
        try:
            return current_review(h, today, review_id)
        finally:
            REPO = saved
    due = due_reviews(today)
    if review_id:
        row = next((r for r in _ndjson("data/review-ledger.ndjson") if r["id"] == review_id), None)
        if not row:
            return None
        overdue = next((o for o, r in due if r["id"] == review_id), None)
        sections = _build_with_seen(row, h, today)
    else:
        # The first due review with something to ask. One with nothing (no project is
        # missing values) stays due without surfacing, as /pfc-review's gates do.
        for overdue, row in due:
            sections = _build_with_seen(row, h, today)
            if any(s["kind"] == "prompt" or s["rows"] for s in sections):
                break
        else:
            return None
    more = sum(s.get("more", 0) for s in sections)
    intro = {"weekly": "A weekly review.", "monthly": "A monthly review.",
             "quarterly": "A quarterly review."}.get(row.get("tier"), "")
    if row.get("seen"):
        intro += f" Carrying on: {len(row['seen'])} rows done earlier this round."
    if more:
        intro += f" {more} more rows after these; the review stays due until they are done."
    return {"id": row["id"], "label": row["label"], "tier": row.get("tier"), "overdue_days": overdue,
            "due_count": len(due), "intro": intro.strip(), "sections": sections}


def _build_with_seen(row, h, today, extra=()):
    global _SEEN
    saved, _SEEN = _SEEN, set(row.get("seen") or []) | set(extra)
    try:
        return build_form(row["id"], h, today)
    finally:
        _SEEN = saved


def finish(review_id, shown, h, today):
    """After a form's answers are applied: stamp the review when no rows are left this
    round, else record the rows shown (`review-seen`) so it stays due and the next form
    starts after them. Returns the web_write command run."""
    import subprocess
    row = next((r for r in _ndjson("data/review-ledger.ndjson") if r["id"] == review_id), None)
    if row is None:
        raise SystemExit(f"no review {review_id}")
    left = sum(len(s["rows"]) + s.get("more", 0) for s in _build_with_seen(row, h, today, shown)
               if s["kind"] == "choices")
    cmd = ["review-seen", review_id, *shown] if (left and shown) else ["stamp-review", review_id]
    subprocess.run([sys.executable, str(SCRIPT_DIR / "web_write.py"), *cmd], cwd=REPO, check=False)
    return cmd


def load_home(today=None):
    """`home_data.build_home` the way `web_data.py --home` calls it."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    import home_data
    from trmnl_push import load_env
    env = load_env()
    now = datetime.now(ZoneInfo(env.get("LOCAL_TZ", "America/Denver"))).replace(tzinfo=None)
    if today:
        now = datetime.combine(date.fromisoformat(today), now.time())
    return home_data.build_home(env, now)


def answers_prompt(review, answers):
    """The command that applies a filled form, the same from every surface."""
    return f"/pfc-review {review['id']} answers {json.dumps(answers, ensure_ascii=False)}"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--today")
    ap.add_argument("--id")
    ap.add_argument("--finish", metavar="REVIEW_ID",
                    help="after applying answers: stamp it, or keep it due when rows are left")
    ap.add_argument("--shown", default="", help="with --finish: comma-separated row ids the form showed")
    args = ap.parse_args(argv)
    h = load_home(args.today)
    if args.finish:
        print(json.dumps(finish(args.finish, [s for s in args.shown.split(",") if s], h, h["date"])))
        return
    json.dump(current_review(h, h["date"], args.id), sys.stdout, ensure_ascii=False, indent=1)
    print()


if __name__ == "__main__":
    main()
