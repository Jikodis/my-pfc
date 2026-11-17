"""AI News: speech chunks and budget, the podcast route, sources, extraction, EPUB, filter, run."""
from __future__ import annotations

import importlib.util
import json
import zipfile

import pytest

import ai_news_tts as tts
import trmnl_serve

# Fetching, extraction and EPUBs need these (pip install trafilatura feedparser lxml);
# without them those tests skip and the stdlib ones (speech, feed, route) still run.
HAS_DEPS = all(importlib.util.find_spec(m) for m in ("trafilatura", "feedparser", "lxml"))
needs_deps = pytest.mark.skipif(not HAS_DEPS, reason="needs trafilatura, feedparser and lxml")


# --- Task 1: speech and the feed route -------------------------------------------------

def test_chunks_under_limit_and_split_on_sentences():
    sentence = "Agents call tools in a loop until the task is done. "
    text = (sentence * 200).strip() + "\n\nShort tail."
    parts = tts.chunks(text, limit=1000)
    assert len(parts) > 1
    assert all(len(p.encode("utf-8")) <= 1000 for p in parts)
    assert all(p.rstrip().endswith((".", "!", "?")) for p in parts)
    assert parts[-1].endswith("Short tail.")
    assert " ".join(p.replace("\n\n", " ") for p in parts).split() == text.replace("\n\n", " ").split()


def test_chunks_cut_run_on_sentence():
    parts = tts.chunks("word " * 2000, limit=500)
    assert all(len(p.encode("utf-8")) <= 500 for p in parts)


def test_usage_caps_at_950k(tmp_path):
    u = tts.Usage(tmp_path / "usage.json")
    assert u.allowed("2025-01", 950_000)
    u.add("2025-01", 900_000)
    assert u.allowed("2025-01", 50_000)
    assert not u.allowed("2025-01", 50_001)
    assert u.allowed("2025-02", 50_001)  # a new month starts fresh


def test_pod_route_rejects_bad_secret_and_traversal(tmp_path):
    feed = tmp_path / "feed"
    (feed / "samples").mkdir(parents=True)
    (feed / "samples" / "a.mp3").write_bytes(b"x")
    (tmp_path / "secret.mp3").write_bytes(b"x")
    (feed / "notes.txt").write_text("x")
    ok = trmnl_serve.resolve_pod_path("/p/pod/s3cret/samples/a.mp3", "s3cret", feed)
    assert ok == (feed / "samples" / "a.mp3").resolve()
    assert trmnl_serve.resolve_pod_path("/p/pod/wrong/samples/a.mp3", "s3cret", feed) is None
    assert trmnl_serve.resolve_pod_path("/p/pod/s3cret/../secret.mp3", "s3cret", feed) is None
    assert trmnl_serve.resolve_pod_path("/p/pod/s3cret/notes.txt", "s3cret", feed) is None
    assert trmnl_serve.resolve_pod_path("/p/pod/s3cret/samples/a.mp3", "", feed) is None


# --- Task 2: sources -------------------------------------------------------------------

if HAS_DEPS:
    import ai_news_epub as epub
    import ai_news_extract as ext
    import ai_news_filter as flt
    import ai_news_sources as src

RSS = """<?xml version="1.0"?><rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel>
<title>t</title>
<item><title>Week 37</title><link>https://code.claude.com/docs/en/whats-new#week-37</link>
<pubDate>Wed, 15 Jan 2025 00:33:44 GMT</pubDate><description>short</description>
<content:encoded><![CDATA[<p>full body</p>]]></content:encoded></item>
<item><title>Tools for agents</title><link>https://Claude.dev/blog/tools/?utm=x</link>
<pubDate>Sat, 04 Jan 2025 18:00:00 GMT</pubDate><description>&lt;p&gt;sum&lt;/p&gt;</description></item>
</channel></rss>"""


