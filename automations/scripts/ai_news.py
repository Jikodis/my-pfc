#!/usr/bin/env python3
"""AI News: new posts from followed AI blogs → reMarkable EPUBs + private podcast episodes.

One daily run (systemd timer `pfc-ai-news`, early morning local time):

1. list posts on every source in config/ai_news.yaml; drop URLs already in
   data/ai-news.ndjson;
2. fetch each new post (title, date, body); posts older than `first_run_days` are
   logged as skipped without a Claude call, so the backlog never floods the tablet;
3. one headless Claude call decides keep or skip for the rest (ai_news_filter.py);
4. each kept post: an EPUB uploaded to the reMarkable folder `AI News`, and, unless it
   is partial or a changelog entry and while the month's voice budget lasts, an MP3;
5. append one line per finished post to data/ai-news.ndjson as it finishes (a run cut
   short reuses the MP3s it already made); prune MP3s older than `audio_keep_days`,
   rewrite the feed, commit and push. A post that got no audio because the month's
   voice allowance ran out is read aloud once the next month's allowance starts.

A post that fails is retried on the next runs, up to `max_attempts`, then logged
`failed`. See docs/ai-news.md.

    python3 automations/scripts/ai_news.py [--dry-run] [--limit N]
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import ai_news_epub  # noqa: E402
import ai_news_extract  # noqa: E402
import ai_news_feed  # noqa: E402
import ai_news_filter  # noqa: E402
import ai_news_sources  # noqa: E402
import ai_news_tts  # noqa: E402
import repo_sync  # noqa: E402

REPO = SCRIPT_DIR.parents[1]
CONFIG = REPO / "config" / "ai_news.yaml"
LOG = REPO / "data" / "ai-news.ndjson"
WORK = REPO / "data" / ".ai-news"
FEED = WORK / "feed"
LOCAL = ZoneInfo(os.environ.get("LOCAL_TZ", "America/Denver"))
RMAPI = os.environ.get("PFC_RMAPI") or shutil.which("rmapi") or str(Path.home() / ".local/bin/rmapi")
# Where trmnl_serve.py is reachable from the internet (docs/install/trmnl-endpoint.md).
DEFAULT_BASE = "https://trmnl.example.com"
BUDGET_REACHED = "monthly voice budget reached"  # read aloud later, once the next month's allowance starts


def load_env():
    env = {}
    p = REPO / ".env"
    if p.exists():
        for line in p.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip("\"'")
    env.update({k: v for k, v in os.environ.items() if v})
    return env


def today():
    return datetime.now(LOCAL).date()


def read_log(path=LOG):
    if not Path(path).exists():
        return []
    return [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]


def append_log(records, path=LOG):
    with open(path, "a") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n")


def load_state(path):
    try:
        return json.loads(Path(path).read_text())
    except (FileNotFoundError, ValueError):
        return {"attempts": {}}


def save_state(state, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(state, indent=1))


def episode_file(url):
    return hashlib.sha1(url.encode()).hexdigest()[:16] + ".mp3"


def rmapi(*args):
    p = subprocess.run([RMAPI, *args], capture_output=True, text=True, timeout=180)
    return p.returncode, (p.stdout + p.stderr)


def upload_epub(path, folder):
    code, out = rmapi("put", str(path), folder)
    if code != 0 and "exist" in out.lower():
        return  # already uploaded on an earlier attempt
    if code != 0:
        raise RuntimeError(f"rmapi put: {out.strip()[-200:]}")


def ensure_folder(folder):
    code, out = rmapi("ls", folder)
    if code != 0:
        code, out = rmapi("mkdir", folder)
        if code != 0:
            raise RuntimeError(f"rmapi mkdir {folder}: {out.strip()[-200:]}")


class Steps:
    """What a run does to the outside world; tests swap these."""
    list_all = staticmethod(ai_news_sources.list_all)
    extract = staticmethod(ai_news_extract.extract)
    decide = staticmethod(ai_news_filter.decide)
    upload = staticmethod(upload_epub)
    ensure_folder = staticmethod(ensure_folder)
    speak = staticmethod(ai_news_tts.synthesize)
    duration = staticmethod(ai_news_tts.duration_seconds)


def weekly_slots(sources, log, now):
    """{source id: posts it may still keep this week (Monday to Sunday)} for sources
    with a `weekly_cap`."""
    monday = (now - timedelta(days=now.weekday())).isoformat()
    out = {}
    for sid, src in sources.items():
        if src.get("weekly_cap") is not None:
            used = sum(1 for r in log if r.get("source") == sid and r.get("decision") == "keep"
                       and (r.get("decided") or "") >= monday)
            out[sid] = max(0, src["weekly_cap"] - used)
    return out


def process(cfg, env, steps=Steps, work=WORK, log_path=LOG, now=None, dry_run=False, limit=None):
    """One run. Returns a summary dict; appends finished posts to the log."""
    now = now or today()
    feed_dir = Path(work) / "feed"
    state_path = Path(work) / "state.json"
    state = load_state(state_path)
    usage = ai_news_tts.Usage(Path(work) / "tts-usage.json")
    month = now.strftime("%Y-%m")
    cutoff = (now - timedelta(days=cfg.get("first_run_days", 14))).isoformat()
    max_attempts = cfg.get("max_attempts", 3)

    known = {r["url"] for r in read_log(log_path)}
    posts, errors = steps.list_all(cfg["sources"])
    new, seen = [], set()
    for p in posts:
        if p["url"] not in known and p["url"] not in seen:
            seen.add(p["url"])
            new.append(p)
    if limit:
        new = new[:limit]

    done, articles, to_decide = [], {}, []

    def record(p, **kw):
        state["attempts"].pop(p["url"], None)
        done.append({"url": p["url"], "source": p["source"], "title": kw.pop("title", p.get("title", "")),
                     "published": kw.pop("published", p.get("published")), "decided": now.isoformat(), **kw})
        if not dry_run:  # logged as it finishes, so a run cut short never redoes this post
            append_log(done[-1:], log_path)
            save_state(state, state_path)

    def failed(p, why):
        n = state["attempts"].get(p["url"], 0) + 1
        state["attempts"][p["url"]] = n
        if n >= max_attempts:
            record(p, decision=None, reason=why[:200], status="failed")

    for p in new:
        if p.get("published") and p["published"] < cutoff:
            record(p, decision="skip", reason="older than the first-run window", status="skipped")
            continue
        try:
            a = steps.extract(p)
        except Exception as e:
            failed(p, f"extract: {e}")
            continue
        a["published"] = a.get("published") or p.get("published") or now.isoformat()
        if a["published"] < cutoff:
            record(p, title=a["title"], published=a["published"], decision="skip",
                   reason="older than the first-run window", status="skipped")
            continue
        articles[p["url"]] = a
        to_decide.append({**p, "title": a["title"], "opening": a["text"][:1200]})

    sources = {s["id"]: s for s in cfg["sources"]}
    slots = weekly_slots(sources, read_log(log_path), now)
    criteria = cfg["criteria"] + "".join(
        f"\n\nFrom {sid} keep at most {n} post{'s' if n != 1 else ''} this run, the most useful by the rule "
        f"above; rank the ones you keep." for sid, n in slots.items())
    decisions = steps.decide(to_decide, criteria) if to_decide else {}
    for sid, n in slots.items():  # a weekly cap holds even when Claude keeps more
        ranked = sorted((p for p in to_decide if p["source"] == sid and decisions.get(p["url"], {}).get("keep")),
                        key=lambda p: decisions[p["url"]].get("rank", 99))
        for p in ranked[n:]:
            decisions[p["url"]] = {"keep": False, "reason": f"over the weekly limit of "
                                   f"{sources[sid]['weekly_cap']} from this blog"}
    kept = [p for p in to_decide if decisions.get(p["url"], {}).get("keep")]
    for p in to_decide:
        d = decisions.get(p["url"])
        if d and not d["keep"]:
            a = articles[p["url"]]
            record(p, title=a["title"], published=a["published"], decision="skip", reason=d["reason"],
                   status="skipped")

    home = cfg.get("remarkable_folder", "AI News")

    def folder_of(p):
        return sources.get(p["source"], {}).get("folder") or home
    if kept and not dry_run:
        for f in sorted({home} | {folder_of(p) for p in kept}):  # the parent before its subfolder
            steps.ensure_folder(f)
    for p in kept:
        a, url = articles[p["url"]], p["url"]
        name = ai_news_extract.doc_name(a["published"], a["title"])
        rec = {"title": a["title"], "published": a["published"], "decision": "keep",
               "reason": decisions[url]["reason"], "partial": a["partial"], "epub": name, "mp3": None}
        if dry_run:
            record(p, **rec, status="dry-run")
            continue
        try:
            path = ai_news_epub.build_epub(a, url, Path(work) / "epub" / f"{name}.epub")
            steps.upload(path, folder_of(p))
        except Exception as e:
            failed(p, f"epub: {e}")
            continue
        speakable = not a["partial"] and p.get("kind") != "changelog" and p.get("audio", True) and a["text"]
        f = feed_dir / "episodes" / episode_file(url)
        if speakable and f.is_file() and f.stat().st_size:
            rec["mp3"], rec["seconds"] = f.name, steps.duration(f)  # spoken by a run cut short
        elif speakable and env.get("GOOGLE_TTS_API_KEY"):
            if usage.allowed(month, len(a["text"]), cfg.get("monthly_char_cap", ai_news_tts.MONTHLY_CAP)):
                try:
                    spoken = f"{a['title']}.\n\n{a['text']}"
                    usage.add(month, steps.speak(spoken, cfg["voice"], env["GOOGLE_TTS_API_KEY"], f))
                    rec["mp3"] = f.name
                    rec["seconds"] = steps.duration(f)
                except Exception as e:
                    rec["mp3_error"] = str(e)[:200]
            else:
                rec["mp3_error"] = BUDGET_REACHED
        record(p, **rec, status="done")

    late = []
    if not dry_run and env.get("GOOGLE_TTS_API_KEY"):
        late = voice_late(cfg, env, steps, state, usage, month, feed_dir, read_log(log_path), now)
        save_state(state, state_path)
    if not dry_run:
        ai_news_feed.prune(feed_dir / "episodes", cfg.get("audio_keep_days", 30))
        episodes = []
        spoken_late = state.get("late_audio", {})
        for r in sorted(read_log(log_path), key=lambda r: r.get("published") or "", reverse=True):
            ep = {"mp3": r.get("mp3"), "seconds": r.get("seconds", 0)} if r.get("mp3") else spoken_late.get(r["url"])
            f = feed_dir / "episodes" / ((ep or {}).get("mp3") or "")
            if ep and f.is_file():
                episodes.append({"file": ep["mp3"], "title": r["title"], "published": r["published"],
                                 "url": r["url"], "source": r["source"], "seconds": ep.get("seconds", 0),
                                 "bytes": f.stat().st_size})
        secret = env.get("AI_NEWS_FEED_SECRET", "")
        base = (env.get("AI_NEWS_FEED_BASE_URL") or DEFAULT_BASE).rstrip("/")
        ai_news_feed.write_feed(episodes, feed_dir / "feed.xml", f"{base}/p/pod/{secret}", f"{base}/")
        save_state(state, state_path)
    return {"new": len(new), "kept": len(kept), "logged": len(done), "errors": errors,
            "retrying": sorted(state["attempts"]), "records": done, "voiced_late": late}


def voice_late(cfg, env, steps, state, usage, month, feed_dir, log, now):
    """Kept posts that got no audio because the month's voice allowance ran out, read
    aloud newest first while this month's allowance lasts (so on the 1st, after a month
    that hit the limit). Their episodes are kept in state["late_audio"], the log being
    append-only. Returns the urls voiced."""
    done = state.setdefault("late_audio", {})
    sources = {s["id"]: s for s in cfg["sources"]}
    since = (now - timedelta(days=cfg.get("audio_keep_days", 30))).isoformat()
    cap = cfg.get("monthly_char_cap", ai_news_tts.MONTHLY_CAP)
    out = []
    for r in sorted(log, key=lambda r: r.get("published") or "", reverse=True):
        src = sources.get(r.get("source"), {})
        if (r.get("mp3_error") != BUDGET_REACHED or r["url"] in done or (r.get("decided") or "") < since
                or src.get("kind") == "changelog" or src.get("audio") is False):
            continue
        try:
            a = steps.extract({"url": r["url"], "source": r["source"], "title": r["title"],
                               "published": r.get("published"), "kind": src.get("kind", "article"),
                               "summary": "", "content_html": ""})
        except Exception:  # noqa: BLE001 — try again on the next run
            continue
        if a["partial"] or not a["text"]:
            continue
        if not usage.allowed(month, len(a["text"]), cap):
            break
        f = feed_dir / "episodes" / episode_file(r["url"])
        try:
            usage.add(month, steps.speak(f"{a['title']}.\n\n{a['text']}", cfg["voice"], env["GOOGLE_TTS_API_KEY"], f))
        except Exception:  # noqa: BLE001
            continue
        done[r["url"]] = {"mp3": f.name, "seconds": steps.duration(f), "on": now.isoformat()}
        out.append(r["url"])
    return out


def _git(*args):
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True, timeout=120,
                          env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "PFC_SKIP_TRELLO_RENDER": "1"})


def commit_log(day):
    if not _git("status", "--porcelain", "--", str(LOG.relative_to(REPO))).stdout.strip():
        return
    for args in (["add", str(LOG.relative_to(REPO))],
                 ["commit", "-q", "-m", f"ai-news: log {day}", "--", str(LOG.relative_to(REPO))]):
        r = _git(*args)
        if r.returncode != 0:
            raise RuntimeError(f"git {args[0]}: {(r.stderr or r.stdout)[-300:]}")
    for attempt in (1, 2):
        ok, detail = repo_sync.sync_with_upstream(_git, REPO)
        if not ok:
            raise RuntimeError(f"repo sync failed, commit kept locally: {detail}")
        if _git("push").returncode == 0:
            return
    raise RuntimeError("git push failed twice; commit kept locally")


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--dry-run", action="store_true", help="fetch and decide; upload, speak and log nothing")
    ap.add_argument("--limit", type=int, help="at most N new posts this run")
    args = ap.parse_args(argv)
    cfg = yaml.safe_load(CONFIG.read_text())
    env = load_env()
    if not args.dry_run:
        repo_sync.sync_with_upstream(_git, REPO)
    result = process(cfg, env, dry_run=args.dry_run, limit=args.limit)
    for r in result["records"]:
        mark = {"done": "KEEP", "dry-run": "KEEP", "skipped": "skip", "failed": "FAIL"}.get(r["status"], r["status"])
        audio = " +audio" if r.get("mp3") else (f" (no audio: {r['mp3_error']})" if r.get("mp3_error") else "")
        print(f"{mark:4}  {r.get('published')}  {r['source']:22}  {r['title'][:70]}{audio}  — {r.get('reason')}")
    for sid, err in result["errors"].items():
        print(f"SOURCE ERROR {sid}: {err}", file=sys.stderr)
    print(f"new {result['new']} · kept {result['kept']} · logged {result['logged']} · retrying {len(result['retrying'])}"
          f" · read aloud late {len(result['voiced_late'])}")
    if not args.dry_run:
        commit_log(today().isoformat())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
