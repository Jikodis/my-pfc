#!/usr/bin/env python3
"""Read pen strokes out of a reMarkable document and draw them over the page image.

    python3 automations/scripts/remarkable_lines.py DOC.zip BASE.png OUT.png

`rmapi get` downloads a document as a zip: `<id>.content`, `<id>.metadata`, and one
`<id>/<page-id>.rm` file per page that has ink. Those `.rm` files are the v6 "lines"
format the Paper Pro writes; `rmapi geta` cannot render them for every document, so
this file reads them itself. Only what reading marks needs is parsed: each stroke's
tool, colour and points. Text boxes, highlights of PDF text, layers and erasures that
leave tombstones are skipped; an erased stroke is gone from the file once the
tablet compacts it, and one still on file only costs a stray line in the image.

Format (the block layout `rmscene` documents): a 43-byte header, then blocks. Each
block is `uint32 length, uint8 0, uint8 min_version, uint8 current_version, uint8
type` followed by `length` bytes. Type 0x05 is a line item. Inside a block, values
are tagged: a varuint whose low 4 bits give the kind (0x1 one byte, 0x4 four bytes,
0x8 eight bytes, 0xC a length-prefixed sub-block, 0xF an id) and whose high bits give
the field index.

Page coordinates: x runs from the page's centre line, y from its top, in the
tablet's own units. `RM_WIDTH` units span the page width: 1620 on the Paper Pro (x from -810
to +810); a reMarkable 2 uses 1404 (set PFC_RM_WIDTH).
The page image is scaled to that width, which matches a 3:4 PDF shown full width.
"""

import io
import json
import os
import struct
import sys
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw

HEADER = b"reMarkable .lines file, version=6"
LINE_BLOCK = 0x05
ERASERS = {6, 8}  # eraser and erase-area tools
HIGHLIGHTERS = {5, 18}
RM_WIDTH = float(os.environ.get("PFC_RM_WIDTH", "1620"))

# The tablet's colour ids (Paper Pro adds the higher ones). Drawn strong enough for
# Claude to see on the page image, whatever pen colour was used.
COLOURS = {0: "#000000", 1: "#555555", 2: "#999999", 3: "#d4a300", 4: "#2e8b2e", 5: "#d63384",
           6: "#1f5fd6", 7: "#d62828", 8: "#555555", 9: "#d4a300", 10: "#2e8b2e", 11: "#0aa5b5",
           12: "#b5179e", 13: "#d4a300"}


class _Reader:
    def __init__(self, data):
        self.b = io.BytesIO(data)
        self.end = len(data)

    def pos(self):
        return self.b.tell()

    def left(self, limit):
        return limit - self.b.tell()

    def u8(self):
        return self.b.read(1)[0]

    def u16(self):
        return struct.unpack("<H", self.b.read(2))[0]

    def u32(self):
        return struct.unpack("<I", self.b.read(4))[0]

    def f32(self):
        return struct.unpack("<f", self.b.read(4))[0]

    def f64(self):
        return struct.unpack("<d", self.b.read(8))[0]

    def varuint(self):
        shift = result = 0
        while True:
            byte = self.u8()
            result |= (byte & 0x7F) << shift
            if not byte & 0x80:
                return result
            shift += 7

    def tag(self):
        x = self.varuint()
        return x >> 4, x & 0xF

    def peek_tag(self):
        at = self.pos()
        try:
            return self.tag()
        except (IndexError, struct.error):
            return None
        finally:
            self.b.seek(at)

    def crdt_id(self):
        return self.u8(), self.varuint()

    def skip_value(self, kind):
        if kind == 0x1:
            self.b.seek(1, 1)
        elif kind == 0x4:
            self.b.seek(4, 1)
        elif kind == 0x8:
            self.b.seek(8, 1)
        elif kind == 0xC:
            self.b.seek(self.u32(), 1)
        elif kind == 0xF:
            self.crdt_id()
        else:
            raise ValueError(f"unknown tag kind {kind:#x}")