@needs_deps
def test_canonical_dedups_variants():
    a = src.canonical("https://Claude.dev/blog/tools/?utm=x#top")
    b = src.canonical("https://claude.dev/blog/tools")
    assert a == b == "https://claude.dev/blog/tools"
    assert src.canonical("https://code.claude.com/docs/en/whats-new#week-37").endswith("#week-37")


@needs_deps
def test_rss_source_parses_items(monkeypatch):
    from zoneinfo import ZoneInfo
    monkeypatch.setattr(src, "LOCAL", ZoneInfo("America/Denver"))
    posts = src.list_posts({"id": "x", "method": "rss", "url": "u", "kind": "changelog"}, fetch=lambda u: RSS)
    assert [p["title"] for p in posts] == ["Week 37", "Tools for agents"]
    assert posts[0]["published"] == "2025-01-14"  # 00:33 UTC is the evening before in Denver
    assert posts[0]["content_html"] == "<p>full body</p>"
    assert posts[1]["url"] == "https://claude.dev/blog/tools"
    assert posts[1]["summary"] == "sum"
    assert all(p["kind"] == "changelog" for p in posts)


@needs_deps
def test_index_source_applies_regex_and_excludes():
    html = ('<a href="/research/agent-memory">x</a><a href="/research/team/alignment">t</a>'
            '<a href="/research/agent-memory">dup</a><a href="https://www.anthropic.com/research/evals">e</a>')
    s = {"id": "a", "method": "index", "url": "https://www.anthropic.com/research",
         "link": "^/research/(?!team/)[A-Za-z0-9-]+$"}
    urls = [p["url"] for p in src.list_posts(s, fetch=lambda u: html)]
    assert urls == ["https://www.anthropic.com/research/agent-memory", "https://www.anthropic.com/research/evals"]


@needs_deps
def test_source_error_isolated():
    def fetch(u):
        if u == "bad":
            raise src.FetchError(403, u)
        return RSS
    posts, errors = src.list_all([{"id": "b", "method": "rss", "url": "bad"},
                                  {"id": "g", "method": "rss", "url": "good"}], fetch)
    assert list(errors) == ["b"] and len(posts) == 2


# --- Task 3: extract and EPUB ----------------------------------------------------------

@needs_deps
def test_doc_name_safe():
    assert ext.doc_name("2025-01-15", 'Agents: "tools" / memory?') == "2025-01-15 - Agents - tools - memory"
    assert ext.doc_name("2025-01-15", "") == "2025-01-15 - Untitled"
    assert len(ext.doc_name("2025-01-15", "x" * 500)) <= 13 + 120


@needs_deps
def test_epub_is_valid_zip_with_mimetype_first(tmp_path):
    art = {"title": "Tools & agents", "published": "2025-01-15", "author": "A",
           "html": '<p>One<br>two</p><img src="/a.png"><img src="/b.svg"><pre><code>x < y</code></pre>',
           "partial": False}
    out = epub.build_epub(art, "https://ex.com/post", tmp_path / "a.epub", fetch_image=lambda u: b"PNG")
    with zipfile.ZipFile(out) as z:
        first = z.infolist()[0]
        assert first.filename == "mimetype" and first.compress_type == zipfile.ZIP_STORED
        assert z.read("mimetype") == b"application/epub+zip"
        assert "OEBPS/img1.png" in z.namelist()
        page = z.read("OEBPS/article.xhtml").decode()
    from lxml import etree
    etree.fromstring(page.encode())  # well-formed XHTML
    assert "b.svg" not in page and "Tools &amp; agents" in page


@needs_deps
def test_speech_text_omits_code_and_tables():
    t = ext.speech_text("<h2>Intro</h2><p>Use <code>tool_use</code> well.</p><pre>x=1</pre>"
                        "<table><tr><td>1</td></tr></table><p>End &amp; out.</p>")
    assert t == "Intro\n\nUse tool_use well.\n\nCode sample omitted.\n\nTable omitted.\n\nEnd & out."


