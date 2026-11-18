#!/usr/bin/env python3
"""The web home page drawn as reMarkable Paper Pro pages (1620x2160, 3:4).

    python3 automations/scripts/remarkable_pages.py OUT_DIR [--today YYYY-MM-DD]

An inbox page for free notes, then one page per group of the web home page
(`web/src/pages/index.astro`), in the page's order, then the one due review and the
task list: `0 - Inbox`, `1 - Today`, `2 - This quarter`, `3 - Always`, `4 - Review`,
`5 - Tasks`. Everything comes from `home_data.build_home`, the dict the web page,
Trello and TRMNL read, so no number can differ. This file only draws;
`remarkable_sync.py` uploads the pages and reads back what was written on them.

Each page returns a `marks` list: the things a pen can change, in drawing order,
with the record they write to and the box Claude is told to look in. Inbox: the
whole ruled area, each note sent to Trello's 📥 Inbox list, which the
`pfc-trello-inbox` timer processes when PFC_TRELLO_INBOX is on (else `/pfc-trello-inbox`).
Today: the rating rows (only while the day is unrated), the 2+1 done and swap
boxes, a pick box per suggestion, the habit checkboxes, a note box. This quarter:
park a focus, a note box (project updates go there). Always: an area's G/Y/R
letters, a note box. Review: the one due review's form. Tasks: done, drop, and
writing beside a task.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

W, H = 1620, 2160
M = 80
GAP = 36
REPLY_LINES = 4
REPLY_X = 700  # the agent's replies sit in the header's top-right corner, right of the title
PAGE_NAMES = ["0 - Inbox", "1 - Today", "2 - This quarter", "3 - Always", "4 - Review", "5 - Tasks"]

_FONT_DIRS = ["/usr/share/fonts/truetype/dejavu", "/Library/Fonts", str(Path.home() / "Library/Fonts")]


def _font(size, bold=False):
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    for d in _FONT_DIRS:
        p = Path(d) / name
        if p.exists():
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default(size)


F_H1, F_SUB, F_T, F_B, F_BB, F_S = (_font(60, True), _font(28), _font(36, True), _font(30),
                                    _font(30, True), _font(25))
F_SB, F_XS = _font(25, True), _font(23)

# The web palette (web/src/layouts/Base.astro), on a white page for e-ink contrast.
INK, SUB, MUTED, BORDER, CARD = "#073642", "#4f656c", "#657b83", "#c9c0a4", "#fffdf5"
LIGHT = {"red": "#dc322f", "yellow": "#b58900", "green": "#859900"}
GREY = "#93a1a1"
WORST_FIRST = {"red": 0, "yellow": 1, "green": 2}


def _light(x):
    return LIGHT.get((x or "").lower(), GREY)


def _watch_logged():
    """Habits `derive_workout_habits.py` logs from the watch (a `workout:` block): they
    keep a checkbox, as on the web, for a session the watch missed."""
    try:
        import yaml
        cfg = yaml.safe_load((SCRIPT_DIR.parents[1] / "config" / "habit_schema.yaml").read_text())
    except Exception:  # noqa: BLE001 — a label, never worth failing a page for
        return set()
    habits = cfg.get("daily_habits") if isinstance(cfg, dict) else None
    return {hb["id"] for hb in habits or [] if isinstance(hb, dict) and hb.get("workout")}


def _date(s):
    return datetime.strptime(s, "%Y-%m-%d")


def _day(s):
    d = _date(s)
    return f"{d.strftime('%A')} {d.day}"


class Page:
    def __init__(self, name, title, sub, date):
        self.name = name
        self.im = Image.new("RGB", (W, H), "white")
        self.d = ImageDraw.Draw(self.im)
        self.marks = []
        d = _date(date)
        self.d.text((M, 60), f"{d.strftime('%A, %B')} {d.day}", font=F_SUB, fill=SUB)
        self.d.text((M, 100), title, font=F_H1, fill=INK)
        self.d.text((M, 178), sub, font=F_SUB, fill=SUB)
        self.y = 240
        self._measuring = False

    @property
    def pages(self):
        """A one-page document; `Doc` holds several (the task list)."""
        return [self]

    # -- drawing primitives -------------------------------------------------
    def wrap(self, text, font, width):
        lines, cur = [], ""
        for w in str(text).split():
            t = (cur + " " + w).strip()
            if font.getlength(t) <= width or not cur:
                cur = t
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines or [""]

    def text(self, x, y, s, font=F_B, fill=INK, width=None):
        lh = int(font.size * 1.35)
        lines = self.wrap(s, font, width) if width else [str(s)]
        for i, line in enumerate(lines):
            self.d.text((x, y + i * lh), line, font=font, fill=fill)
        return y + len(lines) * lh

    def dot(self, x, y, light, r=None):
        """A status chip: a solid colour block with its letter (R, Y, G) in white, big
        enough to tell the colours apart on e-ink, and readable even without colour
        (AGENTS.md: shape plus word where colour may not render). `y` is where a
        small dot used to sit; the chip is centred on the text line beside it."""
        key = (light or "").lower()
        letter = {"red": "R", "yellow": "Y", "green": "G", "parked": "P"}.get(key, "?")
        top = y - 8
        self.d.rounded_rectangle((x, top, x + 38, top + 36), radius=8, fill=_light(light))
        tw = F_BB.getlength(letter)
        self.d.text((x + 19 - tw / 2, top + 1), letter, font=F_BB, fill="white")

    def box(self, x, y, s=34):
        self.d.rounded_rectangle((x, y, x + s, y + s), radius=6, outline=INK, width=3)

    def ring(self, x, y, label, r=30):
        self.d.ellipse((x, y, x + 2 * r, y + 2 * r), outline=SUB, width=2)
        tw = F_BB.getlength(label)
        self.d.text((x + r - tw / 2, y + r - 18), label, font=F_BB, fill=INK)

    def write_line(self, x, y, w, label):
        self.d.text((x, y), label, font=F_S, fill=MUTED)
        lx = int(x + F_S.getlength(label) + 14)
        for px in range(lx, x + w, 18):
            self.d.line((px, y + 30, px + 8, y + 30), fill=MUTED, width=2)
        return y + 52

    def mark(self, **m):
        """Record a writable spot (only on the real pass, not while measuring a card)."""
        if not self._measuring:
            self.marks.append(m)

    def title(self, x, y, s, note=None):
        self.d.text((x, y), s, font=F_T, fill=INK)
        if note:
            self.d.text((x + F_T.getlength(s) + 18, y + 8), note, font=F_S, fill=SUB)
        return y + 58

    # -- layout -------------------------------------------------------------
    def card(self, x, w, draw):
        """Measure on a scratch canvas, draw the card background, then draw for real."""
        top = self.y
        real_im, real_d = self.im, self.d
        self.im = Image.new("RGB", (W, H * 2), "white")
        self.d = ImageDraw.Draw(self.im)
        self._measuring = True
        bottom = draw(self, x + 32, top + 28, w - 64)
        self.im, self.d, self._measuring = real_im, real_d, False
        self.d.rounded_rectangle((x, top, x + w, bottom + 24), radius=22, fill=CARD, outline=BORDER, width=2)
        draw(self, x + 32, top + 28, w - 64)
        return bottom + 24

    def band(self, draw):
        self.y = self.card(M, W - 2 * M, draw) + GAP

    def columns(self, lefts, rights):
        cw = (W - 2 * M - GAP) // 2
        top, ends = self.y, []
        for x, cards in ((M, lefts), (M + cw + GAP, rights)):
            self.y = top
            for c in cards:
                self.y = self.card(x, cw, c) + GAP
            ends.append(self.y)
        self.y = max(ends)

    def note_box(self, x, y, w, page, examples, lines=None):
        """A ruled box for a note to the agent; read like the inbox, tagged with the page.
        With no `lines` it fills the rest of the page (at least 3 lines)."""
        y = self.title(x, y, "Note for the agent", examples)
        top = y
        if lines is None:
            lines = max(3, (H - 70 - top - 64 - 20) // 64 + 1)
        for i in range(lines):
            ly = y + 64 + i * 64
            self.d.line((x, ly, x + w, ly), fill=BORDER, width=2)
        self.mark(kind="note", page=page, label=f"the 'Note for the agent' ruled box ({page} page)",
                  box=[x, top - 10, x + w, top + 64 * lines + 20])
        return top + 64 * lines + 10

    def agent_strip(self, replies):
        """The agent's replies on this page, newest first (remarkable_replies.py), in
        the top-right corner of the header: the first thing you see, and it never
        collides with a page's content, whatever its length."""
        import remarkable_replies
        x, right, y = REPLY_X, W - M, 22
        self.d.text((x, y), "Agent", font=F_SB, fill=INK)
        y += 32
        lines = []
        for r in replies or []:
            lines += self.wrap(f"{remarkable_replies.stamp(r)}  {r['text']}", F_XS, right - x)[:2]
        if not lines:
            lines = ["Nothing from this page in the last day.", "Write anywhere on it to reach me."]
        for line in lines[:REPLY_LINES]:
            while F_XS.getlength(line) > right - x and len(line) > 4:
                line = line[:-4] + "..."
            self.d.text((x, y), line, font=F_XS, fill=SUB if replies else MUTED)
            y += 29


