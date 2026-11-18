#!/usr/bin/env python3
"""Git network steps for scripts/daily-sync.sh, done the way web_write.py does them.

    daily_sync_git.py sync    # bring the branch level with origin (repo_sync), exit 1 on failure
    daily_sync_git.py push    # sync, then push the write branch, exit 1 on failure

Reuses web_write's credential handling (PFC_PUSH_GH_USER), sync and push so the launch
agent pushes as the same GitHub account the web UI does. Prints one line saying why it failed.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import web_write  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) != 1 or argv[0] not in ("sync", "push"):
        print("Usage: daily_sync_git.py sync | push", file=sys.stderr)
        return 2
    if argv[0] == "push":
        ok, detail = web_write.push()
        print("pushed" if ok else (detail or "push failed"))
        return 0 if ok else 1
    with web_write.network_git() as (env, prefix):
        if env is None:
            print(web_write.NO_GH)
            return 1
        ok, detail = web_write.sync(env, prefix)
    print(detail)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