@needs_deps
def test_extract_403_falls_back_partial():
    def fetch(u):
        raise src.FetchError(403, u)
    a = ext.extract({"url": "https://openai.com/index/x", "title": "New model", "published": "2025-01-15",
                     "summary": "A short summary.", "content_html": ""}, fetch)
    assert a["partial"] and a["title"] == "New model" and "A short summary." in a["html"]
    b = ext.extract({"url": "https://ex.com/y", "title": "T", "published": "2025-01-15",
                     "summary": "s", "content_html": "<p>Full text.</p>"}, fetch)
    assert not b["partial"] and b["text"] == "Full text."


# --- Task 4: filter --------------------------------------------------------------------

POSTS = [{"url": "u1", "source": "s", "title": "Agent memory"}, {"url": "u2", "source": "s", "title": "Webinar"}]


@needs_deps
def test_decide_parses_json():
    ans = 'Here:\n[{"url":"u1","keep":true,"reason":"agents"},{"url":"u2","keep":false,"reason":"event"},' \
          '{"url":"zz","keep":true,"reason":"not asked"}]'
    d = flt.decide(POSTS, "criteria", ask=lambda p: ans)
    assert d == {"u1": {"keep": True, "reason": "agents", "rank": 99},
                 "u2": {"keep": False, "reason": "event", "rank": 99}}


@needs_deps
def test_decide_malformed_returns_empty():
    assert flt.decide(POSTS, "c", ask=lambda p: "sorry, no") == {}
    assert flt.decide(POSTS, "c", ask=lambda p: '[{"url":"u1","keep":"yes"}]') == {}
    def boom(p):
        raise RuntimeError("claude exit 1")
    assert flt.decide(POSTS, "c", ask=boom) == {}


# --- Task 5: the run and the feed -------------------------------------------------------

import os
import time
from datetime import date

import ai_news_feed as feed

if HAS_DEPS:
    import ai_news

CFG = {"sources": [], "criteria": "c", "voice": "en-US-Chirp3-HD-Kore", "first_run_days": 14,
       "max_attempts": 3, "monthly_char_cap": 950000, "audio_keep_days": 30}


def _steps(posts, extract=None, decide=None, uploads=None):
    class S(ai_news.Steps):
        pass
    S.list_all = staticmethod(lambda sources: (posts, {}))
    S.extract = staticmethod(extract or (lambda p: {"title": p["title"], "published": p["published"],
                                                   "author": "", "html": "<p>Body.</p>", "text": "Body.",
                                                   "partial": False}))
    S.decide = staticmethod(decide or (lambda ps, c: {p["url"]: {"keep": True, "reason": "agents"} for p in ps}))
    S.upload = staticmethod(lambda path, folder: (uploads.append(path.name) if uploads is not None else None))
    S.ensure_folder = staticmethod(lambda f: None)

    def speak(text, voice, key, out):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"mp3")
        return len(text)
    S.speak = staticmethod(speak)
    S.duration = staticmethod(lambda f: 60)
    return S


def _post(url, published="2025-01-15", kind="article"):
    return {"url": url, "source": "s", "title": f"T {url}", "published": published, "summary": "",
            "content_html": "", "kind": kind}


@needs_deps
def test_run_skips_known_urls(tmp_path):
    log = tmp_path / "log.ndjson"
    log.write_text(json.dumps({"url": "u1", "status": "done"}) + "\n")
    uploads = []
    r = ai_news.process(CFG, {"GOOGLE_TTS_API_KEY": "k"}, _steps([_post("u1"), _post("u2"), _post("u2")],
                        uploads=uploads), work=tmp_path, log_path=log, now=date(2025, 1, 15))
    assert r["new"] == 1 and uploads == ["2025-01-15 - T u2.epub"]
    rec = [json.loads(l) for l in log.read_text().splitlines()][-1]
    assert rec["url"] == "u2" and rec["status"] == "done" and rec["mp3"]
    assert "episodes/" in (tmp_path / "feed" / "feed.xml").read_text()


