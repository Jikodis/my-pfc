"""AI News sources: list the posts on each blog in config/ai_news.yaml.

Two methods: `rss` (feedparser over the blog's feed) and `index` (collect links on the
blog's index page that match the source's `link` pattern; their title and date come
from the article page at extract time). One source failing never stops the others.
"""

import calendar
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import feedparser

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
LOCAL = ZoneInfo(os.environ.get("LOCAL_TZ", "America/Denver"))


class FetchError(Exception):
    def __init__(self, status, url):
        super().__init__(f"HTTP {status} for {url}")
        self.status = status


def http_get(url, timeout=30):
    """Return the body as text; raise FetchError on an HTTP error status."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode(r.headers.get_content_charset() or "utf-8", "replace")
    except urllib.error.HTTPError as e:
        raise FetchError(e.code, url) from None


def canonical(url):
    """One key per post: lower-case host, no query, no trailing slash, fragment only for changelog weeks."""
    parts = urlsplit(url.strip())
    frag = parts.fragment if re.fullmatch(r"week-\d+", parts.fragment or "") else ""
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme or "https", parts.netloc.lower(), path, "", frag))


def _local_date(struct):
    if not struct:
        return None
    return datetime.fromtimestamp(calendar.timegm(struct), timezone.utc).astimezone(LOCAL).strftime("%Y-%m-%d")


def _rss(source, fetch):
    feed = feedparser.parse(fetch(source["url"]))
    posts = []
    for e in feed.entries:
        if not e.get("link"):
            continue
        content = ""
        if e.get("content"):
            content = e.content[0].get("value", "")
        posts.append({
            "url": canonical(e.link),
            "source": source["id"],
            "title": (e.get("title") or "").strip(),
            "published": _local_date(e.get("published_parsed") or e.get("updated_parsed")),
            "summary": re.sub(r"<[^>]+>", " ", e.get("summary", "") or "").strip()[:1500],
            "content_html": content,
            "kind": source.get("kind", "article"), "audio": source.get("audio", True),
        })
    return posts


def _index(source, fetch):
    html = fetch(source["url"])
    pattern = re.compile(source["link"])
    seen, posts = set(), []
    for href in re.findall(r'href="([^"#?]+)"', html):
        path = urlsplit(href).path if href.startswith("http") else href
        if not pattern.search(path):
            continue
        url = canonical(urljoin(source["url"], path))
        if url in seen:
            continue
        seen.add(url)
        posts.append({"url": url, "source": source["id"], "title": "", "published": None,
                      "summary": "", "content_html": "", "kind": source.get("kind", "article"),
                      "audio": source.get("audio", True)})
    return posts


def list_posts(source, fetch=http_get):
    """Posts on one source, newest first as the site lists them."""
    method = {"rss": _rss, "index": _index}[source["method"]]
    return method(source, fetch)


def list_all(sources, fetch=http_get):
    """(posts, errors) across every source; errors maps source id to a message."""
    posts, errors = [], {}
    for s in sources:
        try:
            posts.extend(list_posts(s, fetch))
        except Exception as e:  # one broken site must not stop the others
            errors[s["id"]] = str(e)[:200]
    return posts, errors