# ---------------------------------------------------------------- 0 Inbox
INBOX_LINES = 19


def inbox_unattended():
    """True when the pfc-trello-inbox timer carries notes out (PFC_TRELLO_INBOX=1 in
    .env or the environment); the inbox page then says so instead of naming the skill."""
    try:
        from web_data import load_env
        return load_env().get("PFC_TRELLO_INBOX") == "1"
    except Exception:
        return False


def _inbox(h, replies, unattended=None):
    if unattended is None:
        unattended = inbox_unattended()
    p = Page(PAGE_NAMES[0], "Inbox", "Anything for the system: a task, a project update, a note for an area.",
             h["date"])
    top = p.y + 20
    if unattended:
        lines = ("One note per line, or leave a gap between notes. Within about 15 minutes each note is added to "
                 "the system;", "one that is unclear waits in Trello's Inbox list marked ?. This page comes back blank.")
    else:
        lines = ("One note per line, or leave a gap between notes. Each note becomes a card in Trello's Inbox",
                 "list, word for word, for /pfc-trello-inbox. This page comes back blank.")
    p.d.text((M, top), lines[0], font=F_S, fill=SUB)
    p.d.text((M, top + 36), lines[1], font=F_S, fill=SUB)
    first = top + 130
    step = 76
    for i in range(INBOX_LINES):
        y = first + i * step
        p.d.line((M, y, W - M, y), fill=BORDER, width=2)
    p.mark(kind="inbox", label="the ruled writing area", box=[M, top + 80, W - M, first + INBOX_LINES * step])
    p.agent_strip(replies.get(p.name))
    return p