@needs_deps
def test_old_posts_and_changelog_audio(tmp_path):
    log = tmp_path / "log.ndjson"
    r = ai_news.process(CFG, {"GOOGLE_TTS_API_KEY": "k"},
                        _steps([_post("old", "2024-12-01"), _post("cl", kind="changelog")]),
                        work=tmp_path, log_path=log, now=date(2025, 1, 15))
    recs = {x["url"]: x for x in r["records"]}
    assert recs["old"]["status"] == "skipped"
    assert recs["cl"]["status"] == "done" and recs["cl"]["mp3"] is None


@needs_deps
def test_failed_post_retried_twice_then_failed(tmp_path):
    log = tmp_path / "log.ndjson"

    def boom(p):
        raise RuntimeError("blocked")
    steps = _steps([_post("u")], extract=boom)
    for _ in range(2):
        r = ai_news.process(CFG, {}, steps, work=tmp_path, log_path=log, now=date(2025, 1, 15))
        assert r["retrying"] == ["u"] and not log.exists() or not log.read_text().strip()
    r = ai_news.process(CFG, {}, steps, work=tmp_path, log_path=log, now=date(2025, 1, 15))
    assert r["retrying"] == [] and json.loads(log.read_text())["status"] == "failed"


@needs_deps
def test_undecided_posts_are_not_logged(tmp_path):
    log = tmp_path / "log.ndjson"
    r = ai_news.process(CFG, {}, _steps([_post("u")], decide=lambda ps, c: {}), work=tmp_path,
                        log_path=log, now=date(2025, 1, 15))
    assert r["logged"] == 0


@needs_deps
def test_voice_budget_stops_audio(tmp_path):
    ai_news_tts_usage = tts.Usage(tmp_path / "tts-usage.json")
    ai_news_tts_usage.add("2025-01", 949_999)
    r = ai_news.process(CFG, {"GOOGLE_TTS_API_KEY": "k"}, _steps([_post("u")]), work=tmp_path,
                        log_path=tmp_path / "log.ndjson", now=date(2025, 1, 15))
    assert r["records"][0]["mp3"] is None and "budget" in r["records"][0]["mp3_error"]


def test_prune_drops_old_mp3s(tmp_path):
    old, new = tmp_path / "old.mp3", tmp_path / "new.mp3"
    old.write_bytes(b"x"), new.write_bytes(b"x")
    os.utime(old, (time.time() - 31 * 86400,) * 2)
    assert feed.prune(tmp_path, 30) == ["old.mp3"] and new.exists()


@needs_deps
def test_feed_xml_has_enclosures(tmp_path):
    out = feed.write_feed([{"file": "a.mp3", "title": "A & B", "published": "2025-01-15", "url": "https://x/y",
                            "source": "s", "seconds": 61, "bytes": 10}], tmp_path / "feed.xml", "https://h/p/pod/S")
    from lxml import etree
    root = etree.fromstring(out.read_bytes())
    enc = root.find(".//enclosure")
    assert enc.get("url") == "https://h/p/pod/S/episodes/a.mp3" and enc.get("type") == "audio/mpeg"
    assert root.find(".//item/title").text == "A & B"


@needs_deps
def test_each_post_is_logged_as_it_finishes(tmp_path):
    """A run stopped part way (systemd's time limit) keeps every post it finished."""
    log = tmp_path / "log.ndjson"
    steps = _steps([_post("u1"), _post("u2")])

    def upload(path, folder):
        if "u2" in path.name:
            raise SystemExit("killed")
    steps.upload = staticmethod(upload)
    try:
        ai_news.process(CFG, {"GOOGLE_TTS_API_KEY": "k"}, steps, work=tmp_path, log_path=log,
                        now=date(2025, 1, 15))
    except SystemExit:
        pass
    assert [json.loads(l)["url"] for l in log.read_text().splitlines()] == ["u1"]


