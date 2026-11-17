"""Tests for repo_sync.sync_with_upstream, the step every automated writer runs before
it pushes. Each test builds a bare origin and one or two clones in a temp folder, so
nothing touches the worktree's own branch."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import repo_sync  # noqa: E402


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=check)


def runner(repo: Path):
    """The shape every caller injects: run(*git_args) -> CompletedProcess."""
    return lambda *args: subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                                        timeout=60)


def commit_file(repo: Path, name: str, text: str, message: str) -> str:
    (repo / name).write_text(text)
    git(repo, "add", name)
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD").stdout.strip()


def _identity(repo: Path) -> None:
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "user.email", "test@localhost")
    git(repo, "config", "commit.gpgsign", "false")


def subjects(repo: Path) -> list[str]:
    return git(repo, "log", "--format=%s").stdout.splitlines()


@pytest.fixture
def clones(tmp_path: Path) -> tuple[Path, Path]:
    """Two clones of one bare origin, both level at the initial commit."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    a = tmp_path / "a"
    subprocess.run(["git", "clone", "-q", str(origin), str(a)], check=True, capture_output=True)
    _identity(a)
    git(a, "checkout", "-q", "-b", "main")
    commit_file(a, "shared.txt", "base\n", "initial")
    git(a, "push", "-q", "-u", "origin", "main")
    b = tmp_path / "b"
    subprocess.run(["git", "clone", "-q", str(origin), str(b)], check=True, capture_output=True)
    _identity(b)
    return a, b


def test_no_upstream_is_a_no_op(tmp_path: Path):
    repo = tmp_path / "alone"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    _identity(repo)
    before = commit_file(repo, "x.txt", "x\n", "only")
    assert repo_sync.sync_with_upstream(runner(repo), repo) == (True, "no upstream")
    assert git(repo, "rev-parse", "HEAD").stdout.strip() == before


def test_behind_fast_forwards(clones):
    a, b = clones
    theirs = commit_file(b, "b.txt", "b\n", "other: add b")
    git(b, "push", "-q")
    ok, detail = repo_sync.sync_with_upstream(runner(a), a)
    assert ok, detail
    assert git(a, "rev-parse", "HEAD").stdout.strip() == theirs


def test_local_commits_replay_on_top_and_then_push(clones):
    a, b = clones
    commit_file(b, "b.txt", "b\n", "other: add b")
    git(b, "push", "-q")
    commit_file(a, "a.txt", "a\n", "mine: add a")
    ok, detail = repo_sync.sync_with_upstream(runner(a), a)
    assert ok, detail
    assert subjects(a)[:2] == ["mine: add a", "other: add b"]
    assert git(a, "status", "--porcelain").stdout == ""
    git(a, "push", "-q")  # no longer rejected


def test_conflict_aborts_and_leaves_the_clone_as_it_was(clones):
    a, b = clones
    commit_file(b, "shared.txt", "theirs\n", "other: edit shared")
    git(b, "push", "-q")
    mine = commit_file(a, "shared.txt", "mine\n", "mine: edit shared")
    ok, detail = repo_sync.sync_with_upstream(runner(a), a)
    assert ok is False
    assert "CONFLICT" in detail or "conflict" in detail.lower()
    assert git(a, "rev-parse", "HEAD").stdout.strip() == mine
    assert (a / "shared.txt").read_text() == "mine\n"
    assert git(a, "status", "--porcelain").stdout == ""
    assert not repo_sync.rebase_in_progress(runner(a), a)


def test_uncommitted_edits_fast_forward_and_are_kept(clones):
    a, b = clones
    commit_file(a, "notes.txt", "draft\n", "mine: notes")
    git(a, "push", "-q")
    git(b, "pull", "-q", "--rebase")
    theirs = commit_file(b, "b.txt", "b\n", "other: add b")
    git(b, "push", "-q")
    (a / "notes.txt").write_text("draft, edited\n")  # uncommitted, and not in b's way
    ok, detail = repo_sync.sync_with_upstream(runner(a), a)
    assert ok, detail
    assert git(a, "rev-parse", "HEAD").stdout.strip() == theirs
    assert (a / "notes.txt").read_text() == "draft, edited\n"
    assert git(a, "stash", "list").stdout == ""


def test_uncommitted_edits_plus_local_commits_change_nothing(clones):
    a, b = clones
    commit_file(b, "b.txt", "b\n", "other: add b")
    git(b, "push", "-q")
    mine = commit_file(a, "a.txt", "a\n", "mine: add a")
    (a / "a.txt").write_text("a, edited\n")
    ok, detail = repo_sync.sync_with_upstream(runner(a), a)
    assert ok is False and "uncommitted" in detail
    assert git(a, "rev-parse", "HEAD").stdout.strip() == mine
    assert (a / "a.txt").read_text() == "a, edited\n"
    assert git(a, "stash", "list").stdout == ""


def test_someone_elses_rebase_is_left_alone(clones):
    a, b = clones
    commit_file(b, "shared.txt", "theirs\n", "other: edit shared")
    git(b, "push", "-q")
    commit_file(a, "shared.txt", "mine\n", "mine: edit shared")
    stopped = git(a, "pull", "--rebase", "--quiet", check=False)
    assert stopped.returncode != 0 and repo_sync.rebase_in_progress(runner(a), a)
    ok, detail = repo_sync.sync_with_upstream(runner(a), a)
    assert ok is False and "rebase is in progress" in detail
    assert repo_sync.rebase_in_progress(runner(a), a)  # not aborted on its owner's behalf
    git(a, "rebase", "--abort")

