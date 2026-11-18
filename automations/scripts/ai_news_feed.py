"""AI News podcast feed: RSS 2.0 with one enclosure per MP3, and the 30-day pruning."""

import html as htmllib
import time
from email.utils import formatdate
from datetime import datetime
from pathlib import Path


def prune(episodes_dir, days=30, now=None):
    """Delete MP3s older than `days`. Returns the names removed."""
    now = now or time.time()
    gone = []
    for f in Path(episodes_dir).glob("*.mp3"):
        if now - f.stat().st_mtime > days * 86400:
            f.unlink()
            gone.append(f.name)
    return gone


def write_feed(episodes, out, base_url, site_url=None):
    """episodes: dicts {file, title, published (YYYY-MM-DD), url, source, seconds, bytes}, newest first.
    `base_url` is where the feed is served (`.../p/pod/<secret>`); `site_url` the channel link."""
    site = htmllib.escape(site_url or base_url.split("/p/pod/")[0] + "/")
    items = []
    for e in episodes:
        pub = formatdate(datetime.strptime(e["published"], "%Y-%m-%d").timestamp() + 6 * 3600, usegmt=True)
        title = htmllib.escape(e["title"])
        items.append(
            f"<item><title>{title}</title><guid isPermaLink=\"false\">{htmllib.escape(e['url'])}</guid>"
            f"<link>{htmllib.escape(e['url'])}</link><pubDate>{pub}</pubDate>"
            f"<description>{htmllib.escape(e['source'])}: {htmllib.escape(e['url'])}</description>"
            f"<enclosure url=\"{base_url}/episodes/{e['file']}\" length=\"{e['bytes']}\" type=\"audio/mpeg\"/>"
            f"<itunes:duration>{e['seconds']}</itunes:duration></item>")
    xml = ('<?xml version="1.0" encoding="utf-8"?>'
           '<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"><channel>'
           f'<title>AI News (private)</title><link>{site}</link>'
           '<description>Articles from followed AI blogs, read aloud. Private feed.</description>'
           '<language>en-us</language><itunes:block>Yes</itunes:block>'
           + "".join(items) + "</channel></rss>")
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(xml, encoding="utf-8")
    tmp.replace(out)
    return out
