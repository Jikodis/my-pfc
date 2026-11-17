"""Google Cloud Text-to-Speech for AI News episodes.

Splits article text into requests under Google's 5,000-byte limit, sends each to the
REST API with the API key in `GOOGLE_TTS_API_KEY`, joins the MP3 parts with ffmpeg,
and counts characters per calendar month so audio stops at `monthly_char_cap`
(default 950,000, just under the free monthly allowance for Chirp 3 HD voices; check
Google's current pricing).
"""

import base64
import json
import re
import subprocess
import tempfile
import urllib.request
from pathlib import Path

API = "https://texttospeech.googleapis.com/v1/text:synthesize"
MONTHLY_CAP = 950_000


def chunks(text, limit=4500):
    """Split text into pieces of at most `limit` UTF-8 bytes, at paragraph then sentence ends."""
    out, cur = [], ""

    def size(s):
        return len(s.encode("utf-8"))

    pieces = []
    for para in [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]:
        if size(para) <= limit:
            pieces.append(para)
            continue
        for sent in re.split(r"(?<=[.!?])\s+", para):
            while size(sent) > limit:  # a single run-on sentence: cut at a space
                cut = sent.encode("utf-8")[:limit].decode("utf-8", "ignore")
                cut = cut.rsplit(" ", 1)[0] if " " in cut else cut
                pieces.append(cut)
                sent = sent[len(cut):].lstrip()
            if sent:
                pieces.append(sent)
    for piece in pieces:
        joined = f"{cur}\n\n{piece}" if cur else piece
        if size(joined) <= limit:
            cur = joined
        else:
            out.append(cur)
            cur = piece
    if cur:
        out.append(cur)
    return out


class Usage:
    """Characters sent per calendar month, in a small JSON file."""

    def __init__(self, path):
        self.path = Path(path)

    def _load(self):
        try:
            return json.loads(self.path.read_text())
        except (FileNotFoundError, ValueError):
            return {}

    def used(self, month):
        return self._load().get(month, 0)

    def add(self, month, n):
        data = self._load()
        data[month] = data.get(month, 0) + n
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=1))

    def allowed(self, month, n, cap=MONTHLY_CAP):
        return self.used(month) + n <= cap


def _request(text, voice, key):
    body = json.dumps({
        "input": {"text": text},
        "voice": {"languageCode": voice.rsplit("-", 3)[0] if voice.count("-") >= 3 else "en-US", "name": voice},
        "audioConfig": {"audioEncoding": "MP3"},
    }).encode()
    req = urllib.request.Request(API, data=body, headers={"Content-Type": "application/json", "X-Goog-Api-Key": key})
    with urllib.request.urlopen(req, timeout=120) as r:
        return base64.b64decode(json.load(r)["audioContent"])


def synthesize(text, voice, key, out):
    """Speak `text` into the MP3 at `out`. Returns the number of characters sent."""
    parts = chunks(text)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        files = []
        for i, part in enumerate(parts):
            f = Path(tmp) / f"{i:04d}.mp3"
            f.write_bytes(_request(part, voice, key))
            files.append(f)
        if len(files) == 1:
            out.write_bytes(files[0].read_bytes())
        else:
            listing = Path(tmp) / "list.txt"
            listing.write_text("".join(f"file '{f}'\n" for f in files))
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
                            "-c", "copy", str(out)], check=True)
    return sum(len(p) for p in parts)


def duration_seconds(path):
    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True)
    try:
        return int(float(p.stdout.strip()))
    except ValueError:
        return 0
