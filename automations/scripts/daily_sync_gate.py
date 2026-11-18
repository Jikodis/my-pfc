#!/usr/bin/env python3
"""Decide whether scripts/daily-sync.sh should run now, and which steps are already done.

Why this exists: a launch agent that fires early in the morning can find the Mac asleep
on battery. macOS then runs the job inside short wakes with no usable network, so a run
can be skipped entirely (GitHub unreachable) or a step can time out, and nothing would
try again until the next morning. The agent therefore fires every hour from 5:00 AM to
10:00 PM, and this gate turns those firings into "run once the network works, retry
only what failed, then stay quiet until tomorrow":

    daily_sync_gate.py should-run [--force]   exit 0 = run now; exit 1 = not now (reason printed)
    daily_sync_gate.py step-done NAME         exit 0 = NAME already logged OK today
    daily_sync_gate.py begin                  log today's `RUN attempt N` line

`should-run` says no, and the script exits without writing a DONE line, when:
  - today's last DONE line has fail=0 (the day is finished);
  - today already has MAX_RUNS `RUN attempt` lines (a step that fails for a reason other
    than the network is not retried all day; each retry of a Claude step costs tokens);
  - github.com or api.trello.com cannot be reached (logged once a day as `WAIT no network`).
Because a waiting run writes no DONE line, the home page keeps showing the last real
result and calls it stale after about 30 hours (home_data.py).

All dates are the Mac's local date, the same clock daily-sync.sh stamps its lines with.
"""

from __future__ import annotations

import os
import re
import socket
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_LOG = "/tmp/pfc-daily-sync.log"
MAX_RUNS = 3
HOSTS = (("github.com", 443), ("api.trello.com", 443))
CONNECT_TIMEOUT_SECONDS = 8

_LINE = re.compile(r"^(\d{4}-\d{2}-\d{2}) \d{2}:\d{2}:\d{2} (.*)$")
_DONE = re.compile(r"^DONE ok=(\d+) fail=(\d+)\s*$")


def todays_lines(log_text: str, today: str) -> list[str]:
    """The message part of every timestamped line dated `today`, in order."""
    out = []
    for line in log_text.splitlines():
        m = _LINE.match(line)
        if m and m.group(1) == today:
            out.append(m.group(2))
    return out


def finished_clean(lines: list[str]) -> bool:
    """True when the day's last DONE line counted no failures."""
    for msg in reversed(lines):
        m = _DONE.match(msg)
        if m:
            return m.group(2) == "0"
    return False


def runs_started(lines: list[str]) -> int:
    return sum(1 for msg in lines if msg.startswith("RUN attempt "))


def steps_ok(lines: list[str]) -> set[str]:
    """Names of the steps that logged `OK <name>` today."""
    return {msg[3:] for msg in lines if msg.startswith("OK ")}


def decide(log_text: str, today: str, network_up: bool, max_runs: int = MAX_RUNS) -> tuple[bool, str]:
    """(run now?, reason). Checked in order: finished, out of attempts, network."""
    lines = todays_lines(log_text, today)
    if finished_clean(lines):
        return False, "already finished today with no failures"
    if runs_started(lines) >= max_runs:
        return False, f"already tried {max_runs} times today"
    if not network_up:
        return False, "no network"
    return True, "run"


def network_up(hosts=HOSTS, timeout: float = CONNECT_TIMEOUT_SECONDS) -> bool:
    """True when every host accepts a TCP connection. A sleeping Mac's wake has none."""
    for host, port in hosts:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                pass
        except OSError:
            return False
    return True


def _append(log: Path, message: str) -> None:
    with log.open("a") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {message}\n")


def main(argv: list[str]) -> int:
    log = Path(os.environ.get("PFC_DAILY_SYNC_LOG", DEFAULT_LOG))
    text = log.read_text() if log.exists() else ""
    today = datetime.now().strftime("%Y-%m-%d")
    lines = todays_lines(text, today)
    if argv[:1] == ["should-run"]:
        if "--force" in argv:
            return 0
        # The cheap checks first: the network is only tried when the answer depends on it.
        go, reason = decide(text, today, network_up=True)
        if go and not network_up():
            go, reason = False, "no network"
            if "WAIT no network" not in lines:
                _append(log, "WAIT no network")
        print(reason)
        return 0 if go else 1
    if argv[:1] == ["step-done"] and len(argv) == 2:
        return 0 if argv[1] in steps_ok(lines) else 1
    if argv == ["begin"]:
        _append(log, f"RUN attempt {runs_started(lines) + 1}")
        return 0
    print(__doc__.strip().splitlines()[0], file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