@needs_deps
def test_an_existing_mp3_is_reused_not_spoken_again(tmp_path):
    f = tmp_path / "feed" / "episodes" / ai_news.episode_file("u")
    f.parent.mkdir(parents=True)
    f.write_bytes(b"mp3 from the killed run")
    steps = _steps([_post("u")])
    steps.speak = staticmethod(lambda *a: (_ for _ in ()).throw(AssertionError("spoken again")))
    r = ai_news.process(CFG, {"GOOGLE_TTS_API_KEY": "k"}, steps, work=tmp_path,
                        log_path=tmp_path / "log.ndjson", now=date(2025, 1, 15))
    assert r["records"][0]["mp3"] == f.name and f.read_bytes() == b"mp3 from the killed run"


@needs_deps
def test_a_source_with_audio_off_gets_an_epub_but_no_episode(tmp_path):
    post = {**_post("aws"), "audio": False}
    r = ai_news.process(CFG, {"GOOGLE_TTS_API_KEY": "k"}, _steps([post]), work=tmp_path,
                        log_path=tmp_path / "log.ndjson", now=date(2025, 1, 15))
    assert r["records"][0]["status"] == "done" and r["records"][0]["mp3"] is None


@needs_deps
def test_a_weekly_cap_keeps_the_best_ranked_and_files_them_in_the_source_folder(tmp_path):
    cfg = {**CFG, "sources": [{"id": "s", "weekly_cap": 2, "folder": "AI News/AWS"}]}
    log = tmp_path / "log.ndjson"
    log.write_text(json.dumps({"url": "old", "source": "s", "decision": "keep", "status": "done",
                               "decided": "2025-01-13"}) + "\n")  # Monday: one slot used
    asked = []

    def decide(ps, criteria):
        asked.append(criteria)
        return {p["url"]: {"keep": True, "reason": "r", "rank": int(p["url"][1])} for p in ps}
    uploads, folders = [], []
    steps = _steps([_post("u3", "2025-01-14"), _post("u1", "2025-01-14"), _post("u2", "2025-01-14")],
                   decide=decide, uploads=uploads)
    steps.ensure_folder = staticmethod(folders.append)
    steps.upload = staticmethod(lambda path, folder: uploads.append(folder))
    r = ai_news.process(cfg, {}, steps, work=tmp_path, log_path=log, now=date(2025, 1, 15))
    recs = {x["url"]: x for x in r["records"]}
    assert recs["u1"]["status"] == "done" and uploads == ["AI News/AWS"]
    assert recs["u2"]["status"] == recs["u3"]["status"] == "skipped"
    assert "weekly limit" in recs["u3"]["reason"] and "keep at most 1 post" in asked[0]
    assert folders == ["AI News", "AI News/AWS"]


@needs_deps
def test_posts_that_missed_audio_at_the_limit_are_read_aloud_when_the_month_resets(tmp_path):
    log = tmp_path / "log.ndjson"
    missed = {"url": "m", "source": "s", "title": "T m", "published": "2025-01-28", "decided": "2025-01-28",
              "decision": "keep", "status": "done", "partial": False, "mp3": None,
              "mp3_error": "monthly voice budget reached"}
    log.write_text(json.dumps(missed) + "\n")
    tts.Usage(tmp_path / "tts-usage.json").add("2025-01", 950_000)
    cfg = {**CFG, "sources": [{"id": "s"}]}
    r = ai_news.process(cfg, {"GOOGLE_TTS_API_KEY": "k"}, _steps([]), work=tmp_path, log_path=log,
                        now=date(2025, 1, 30))
    assert r["voiced_late"] == []  # still January: the allowance is used up
    r = ai_news.process(cfg, {"GOOGLE_TTS_API_KEY": "k"}, _steps([]), work=tmp_path, log_path=log,
                        now=date(2025, 2, 1))
    assert r["voiced_late"] == ["m"]
    assert ai_news.episode_file("m") in (tmp_path / "feed" / "feed.xml").read_text()
    r = ai_news.process(cfg, {"GOOGLE_TTS_API_KEY": "k"}, _steps([]), work=tmp_path, log_path=log,
                        now=date(2025, 2, 2))
    assert r["voiced_late"] == []  # once only
