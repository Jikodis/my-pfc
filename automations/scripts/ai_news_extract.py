"""AI News extraction: turn one post into clean article HTML and speakable text.

The article is kept as written: trafilatura pulls the body (headings, paragraphs,
lists, code, images) out of the page. A site that blocks fetching falls back to the
feed's full content, else to its summary, marked `partial` (no audio for those).
"""

import html as htmllib
import re

import trafilatura

from ai_news_sources import FetchError, http_get

UNSAFE = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')


def doc_name(published, title):
    """`YYYY-MM-DD - Title`, safe as a reMarkable document name."""
    clean = UNSAFE.sub(" - ", title or "Untitled")
    clean = re.sub(r"\s+", " ", clean)
    clean = re.sub(r"(\s*-\s*){2,}", " - ", clean).strip(" -.")[:120].rstrip(" -.")
    return f"{published} - {clean or 'Untitled'}"


def _from_page(page_html, url):
    body = trafilatura.extract(page_html, url=url, output_format="html", include_images=True,
                               include_formatting=True, include_links=False, include_tables=True,
                               favor_recall=True)
    meta = trafilatura.extract_metadata(page_html, default_url=url)
    return body, meta


def extract(post, fetch=http_get):
    """Article dict: title, published, author, html, text, partial."""
    title, published, author = post.get("title") or "", post.get("published"), ""
    body, partial = None, False
    try:
        page = fetch(post["url"].split("#")[0])
        body, meta = _from_page(page, post["url"])
        if meta:
            title = title or (meta.title or "")
            published = published or meta.date
            author = meta.author or ""
        if post.get("kind") == "changelog" and post.get("content_html"):
            body = None  # one page holds many weeks: use this week's feed entry
    except FetchError:
        pass
    if not body and post.get("content_html"):
        body = post["content_html"]
    if not body:
        summary = htmllib.escape(post.get("summary") or "")
        body = f"<p>{summary}</p>" if summary else ""
        partial = True
    return {"title": title.strip() or "Untitled", "published": published, "author": author,
            "html": body, "text": speech_text(body), "partial": partial}


def speech_text(body_html):
    """Plain text for the voice: code and tables are announced, not read."""
    s = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", body_html or "")
    s = re.sub(r"(?is)<pre\b.*?</pre>", "\n\nCode sample omitted.\n\n", s)
    s = re.sub(r"(?is)<table\b.*?</table>", "\n\nTable omitted.\n\n", s)
    s = re.sub(r"(?is)<code\b[^>]*>(.*?)</code>", r"\1", s)
    s = re.sub(r"(?is)<img\b[^>]*>", " ", s)
    s = re.sub(r"(?i)</(p|h[1-6]|li|div|blockquote|section)>|<br\s*/?>", "\n\n", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = htmllib.unescape(s)
    s = re.sub(r"[ \t\xa0]+", " ", s)
    s = re.sub(r"\s*\n\s*(\n\s*)+", "\n\n", s)
    return s.strip()
