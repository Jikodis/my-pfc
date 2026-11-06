#!/usr/bin/env python3
"""Run a command while holding the web writer's lock.

    with_write_lock.py [--lock PATH] [--log PATH] -- command [args...]

Takes an exclusive, non-blocking flock on `data/.web-write.lock` (the lock web_write.py
holds for every change), runs the command, and exits with its exit code. When the lock
is busy it appends one timestamped line to the log, runs nothing, and exits 0, so a
scheduled job skips the run instead of racing the web writer. macOS has no flock CLI,
which is why this is a script. The lock is released when this process exits.

A command that runs past `PFC_LOCK_TIMEOUT_SECONDS` (default 1200, 20 minutes) is
killed with its whole process group, so a hung `claude -p` cannot hold the lock
forever and block every web write; that run logs one FAIL line and exits 0.
"""

from __future__ import annotations

import fcntl
import os
import signal
import subprocess
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_LOCK = Path(os.environ.get("PFC_REPO_ROOT") or Path(__file__).resolve().parents[2]) / "data" / ".web-write.lock"
DEFAULT_LOG = "/tmp/pfc-daily-sync.log"
DEFAULT_TIMEOUT_SECONDS = 20 * 60
KILL_GRACE_SECONDS = 10


def _log(log_path: Path, message: str) -> None:
    """One FAIL line, then the DONE summary line the web UI home page reads (a skipped
    or killed run is ok=0 fail=1)."""
    with open(log_path, "a") as log:
        now = f"{datetime.now():%Y-%m-%d %H:%M:%S}"
        log.write(f"{now} FAIL {message}\n{now} DONE ok=0 fail=1\n")


def _timeout() -> int:
    try:
        return max(1, int(os.environ.get("PFC_LOCK_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)))
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS


def _run(command: list[str], log_path: Path) -> int:
    """Run the command in its own process group; past the timeout, kill the group."""
    limit = _timeout()
    child = subprocess.Popen(command, start_new_session=True)
    try:
        return child.wait(timeout=limit)
    except subprocess.TimeoutExpired:
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(child.pid, sig)
            except ProcessLookupError:
                break
            try:
                child.wait(timeout=KILL_GRACE_SECONDS)
                if sig == signal.SIGTERM:
                    # The leader is gone; still kill whatever it left in the group.
                    os.killpg(child.pid, signal.SIGKILL)
                break
            except subprocess.TimeoutExpired:
                continue
            except ProcessLookupError:
                break
        _log(log_path, f"command timed out after {limit} seconds, killed")
        return 0


def main(argv: list[str]) -> int:
    lock_path, log_path = DEFAULT_LOCK, Path(DEFAULT_LOG)
    args = list(argv)
    while args and args[0] != "--":
        flag = args.pop(0)
        if flag in ("--lock", "--log") and args:
            value = Path(args.pop(0))
            if flag == "--lock":
                lock_path = value
            else:
                log_path = value
        else:
            print(f"Usage: with_write_lock.py [--lock PATH] [--log PATH] -- command [args...] (got {flag})", file=sys.stderr)
            return 2
    if not args or len(args) < 2:
        print("Usage: with_write_lock.py [--lock PATH] [--log PATH] -- command [args...]", file=sys.stderr)
        return 2
    command = args[1:]

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            _log(log_path, "write lock busy, skipped")
            return 0
        return _run(command, log_path)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
