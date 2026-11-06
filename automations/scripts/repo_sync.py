#!/usr/bin/env python3
"""Bring a clone's branch level with its upstream before it writes or pushes.

More than one clone can commit to this repo's `main` (a laptop and a server, say).
Git merges their work fine, but a writer that pushes without pulling first is
rejected whenever the other clone pushed in between, and its commits sit until
someone merges by hand. Every automated writer calls `sync_with_upstream` right
before it pushes, and the ones that read a file and write it back call it before
reading too, so they edit the newest copy.

The runner is injected, `run(*git_args) -> subprocess.CompletedProcess`, so each
caller keeps its own process handling (web_write runs git in a session of its own with
a time limit). The function never prompts, never stashes, and never leaves a rebase of
its own in progress:

- no upstream configured (tests, a fresh clone)       -> (True, "no upstream")
- a rebase is already in progress (someone's work)    -> (False, ...), nothing touched
- clean tree: `git pull --rebase`                      -> (True, ...); on a conflict the
                                                         rebase is aborted -> (False, git's
                                                         conflict line)
- uncommitted edits: `git fetch` + fast-forward only   -> (True, ...) when the branch has no
                                                         commits of its own and the edits are
                                                         not in the way; else (False, ...) and
                                                         the caller goes on with the copy it has

Uncommitted edits are never stashed on the user's behalf: an autostash that fails to
re-apply resets the working tree and parks the edits in `git stash`, which is the one
thing a live checkout must never have done to it.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

Runner = Callable[..., subprocess.CompletedProcess]

REBASE_IN_PROGRESS = ("a git rebase is in progress in the repo; finish it (git rebase --continue) "
                      "or abort it (git rebase --abort), then try again")


def rebase_in_progress(run: Runner, repo: Path) -> bool:
    """True when `.git/rebase-merge` or `.git/rebase-apply` exists."""
    for name in ("rebase-merge", "rebase-apply"):
        proc = run("rev-parse", "--git-path", name)
        if proc.returncode != 0:
            continue
        rel = Path(proc.stdout.strip())
        if (rel if rel.is_absolute() else repo / rel).exists():
            return True
    return False


def has_uncommitted_edits(run: Runner) -> bool:
    """Tracked files with changes, staged or not. Untracked files never block a sync."""
    proc = run("status", "--porcelain", "--untracked-files=no")
    return bool(proc.stdout.strip())


def sync_with_upstream(run: Runner, repo: Path) -> tuple[bool, str]:
    """Level the current branch with its upstream. Returns (synced, detail)."""
    # Mid-rebase HEAD is detached and has no upstream, so this check comes first.
    if rebase_in_progress(run, repo):
        return False, REBASE_IN_PROGRESS
    upstream = run("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
    if upstream.returncode != 0:
        return True, "no upstream"
    try:
        if has_uncommitted_edits(run):
            fetched = run("fetch", "--quiet")
            if fetched.returncode != 0:
                return False, _first_line(fetched) or "git fetch failed."
            ff = run("merge", "--ff-only", "--quiet", upstream.stdout.strip())
            if ff.returncode == 0:
                return True, "fast-forwarded"
            return False, "uncommitted edits in the working tree; " + (_first_line(ff) or "cannot fast-forward")
        pulled = run("pull", "--rebase", "--quiet")
    except subprocess.TimeoutExpired:
        _abort_own_rebase(run, repo)
        return False, "git timed out reaching origin."
    if pulled.returncode == 0:
        return True, "up to date"
    _abort_own_rebase(run, repo)
    return False, _first_line(pulled) or "git pull --rebase failed."


def _abort_own_rebase(run: Runner, repo: Path) -> None:
    """Only a rebase this call started can be in progress here; put the clone back."""
    if rebase_in_progress(run, repo):
        run("rebase", "--abort")


def _first_line(proc: subprocess.CompletedProcess) -> str:
    """git's conflict line when there is one, else its first non-empty line."""
    lines = [line.strip() for line in (proc.stderr + "\n" + proc.stdout).splitlines() if line.strip()]
    conflict = next((line for line in lines if "CONFLICT" in line), None)
    return conflict or (lines[0] if lines else "")
