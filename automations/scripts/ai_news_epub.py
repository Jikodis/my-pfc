"""AI News EPUB: one article as a minimal EPUB 3 the reMarkable reflows.

Images referenced by absolute URL are downloaded into the book (best effort); one
that fails is dropped. Stdlib only.
"""

import html as htmllib
import re
import urllib.request
import uuid
import zipfile
from pathlib import Path
from urllib.parse import urljoin

from ai_news_sources import UA

CSS = "body{font-family:serif;line-height:1.45}pre{white-space:pre-wrap;font-size:.85em}img{max-width:100%}" \
      ".src{font-size:.85em;color:#444}"
TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp"}


def _xhtml(body):
    """Re-serialize article HTML as well-formed XHTML (EPUB requires it), dropping what EPUB rejects."""
    from lxml import etree, html as lhtml
    if not (body or "").strip():
        return ""
    root = lhtml.fragment_fromstring(body, create_parent="div")
    for bad in root.xpath("//script|//style|//iframe|//svg|//form|//noscript"):
        bad.getparent().remove(bad)
    for el in root.iter():
        if isinstance(el.tag, str):
            for attr in [a for a in el.attrib if a not in ("src", "alt", "href", "colspan", "rowspan")]:
                del el.attrib[attr]
    return "".join(etree.tostring(child, method="xml", encoding="unicode") for child in root) \
        if len(root) else htmllib.escape(root.text or "")


def _images(body, base_url, fetch_image):
    files = {}

    def swap(m):
        src = htmllib.unescape(m.group(2))
        ext = Path(src.split("?")[0]).suffix.lower()
        if ext not in TYPES:
            return ""
        try:
            data = fetch_image(urljoin(base_url, src))
        except Exception:
            return ""
        name = f"img{len(files) + 1}{ext}"
        files[name] = data
        return f'{m.group(1)}"{name}"'

    body = re.sub(r'(?i)(<img\b[^>]*?\ssrc=)"([^"]+)"', swap, body)
    body = re.sub(r"(?i)<img\b(?![^>]*\ssrc=)[^>]*>", "", body)  # images whose download failed
    return body, files


def _fetch_image(url, limit=3_000_000):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read(limit + 1)
    if len(data) > limit:
        raise ValueError("image too large")
    return data


def build_epub(article, url, out, fetch_image=_fetch_image):
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    title = htmllib.escape(article["title"])
    body, images = _images(_xhtml(article["html"]), url, fetch_image)
    by = f" · {htmllib.escape(article['author'])}" if article.get("author") else ""
    partial = ("<p><em>Only the summary could be fetched. Full article at the link above.</em></p>"
               if article.get("partial") else "")
    page = (f'<?xml version="1.0" encoding="utf-8"?><!DOCTYPE html><html xmlns="http://www.w3.org/1999/xhtml">'
            f'<head><title>{title}</title><link rel="stylesheet" href="style.css"/></head><body>'
            f'<h1>{title}</h1><p class="src">{article.get("published") or ""}{by}<br/>{htmllib.escape(url)}</p>'
            f'{partial}{body}</body></html>')
    book_id = f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, url)}"
    manifest = "".join(f'<item id="i{i}" href="{n}" media-type="{TYPES[Path(n).suffix]}"/>'
                       for i, n in enumerate(images))
    opf = (f'<?xml version="1.0" encoding="utf-8"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
           f'unique-identifier="id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
           f'<dc:identifier id="id">{book_id}</dc:identifier><dc:title>{title}</dc:title><dc:language>en</dc:language>'
           f'<meta property="dcterms:modified">2025-01-01T00:00:00Z</meta></metadata><manifest>'
           f'<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
           f'<item id="a" href="article.xhtml" media-type="application/xhtml+xml"/>'
           f'<item id="css" href="style.css" media-type="text/css"/>{manifest}</manifest>'
           f'<spine><itemref idref="a"/></spine></package>')
    nav = (f'<?xml version="1.0" encoding="utf-8"?><!DOCTYPE html><html xmlns="http://www.w3.org/1999/xhtml" '
           f'xmlns:epub="http://www.idpf.org/2007/ops"><head><title>{title}</title></head><body>'
           f'<nav epub:type="toc"><ol><li><a href="article.xhtml">{title}</a></li></ol></nav></body></html>')
    container = ('<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                 '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
                 '</rootfiles></container>')
    with zipfile.ZipFile(out, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", container, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/content.opf", opf, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/nav.xhtml", nav, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/article.xhtml", page, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/style.css", CSS, compress_type=zipfile.ZIP_DEFLATED)
        for n, data in images.items():
            z.writestr(f"OEBPS/{n}", data, compress_type=zipfile.ZIP_DEFLATED)
    return out
