"""Tests for scripts/open-web-ui.sh, which the daily summary runs.

Every test puts a fake `open`, `curl`, and `uname` first on PATH, so no browser is
started and no server is asked. The script must exit 0 whatever happens: it is a
convenience at the end of a skill and may never fail the skill.
"""

import os
import stat
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "open-web-ui.sh"


@pytest.fixture
def fakes(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "open-calls.txt"

    def fake(name, body):
        path = bin_dir / name
        path.write_text("#!/bin/bash\n" + body + "\n")
        path.chmod(path.stat().st_mode | stat.S_IEXEC)

    fake("open", f'printf "%s\\n" "$*" >> "{calls}"')
    fake("curl", 'exit "${FAKE_CURL_EXIT:-0}"')
    fake("uname", 'echo "${FAKE_UNAME:-Darwin}"')
    return bin_dir, calls


def run(fakes, *args, **env):
    bin_dir, calls = fakes
    full = {"PATH": f"{bin_dir}:/usr/bin:/bin", **env}
    proc = subprocess.run(["/bin/bash", str(SCRIPT), *args], capture_output=True, text=True, env=full, timeout=20)
    opened = calls.read_text().splitlines() if calls.exists() else []
    return proc, opened


def test_opens_the_today_page_when_the_server_answers(fakes):
    proc, opened = run(fakes)
    assert proc.returncode == 0
    assert opened == ["http://127.0.0.1:4323/"]
    assert proc.stdout.strip() == "Opened http://127.0.0.1:4323/ in the browser."


def test_opens_a_named_page_behind_the_current_window(fakes):
    proc, opened = run(fakes, "--background", "/tasks")
    assert proc.returncode == 0
    assert opened == ["-g http://127.0.0.1:4323/tasks"]


def test_does_nothing_when_the_server_is_not_running(fakes):
    proc, opened = run(fakes, FAKE_CURL_EXIT="7")
    assert proc.returncode == 0
    assert opened == []
    assert proc.stdout.strip() == "Web UI not opened: nothing is answering at http://127.0.0.1:4323."


def test_does_nothing_inside_the_web_page_own_chat(fakes):
    proc, opened = run(fakes, PFC_WEB_CHAT="1")
    assert proc.returncode == 0
    assert opened == []
    assert proc.stdout.strip() == "Web UI not opened: this run was started from the web page."


def test_does_nothing_on_a_machine_that_is_not_macos(fakes):
    proc, opened = run(fakes, FAKE_UNAME="Linux")
    assert proc.returncode == 0
    assert opened == []
    assert proc.stdout.strip() == "Web UI not opened: it runs only on macOS."


@pytest.mark.parametrize("path", ["//evil.example", "http://evil.example", "/a/../x", "tasks", "/a b"])
def test_refuses_a_path_that_is_not_a_plain_page_path(fakes, path):
    proc, opened = run(fakes, path)
    assert proc.returncode == 0
    assert opened == []
    assert proc.stdout.strip() == "Web UI not opened: that is not a page path."