def _read_line(r, version, limit):
    """One line item's value (the sub-block after the item type byte)."""
    fields = {}
    points = []
    while r.left(limit) > 0:
        index, kind = r.tag()
        if index == 5 and kind == 0xC:
            length = r.u32()
            size = 14 if version >= 2 else 24
            for _ in range(length // size):
                x, y = r.f32(), r.f32()
                if size == 14:
                    r.b.seek(6, 1)  # speed u16, width u16, direction u8, pressure u8
                else:
                    r.b.seek(16, 1)
                points.append((x, y))
            r.b.seek(length % size, 1)
        elif index in (1, 2, 8) and kind == 0x4:
            fields[index] = r.u32()  # 8: the Paper Pro's exact ARGB colour
        else:
            r.skip_value(kind)
    argb = fields.get(8)
    rgb = f"#{argb & 0xFFFFFF:06x}" if argb else None
    return {"tool": fields.get(1, 0), "colour": fields.get(2, 0), "rgb": rgb, "points": points}


def read_strokes(data):
    """Every pen stroke in one v6 `.rm` file: [{tool, colour, points: [(x, y)]}]."""
    if not data.startswith(HEADER):
        raise ValueError("not a v6 reMarkable lines file")
    r = _Reader(data)
    r.b.seek(43)
    strokes = []
    while r.left(r.end) >= 8:
        length = r.u32()
        r.u8()
        r.u8()  # min version
        version = r.u8()
        btype = r.u8()
        start = r.pos()
        block_end = start + length
        if btype == LINE_BLOCK:
            try:
                stroke = _read_line_block(r, version, block_end)
                if stroke and stroke["points"] and stroke["tool"] not in ERASERS:
                    strokes.append(stroke)
            except (ValueError, IndexError, struct.error):
                pass  # one unreadable block never hides the rest
        r.b.seek(block_end)
    return strokes


def _read_line_block(r, version, block_end):
    for _ in range(4):  # parent, item, left, right ids
        _, kind = r.tag()
        r.skip_value(kind)
    _, kind = r.tag()  # deleted length
    deleted = r.u32() if kind == 0x4 else 0
    if deleted or r.left(block_end) <= 0:
        return None
    index, kind = r.tag()
    if index != 6 or kind != 0xC:
        return None
    sub_len = r.u32()
    sub_end = r.pos() + sub_len
    item_type = r.u8()
    if item_type != 0x03:  # 3 = line
        return None
    return _read_line(r, version, sub_end)


def strokes_from_zip(zip_path):
    """All strokes on every page of a downloaded document, keyed by page id."""
    out = {}
    with zipfile.ZipFile(zip_path) as z:
        for name in z.namelist():
            if name.endswith(".rm"):
                out[Path(name).stem] = read_strokes(z.read(name))
    return out


def page_order(zip_path):
    """Page ids in document order, from the `.content` file (v1 `pages` or v2 `cPages`)."""
    with zipfile.ZipFile(zip_path) as z:
        content = next((n for n in z.namelist() if n.endswith(".content")), None)
        if not content:
            return []
        c = json.loads(z.read(content))
    if isinstance(c.get("cPages"), dict):
        return [p["id"] for p in c["cPages"].get("pages", []) if not (p.get("deleted") or {}).get("value")]
    return list(c.get("pages") or [])


def overlay(base_png, strokes, out_png, rm_width=RM_WIDTH):
    """Draw `strokes` over the page image; returns how many strokes were drawn."""
    im = Image.open(base_png).convert("RGBA")
    marks = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(marks)
    scale = im.width / rm_width
    cx = im.width / 2
    # Highlighters first and see-through, so ink drawn over them stays readable.
    for s in sorted(strokes, key=lambda s: s["tool"] not in HIGHLIGHTERS):
        pts = [(cx + x * scale, y * scale) for x, y in s["points"]]
        rgb = s.get("rgb") or COLOURS.get(s["colour"], "#000000")
        hi = s["tool"] in HIGHLIGHTERS
        fill = (*Image.new("RGB", (1, 1), rgb).getpixel((0, 0)), 110 if hi else 255)
        if len(pts) == 1:
            x, y = pts[0]
            d.ellipse((x - 3, y - 3, x + 3, y + 3), fill=fill)
        else:
            d.line(pts, fill=fill, width=28 if hi else 5, joint="curve")
    Image.alpha_composite(im, marks).convert("RGB").save(out_png)
    return len(strokes)


def main(argv=None):
    argv = argv or sys.argv[1:]
    if len(argv) != 3:
        print(__doc__.splitlines()[2].strip(), file=sys.stderr)
        return 2
    zip_path, base, out = argv
    order = page_order(zip_path)
    pages = strokes_from_zip(zip_path)
    first = order[0] if order and order[0] in pages else next(iter(pages), None)
    n = overlay(base, pages.get(first, []), out)
    print(json.dumps({"page": first, "strokes": n}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
