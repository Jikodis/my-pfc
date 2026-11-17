#!/usr/bin/env python3
"""One NDJSON file, rewritten so that only the lines that changed change.

Both writers that rewrite data files in place use it: the web UI's writer
(`web_write.py`) and the Trello sync (`trello_writeback.py`). Existing lines keep
their exact bytes (older lines may mix `jq -c` and `json.dumps` spacing), so a
commit's diff shows the record that changed and nothing else. A changed or new line is written the way `jq -c` writes it. A write goes through a
temp file in the same folder and `os.replace`, so a reader never sees half a file,
and it refuses when the file on disk is no longer the one that was read.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def compact(record: dict) -> str:
    """One record the way `jq -c` writes it."""
    return json.dumps(record, ensure_ascii=False, separators=(",", ":"))


class ChangedUnderneath(Exception):
    """The file on disk changed after it was read; nothing was written to it."""

    def __init__(self, label: str):
        super().__init__(f"{label} changed after it was read")
        self.label = label


class NdjsonFile:
    """Read once; change `records` in place or append to it; `write()` the result.

    Records are matched to lines by position, which is how every caller uses it:
    records are changed in place or added at the end, never reordered. A record is
    removed only through `remove_at`, which drops its line with it.
    """

    def __init__(self, path: Path | str, label: str | None = None):
        self.path = Path(path)
        self.label = label or self.path.name
        self.existed = self.path.exists()
        self.text = self.path.read_text(encoding="utf-8") if self.existed else ""
        self.lines = self.text.splitlines()
        self.records = [json.loads(line) for line in self.lines if line.strip()]
        self.original = json.loads(json.dumps(self.records))
        self.removed = 0

    def remove_at(self, index: int) -> None:
        """Remove the record at `index` and the line it came from; every other line keeps its bytes."""
        seen = -1
        for pos, line in enumerate(self.lines):
            if line.strip():
                seen += 1
                if seen == index:
                    del self.lines[pos]
                    break
        else:
            raise IndexError(index)
        del self.records[index]
        del self.original[index]
        self.removed += 1

    def render(self) -> str:
        out, index = [], 0
        for line in self.lines:
            if not line.strip():
                out.append(line)
                continue
            if index >= len(self.records):
                break
            record = self.records[index]
            out.append(line if record == self.original[index] else compact(record))
            index += 1
        out.extend(compact(r) for r in self.records[index:])
        return "".join(line + "\n" for line in out)

    def changed(self) -> bool:
        return self.removed > 0 or self.records != self.original

    def unchanged_on_disk(self) -> bool:
        """True while the file on disk still holds exactly what was read."""
        if not self.path.exists():
            return not self.existed
        return self.existed and self.path.read_text(encoding="utf-8") == self.text

    def write(self) -> None:
        """Temp file, a last check that nobody wrote the file since it was read, then `os.replace`."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(self.render())
                fh.flush()
                os.fsync(fh.fileno())
            if self.existed:
                os.chmod(tmp, self.path.stat().st_mode & 0o777)
            if not self.unchanged_on_disk():
                raise ChangedUnderneath(self.label)
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise


def rewrite(path: Path | str, records: list[dict]) -> None:
    """Write `records` to `path`, keeping the bytes of every line whose record is unchanged.

    The file is re-read here, at write time, as the original the records are compared
    against. A line appended by someone else between the caller's own read and this call
    is therefore not caught: it is simply dropped from the result. A caller that must
    not lose such a line should hold an `NdjsonFile` from its own read and call `write()`.
    """
    f = NdjsonFile(path)
    f.records = records
    f.write()


def append(path: Path | str, record: dict) -> None:
    with Path(path).open("a", encoding="utf-8") as fh:
        fh.write(compact(record) + "\n")
