"""Tests for with_write_lock.py: it runs the command under the lock, and skips (exit 0,
one log line) when the web writer's lock is already held."""

from __future__ import annotations

import fcntl
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "with_write_lock.py"


def run(tmp_path: Path, *command: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), "--lock", str(tmp_path / "w.lock"),
                           "--log", str(tmp_path / "log"), "--", *command],
                          capture_output=True, text=True)


def test_runs_command_and_passes_exit_code(tmp_path):
    ok = run(tmp_path, sys.executable, "-c", "print('hi')")
    assert ok.returncode == 0 and ok.stdout.strip() == "hi"
    assert run(tmp_path, sys.executable, "-c", "raise SystemExit(7)").returncode == 7


def test_busy_lock_skips_and_logs(tmp_path):
    marker = tmp_path / "ran"
    with open(tmp_path / "w.lock", "a") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = run(tmp_path, sys.executable, "-c", f"open({str(marker)!r}, 'w')")
    assert result.returncode == 0
    assert not marker.exists()
    assert "FAIL write lock busy, skipped" in (tmp_path / "log").read_text()
    assert (tmp_path / "log").read_text().rstrip().endswith("DONE ok=0 fail=1")


def test_lock_is_released_after_the_command(tmp_path):
    run(tmp_path, sys.executable, "-c", "pass")
    with open(tmp_path / "w.lock", "a") as again:
        fcntl.flock(again, fcntl.LOCK_EX | fcntl.LOCK_NB)


def test_hung_command_is_killed_with_its_children_and_logged(tmp_path):
    marker = tmp_path / "child-alive"
    # The command starts a grandchild that would write the marker after 3 seconds,
    # then hangs; the timeout must kill both, log FAIL, and exit 0.
    script = (
        "import subprocess, sys, time;"
        f"subprocess.Popen([sys.executable, '-c', \"import time; time.sleep(3); open({str(marker)!r}, 'w')\"]);"
        "time.sleep(60)"
    )
    env = {**__import__("os").environ, "PFC_LOCK_TIMEOUT_SECONDS": "1"}
    result = subprocess.run([sys.executable, str(SCRIPT), "--lock", str(tmp_path / "w.lock"),
                             "--log", str(tmp_path / "log"), "--", sys.executable, "-c", script],
                            capture_output=True, text=True, env=env, timeout=30)
    assert result.returncode == 0
    assert "FAIL command timed out after 1 seconds, killed" in (tmp_path / "log").read_text()
    __import__("time").sleep(3.5)
    assert not marker.exists()
    with open(tmp_path / "w.lock", "a") as again:
        fcntl.flock(again, fcntl.LOCK_EX | fcntl.LOCK_NB)