# ---------------------------------------------------------------- 1 Today
def _today(h, replies, review=None):
    p = Page(PAGE_NAMES[1], "Today", "Body first, then the picks.", h["date"])

    def body(p, x, y, w):
        b, pu = h.get("body") or {}, h.get("pulse") or {}
        p.dot(x, y + 10, (pu.get("verdict_mark") or "").lower())
        p.d.text((x + 54, y), "Body first", font=F_T, fill=INK)
        y = p.text(x, y + 58, pu.get("verdict") or "Last night's sleep decides what today can hold.", F_BB, width=w)
        if pu.get("move"):
            y = p.text(x, y + 6, "Tonight: " + pu["move"], F_B, SUB, width=w)
        y += 16
        slept = "No data" if b.get("sleep_hours") is None else f"{b['sleep_hours']} h"
        stats = [(slept, "slept")]
        if b.get("awake_minutes") is not None:
            stats.append((f"{b['awake_minutes']} min", "awake in the night"))
        cw = w // 3
        for i, (v, label) in enumerate(stats):
            p.d.text((x + i * cw, y), v, font=_font(44, True), fill=INK)
            p.text(x + i * cw, y + 56, label, F_S, SUB, width=cw - 20)
        y += 110
        levers = pu.get("levers") or []
        off = [lv for lv in levers if lv.get("mark") != "GREEN"]
        if levers:
            # The three worst levers side by side, each with its chip, value and nights on target.
            for i, lv in enumerate(off[:3]):
                lx = x + i * cw
                p.dot(lx, y + 6, lv["mark"].lower())
                p.d.text((lx + 50, y), f"{lv['label']} {lv['value']}", font=F_S, fill=INK)
                if lv.get("on") is not None:
                    p.d.text((lx + 50, y + 32), f"on target {lv['on']} of {lv['n']} nights", font=F_S, fill=SUB)
            y += 70
            on = len(levers) - len(off)
            more = len(off) - 3
            tail = ", ".join(s for s in [f"{more} more off target" if more > 0 else "",
                                          f"{on} on target last night" if on else ""] if s)
            if tail:
                y = p.text(x, y, tail, F_S, SUB) + 4
        return y

    def rate(p, x, y, w):
        rt = h["rate_target"]
        y = p.title(x, y, f"How was {_date(rt['date']).strftime('%A')}?", "5 is best.")
        for key, label in [("energy", "Energy"), ("mood", "Mood"), ("focus", "Focus")]:
            p.d.text((x, y + 12), label, font=F_BB, fill=INK)
            for n in range(1, 6):
                p.ring(x + 268 + (n - 1) * 70, y, str(n), 26)
            p.mark(kind="rating", field=key, date=rt["date"], label=f"{label} row (circle 1 to 5)",
                   box=[x, y - 4, x + 640, y + 56])
            y += 64
        # The web card's optional row, same wording (web/src/pages/index.astro).
        p.d.text((x, y + 12), "Hyperfocused", font=F_BB, fill=INK)
        for i, c in enumerate(("Yes", "No")):
            p.ring(x + 290 + i * 100, y, c, 30)
        p.mark(kind="rating", field="hyperfocused", date=rt["date"], label="Hyperfocused? row (circle Yes or No; "
               "optional)", box=[x, y - 4, x + 640, y + 64])
        return y + 66

    def rated(p, x, y, w):
        rt = h["rate_target"]
        y = p.title(x, y, f"{_date(rt['date']).strftime('%A')} is rated")
        return p.text(x, y, "Nothing to rate until the next day.", F_S, SUB, width=w)

    def picks(p, x, y, w):
        pk = h.get("picks") or {}
        y = p.title(x, y, "The 2+1", "Tick when done, or swap.")
        fd = h.get("focus_of_day")
        if fd:  # the web band's Why line: one focus a day, with its vision and value
            why = " → ".join(t for t in (fd.get("title"), fd.get("vision"), fd.get("value")) if t)
            y = p.text(x, y - 6, "Why: " + why, F_S, SUB, width=w) + 8
        rows = [(t, "") for t in pk.get("critical") or []]
        if pk.get("bonus"):
            rows.append((pk["bonus"], "Bonus: "))
        if not rows:
            y = p.text(x, y, "No picks set yet: tick one below.", F_S, SUB, width=w) + 8
        for t, tag in rows:
            if t.get("done"):
                p.d.text((x, y), "✓", font=F_BB, fill=LIGHT["green"])
                y = p.text(x + 56, y, tag + t["title"], F_B, MUTED, width=w - 56) + 14
                continue
            p.box(x, y + 2)
            p.mark(kind="task", id=t["id"], label=f"done checkbox: {tag}{t['title']}",
                   box=[x - 10, y - 6, x + 50, y + 46])
            sx = x + w - 34
            p.d.text((sx - F_S.getlength("swap") - 10, y + 6), "swap", font=F_S, fill=MUTED)
            p.box(sx, y + 2)
            p.mark(kind="swap", id=t["id"], date=h["date"], label=f"swap checkbox (right edge): {tag}{t['title']}",
                   box=[sx - 90, y - 6, sx + 44, y + 46])
            y = p.text(x + 56, y, tag + t["title"], F_B, width=w - 56 - 130) + 14
        # The web page's suggestions, for the day it is picking (tomorrow from about 6 PM).
        sugg = h.get("suggested") or []
        if sugg:
            day = h.get("pick_date") or h["date"]
            snap = h.get("tomorrow_picks") if day != h["date"] else pk
            snap = snap or {}
            label = "Pick for tomorrow" if day != h["date"] else "Swap in"
            y = p.text(x, y + 6, label, F_BB) + 4
            for t in sugg[:3]:
                p.box(x, y + 2, 30)
                p.mark(kind="pick", id=t["id"], date=day, critical=list(snap.get("critical_ids") or []),
                       bonus=snap.get("bonus_id"), label=f"pick checkbox: {t['title']}",
                       box=[x - 10, y - 6, x + 46, y + 42])
                y = p.text(x + 48, y, t["title"], F_S, SUB, width=w - 48) + 10
        tp = h.get("tomorrow_picks")
        if h.get("evening") and tp:
            y = p.text(x, y + 6, "Tomorrow", F_BB) + 2
            for t in (tp.get("critical") or []) + ([tp["bonus"]] if tp.get("bonus") else []):
                y = p.text(x, y, "· " + t["title"], F_S, SUB, width=w) + 4
        # What needs you, as on the web: overdue items that are not picks, the one due
        # review (it is on page 4), the hand-off count.
        ids = {t["id"] for t in (pk.get("critical") or [])} | ({pk["bonus"]["id"]} if pk.get("bonus") else set())
        needs = [n for n in h.get("needs_you") or [] if n.get("id") not in ids]
        lines = [n["title"] + (f" ({n['why']} {_date(n['date']).strftime('%b')} {_date(n['date']).day})"
                               if n.get("date") else "") for n in needs[:2]]
        if review:
            lines.append(f"Review: {review['label']} (page 4)")
        if h.get("handoffs"):
            lines.append(f"{len(h['handoffs'])} tasks an agent can do: hand off on the web or in a note")
        if lines:
            y = p.text(x, y + 6, "What needs you", F_BB) + 2
            for line in lines:
                y = p.text(x, y, "· " + line, F_S, SUB, width=w) + 4
        return y

    def habits(p, x, y, w):
        daily = [r for r in h.get("habits") or [] if r.get("cadence") == "daily" and not r.get("auto_derived")]
        watch = _watch_logged()
        y = p.title(x, y, "Habits", "Tick today's.")
        cw = w // 2
        for i, r in enumerate(daily):
            hx, hy = x + (i % 2) * cw, y + (i // 2) * 46
            name = r["title"] + (" *" if r["id"] in watch else "")
            if r.get("logged_today"):
                p.d.text((hx, hy - 4), "✓", font=F_BB, fill=LIGHT["green"])
                p.text(hx + 40, hy, name, F_S, MUTED, width=cw - 48)
            else:
                p.box(hx, hy, 30)
                p.mark(kind="habit", id=r["id"], date=h["date"], label=f"checkbox: {r['title']}",
                       box=[hx - 10, hy - 8, hx + 46, hy + 40])
                p.text(hx + 40, hy, name, F_S, INK, width=cw - 48)
        y += ((len(daily) + 1) // 2) * 46
        monthly = [r for r in h.get("habits") or [] if r.get("cadence") == "monthly" and not r.get("auto_derived")]
        if monthly:
            y = p.text(x, y, "This month", F_BB, SUB) + 4
            for i, r in enumerate(monthly):
                hx, hy = x + (i % 2) * cw, y + (i // 2) * 46
                p.box(hx, hy, 30)
                p.mark(kind="habit", id=r["id"], date=h["date"], label=f"checkbox (monthly): {r['title']}",
                       box=[hx - 10, hy - 8, hx + 46, hy + 40])
                p.text(hx + 40, hy, r["title"], F_S, INK, width=cw - 48)
            y += ((len(monthly) + 1) // 2) * 46
        if any(r["id"] in watch for r in daily):
            y = p.text(x, y, "* also logged from the watch", F_S, MUTED) + 2
        return y

    def week(p, x, y, w):
        """Compact: each day's first three events on one wrapped line, so the band
        fits beside the tall rating card without running off the page."""
        y = p.title(x, y, "Week", "today and tomorrow")
        for i, day in enumerate((h.get("week") or [])[:2]):
            y = p.text(x, y + (10 if i else 0), _day(day["date"]), F_BB) + 2
            evs = day.get("events") or []
            parts = []
            for e in evs[:3]:
                t = datetime.fromisoformat(e["start"]) if "T" in e.get("start", "") else None
                parts.append((t.strftime("%I:%M %p").lstrip("0") + " " if t else "") + e["title"])
            line = " · ".join(parts) + (f" · {len(evs) - 3} more" if len(evs) > 3 else "")
            y = p.text(x, y, line or "Nothing scheduled", F_S, SUB if evs else MUTED, width=w) + 2
        return y

    p.band(body)
    first = rate if h["rate_target"].get("unrated") else rated
    note = lambda p, x, y, w: p.note_box(x, y, w, "Today", "habits, tasks")  # noqa: E731
    if first is rate:  # the tall rating card: Week goes under the 2+1 instead
        p.columns([first, habits, note], [picks, week])
    else:
        p.columns([first, habits, week], [picks, note])
    p.agent_strip(replies.get(p.name))
    return p


# ---------------------------------------------------------------- 2 This quarter
def _quarter(h):
    p = Page(PAGE_NAMES[2], "This quarter", "What you are on now, and how it is going.", h["date"])

    def focuses(p, x, y, w):
        y = p.title(x, y, "Focuses", "impact and urgency first. Tick park to pause one.")
        names = {"foundation": "Foundations", "pursuit": "Active Pursuits", "consuming": "Currently Consuming"}
        for tier, rows in (h.get("focuses") or {}).items():
            if not rows:
                continue
            y = p.text(x, y + 4, names.get(tier, tier), F_BB, SUB) + 6
            for r in rows:
                p.dot(x, y + 6, r.get("light"))
                p.d.text((x + 52, y), str(r["title"])[:52], font=F_B, fill=MUTED if r.get("parked") else INK)
                pr = r.get("primary")
                right = "parked" if r.get("parked") else (f"{pr['completed']} of {pr['target']}" if pr else "")
                p.d.text((x + w - 300, y + 4), right, font=F_S, fill=SUB)
                if not r.get("parked") and r.get("focus_id"):
                    bx = x + w - 34
                    p.d.text((bx - F_S.getlength("park") - 10, y + 4), "park", font=F_S, fill=MUTED)
                    p.box(bx, y, 30)
                    p.mark(kind="park", id=r["focus_id"], label=f"park checkbox (right edge): {r['title']}",
                           box=[bx - 80, y - 8, bx + 40, y + 40])
                y += 42
        return y

    def projects(p, x, y, w):
        y = p.title(x, y, "Projects", "updates go in the note box")
        for r in (h.get("projects") or {}).get("active") or []:
            p.d.text((x, y), r["name"], font=F_BB, fill=INK)
            bx = x + w - 260
            p.d.rounded_rectangle((bx, y + 8, bx + 200, y + 28), radius=10, outline=SUB, width=2)
            pct = max(0, min(100, r.get("pct") or 0))
            if pct:
                p.d.rounded_rectangle((bx, y + 8, bx + 2 * pct, y + 28), radius=10, fill=LIGHT["green"])
            p.d.text((bx + 212, y + 2), f"{pct}%", font=F_S, fill=SUB)
            nxt = (r.get("next_task") or {}).get("title") or "no next task"
            idle = f"  ·  idle {r['days_idle']} days" if r.get("stalled") else ""
            line = "Next: " + nxt + idle
            while F_S.getlength(line) > w and len(line) > 20:
                line = line[:-2]
            if line != "Next: " + nxt + idle:
                line = line.rstrip() + "…"
            y = p.text(x, y + 44, line, F_S, SUB) + 2
            y += 6
        return y

    def trends(p, x, y, w):
        y = p.title(x, y, "Trends", "last 30 days, worst first")
        rows = sorted(h.get("trends") or [], key=lambda t: WORST_FIRST.get(t.get("light"), 3))
        for t in [t for t in rows if t.get("light") != "green"]:
            p.dot(x, y + 6, t.get("light"))
            y = p.text(x + 52, y, f"{t['name']}: {t.get('why') or ''}", F_S, INK, width=w - 52) + 10
        on = [t["name"] for t in rows if t.get("light") == "green"]
        if on:
            p.dot(x, y + 6, "green")
            y = p.text(x + 52, y, "On track: " + ", ".join(on), F_S, SUB, width=w - 52) + 4
        return y

    p.band(focuses)
    p.band(projects)
    p.columns([trends], [lambda p, x, y, w: p.note_box(x, y, w, "This quarter", "focuses, projects")])
    return p


# ---------------------------------------------------------------- 3 Always
def _always(h):
    p = Page(PAGE_NAMES[3], "Always", "Where life lives, and what it is judged by.", h["date"])

    def areas(p, x, y, w):
        pl = h.get("plate") or {}
        y = p.title(x, y, "Areas", "Circle G, Y or R to change a hand-set one; the rest follow their items.")
        if pl.get("free"):
            y = p.text(x, y, f"The plate: {pl['committed']:.0f} of {pl['free']} free waking hours committed "
                             f"({pl['pct']}%)", F_S, SUB, width=w) + 10
        for r in (h.get("areas") or {}).get("rows") or []:
            p.dot(x, y + 6, r.get("light"))
            p.d.text((x + 52, y), r["label"], font=F_BB, fill=INK)
            why = r.get("why") if r.get("light") != "green" else ""
            if r.get("source") == "items":
                # Lit by its items: the reason, no letters to circle (it changes when they do).
                if why:
                    line = why
                    while F_S.getlength(line) > w - 290 and len(line) > 10:
                        line = line[:-2]
                    p.d.text((x + 280, y + 4), line if line == why else line.rstrip() + "…", font=F_S, fill=SUB)
            else:
                if why:
                    p.d.text((x + 280, y + 4), str(why)[:44], font=F_S, fill=SUB)
                for i, c in enumerate("GYR"):
                    p.ring(x + w - 190 + i * 66, y - 8, c, 24)
                p.mark(kind="area", id=r["key"], label=f"{r['label']} row: G/Y/R letters at the right, "
                       f"currently {r.get('light')}", box=[x, y - 10, x + w, y + 44])
            y += 46
        y += 8
        if not h.get("household"):  # parked (config/automation_config.yaml)
            return y
        rows = sorted(h["household"].get("rows") or [], key=lambda r: WORST_FIRST.get(r.get("light"), 3))
        look = [r for r in rows if r.get("light") != "green"]
        y = p.text(x, y, "Rooms", F_BB, SUB) + 4
        cw = w // 3
        for i, r in enumerate(look):
            cx, cy = x + (i % 3) * cw, y + (i // 3) * 42
            p.dot(cx, cy + 6, r.get("light"))
            p.d.text((cx + 52, cy), r["label"], font=F_B, fill=INK)
        y += ((len(look) + 2) // 3) * 42
        p.dot(x, y + 6, "green")
        return p.text(x + 52, y, f"{len(rows) - len(look)} of {len(rows)} rooms green", F_B)

    def values(p, x, y, w):
        y = p.title(x, y, "Values")
        y = p.text(x, y, "  ·  ".join(h.get("values") or []), F_B, width=w)
        q = h.get("question_of_day")
        if q:
            y = p.text(x, y + 14, "Question of the day: " + q["text"], F_S, SUB, width=w)
        return y

    def front(p, x, y, w):
        y = p.title(x, y, "Front of mind")
        for a in h.get("anchors") or []:
            y = p.text(x, y, a["title"], F_B, width=w) + 12
        return y

    def visions(p, x, y, w):
        y = p.title(x, y, "Visions")
        v = h.get("vision_of_day")
        if v:
            y = p.text(x, y, "Today: " + v["title"], F_BB, width=w) + 10
        others = [r["title"].split(" — ")[0] for r in h.get("visions") or [] if not v or r["id"] != v.get("id")]
        return p.text(x, y, "  ·  ".join(others), F_S, SUB, width=w)

    p.band(areas)
    p.columns([values, visions], [front, lambda p, x, y, w: p.note_box(x, y, w, "Always", "why; areas, visions")])
    return p


# ---------------------------------------------------------------- 4 Review
def _pill(p, x, y, label):
    """An option to circle: its word in a rounded outline. Returns the right edge."""
    tw = F_S.getlength(label)
    p.d.rounded_rectangle((x, y, x + tw + 28, y + 40), radius=20, outline=SUB, width=2)
    p.d.text((x + 14, y + 6), label, font=F_S, fill=INK)
    return x + tw + 28


def _review(h, review):
    p = Page(PAGE_NAMES[4], "Review", "One review at a time. Circle, tick and write; the next sync saves it.",
             h["date"])
    if not review:
        p.d.text((M, p.y + 20), "No reviews due right now.", font=F_T, fill=INK)
        return p

    def head(p, x, y, w):
        y = p.text(x, y, review["label"], F_T, INK, width=w - 260) + 4
        over = review.get("overdue_days")
        why = "never done yet" if over is None else (f"{over} days overdue" if over else "due today")
        n = review.get("due_count") or 1
        y = p.text(x, y, f"{why}  ·  {n} due, one at a time", F_S, SUB) + 4
        if review.get("intro"):
            y = p.text(x, y, review["intro"], F_S, SUB, width=w) + 4
        bx = x + w - 34
        p.d.text((bx - F_S.getlength("skip this review") - 10, y - 74), "skip this review", font=F_S, fill=MUTED)
        p.box(bx, y - 80, 30)
        p.mark(kind="review-skip", id=review["id"], label="'skip this review' checkbox (top right)",
               box=[bx - 230, y - 90, bx + 40, y - 40])
        return y

    p.band(head)

    for si, sec in enumerate(review["sections"]):
        if sec["kind"] == "prompt":
            def prompt(p, x, y, w, sec=sec):
                y = p.text(x, y, sec["question"], F_BB, INK, width=w) + 6
                top = y
                for i in range(sec["lines"]):
                    p.d.line((x, y + 56 + i * 60, x + w, y + 56 + i * 60), fill=BORDER, width=2)
                y = top + 56 + sec["lines"] * 60
                p.mark(kind="review-prompt", id=sec["id"], review=review["id"],
                       label=f"answer lines under: {sec['question'][:80]}", box=[x, top - 10, x + w, y])
                return y
            p.band(prompt)
            continue

        def choices(p, x, y, w, sec=sec):
            y = p.text(x, y, sec["title"], F_T, INK, width=w) + 2
            if sec.get("hint"):
                y = p.text(x, y, sec["hint"], F_S, SUB, width=w) + 6
            opts = sec.get("options") or []
            pills_w = sum(F_S.getlength(o) + 28 for o in opts) + 12 * max(0, len(opts) - 1)
            title_w = w - pills_w - 24 if opts else w

            def row_h(row):
                hgt = len(p.wrap(row["title"], F_BB, title_w)) * int(F_BB.size * 1.35) + 2
                if row.get("detail"):
                    hgt += len(p.wrap(row["detail"], F_S, title_w)) * int(F_S.size * 1.35) + 2
                return hgt + (60 if sec.get("note") else 0) + 14

            for ri, row in enumerate(sec["rows"]):
                # A long row that would run off the page waits for the next form whole.
                if y > H - 260 or (ri and y + row_h(row) > H - 200):
                    # Rows past the page aren't marked shown, so the next form starts with them.
                    left = len(sec["rows"]) - ri
                    y = p.text(x, y, f"{left} more rows did not fit this page; they come on the next form.",
                               F_S, SUB, width=w) + 4
                    break
                top = y
                y = p.text(x, y, row["title"], F_BB, INK, width=title_w) + 2
                px = x + w - pills_w
                for o in opts:
                    px = _pill(p, px, top - 4, o) + 12
                if row.get("detail"):
                    y = p.text(x, y, row["detail"], F_S, SUB, width=title_w) + 2
                if sec.get("note"):
                    y = p.write_line(x, y, w, "note:") - 6
                p.mark(kind="review-row", id=row["id"], review=review["id"], options=opts, note=bool(sec.get("note")),
                       label=f"row '{row['title'][:70]}': " + (f"circle one of {', '.join(opts)}" if opts else
                                                                 "the note line is the answer")
                       + (", plus the note line" if opts and sec.get("note") else ""),
                       box=[x, top - 8, x + w, y + 4])
                y += 14
            return y
        p.band(choices)
    return p


class Doc:
    """A document of several pages under one name (the task list)."""

    def __init__(self, name, pages):
        self.name, self.pages = name, pages


# ---------------------------------------------------------------- 5 Tasks
def open_tasks():
    """Every open task in the web Tasks page's order (web/src/lib/priority.ts): the
    impact/urgency code (AA first, no code last), then file order."""
    import json as _json
    repo = SCRIPT_DIR.parents[1]

    def rows(rel):
        p = repo / rel
        return [_json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []
    letter = {"high": "A", "medium": "B", "low": "C"}
    projects = {p["id"]: p.get("name") for p in rows("5-projects/_data/projects.ndjson")}
    out = []
    for i, t in enumerate(rows("6-tasks/_data/tasks.ndjson")):
        if t.get("status") != "open":
            continue
        code = (letter.get(t.get("impact")) or "") + (letter.get(t.get("urgency")) or "")
        code = code if len(code) == 2 else ""
        out.append({**t, "code": code, "project_name": projects.get(t.get("project")), "_i": i})
    out.sort(key=lambda t: (t["code"] == "", t["code"], t["_i"]))
    return out


def _tasks(h, tasks=None):
    tasks = open_tasks() if tasks is None else tasks
    pages, i, n = [], 0, 0
    while True:
        n += 1
        p = Page(PAGE_NAMES[5], "Tasks", f"{len(tasks)} open, top priority first. Tick done, tick drop to remove "
                 "one, or write beside a task.", h["date"])
        p.d.text((M + F_H1.getlength("Tasks") + 24, 128), f"page {n}", font=F_SUB, fill=SUB)

        def rows(p, x, y, w, start=i):
            k = start
            while k < len(tasks) and y < H - 480:  # room for a 3-line note box below
                t = tasks[k]
                top = y
                p.box(x, y + 2)
                p.mark(kind="task", id=t["id"], label=f"done checkbox: {t['description'][:80]}",
                       box=[x - 10, y - 6, x + 50, y + 46])
                dx = x + w - 34
                p.d.text((dx - F_S.getlength("drop") - 10, y + 6), "drop", font=F_S, fill=MUTED)
                p.box(dx, y + 2)
                p.mark(kind="drop", id=t["id"], label=f"drop checkbox (right edge): {t['description'][:80]}",
                       box=[dx - 80, y - 6, dx + 44, y + 46])
                label = (t["code"] + "  " if t["code"] else "") + t["description"]
                y = p.text(x + 56, y, label, F_B, INK, width=w - 56 - 130) + 2
                meta = " · ".join(s for s in (t.get("project_name"), t.get("area"),
                                              f"due {_date(t['deadline']).strftime('%b')} {_date(t['deadline']).day}" if t.get("deadline") else None,
                                              "deferred" if t.get("deferred") else None) if s)
                if meta:
                    y = p.text(x + 56, y, meta, F_S, SUB, width=w - 56 - 130)
                p.mark(kind="task-note", id=t["id"], title=t["description"][:80],
                       label=f"the row of task '{t['description'][:60]}' (writing on or beside it)",
                       box=[x, top - 8, x + w, y + 8])
                y += 18
                k += 1
            p._rows_end = k
            return y

        p.band(rows)
        i = getattr(p, "_rows_end", i)
        p.band(lambda p, x, y, w: p.note_box(x, y, w, "Tasks", "a new task, anything"))
        pages.append(p)
        if i >= len(tasks) or n >= 20:
            break
    return Doc(PAGE_NAMES[5], pages)


def load_home(today=None):
    """`home_data.build_home` the way `web_data.py --home` calls it."""
    import review_forms
    return review_forms.load_home(today)


def build_pages(h, replies=None, review="current", tasks=None):
    """The inbox, the three web groups, the one due review and the task list, for one
    `build_home` dict. `review` is a `review_forms.current_review` result; "current"
    computes it. `replies` maps a page name to its agent replies (newest first); None
    reads them from remarkable_replies.py's store."""
    if review == "current":
        import review_forms
        review = review_forms.current_review(h, h["date"])
    if replies is None:
        import remarkable_replies
        replies = {name: remarkable_replies.recent(name) for name in PAGE_NAMES}
    docs = [_inbox(h, replies), _today(h, replies, review), _quarter(h), _always(h), _review(h, review),
            _tasks(h, tasks)]
    for doc in docs[2:]:
        for p in doc.pages:
            p.agent_strip(replies.get(doc.name))
    return docs


def save(doc, out_dir):
    """Write `<name>.pdf` (every page, what the tablet gets) and `<name>-p<N>.png` per
    page (the bases for reading marks). Returns (pdf, [png per page])."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf = out_dir / f"{doc.name}.pdf"
    ims = [p.im for p in doc.pages]
    ims[0].save(pdf, "PDF", resolution=229, save_all=True, append_images=ims[1:])
    pngs = []
    for k, im in enumerate(ims):
        png = out_dir / f"{doc.name}-p{k}.png"
        im.save(png)
        pngs.append(png)
    return pdf, pngs


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out_dir")
    ap.add_argument("--today")
    args = ap.parse_args(argv)
    for doc in build_pages(load_home(args.today)):
        pdf, pngs = save(doc, args.out_dir)
        print(json.dumps({"page": doc.name, "pdf": str(pdf), "pages": len(pngs),
                          "marks": sum(len(p.marks) for p in doc.pages)}))


if __name__ == "__main__":
    main()
