"""NdjsonFile's last check before os.replace: a file written after it was read is left alone."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ndjson_file import ChangedUnderneath, NdjsonFile  # noqa: E402


def test_a_write_after_the_read_is_refused_and_the_file_is_left_alone(tmp_path):
    path = tmp_path / "tasks.ndjson"
    path.write_text('{"id":"a","status":"open"}\n')
    f = NdjsonFile(path, "tasks.ndjson")
    f.records[0]["status"] = "done"
    # Something else (a skill's jq write) replaces the file between the read and the write.
    someone_else = '{"id":"a","status":"open"}\n{"id":"b","status":"open"}\n'
    path.write_text(someone_else)
    with pytest.raises(ChangedUnderneath):
        f.write()
    assert path.read_text() == someone_else
    assert [p.name for p in tmp_path.iterdir()] == ["tasks.ndjson"]  # no temp file left behind


def test_an_untouched_file_is_written(tmp_path):
    path = tmp_path / "tasks.ndjson"
    path.write_text('{"id": "a", "status": "open"}\n')
    f = NdjsonFile(path)
    f.records[0]["status"] = "done"
    f.write()
    assert path.read_text() == '{"id":"a","status":"done"}\n'


def test_remove_at_drops_the_record_and_its_line_and_keeps_the_rest_byte_for_byte(tmp_path):
    path = tmp_path / "tasks.ndjson"
    path.write_text('{"id": "a"}\n\n{"id":"b"}\n{"id": "c"}\n')
    f = NdjsonFile(path, "tasks.ndjson")
    f.remove_at(1)
    assert f.changed()
    assert [r["id"] for r in f.records] == ["a", "c"]
    f.write()
    assert path.read_text() == '{"id": "a"}\n\n{"id": "c"}\n'
