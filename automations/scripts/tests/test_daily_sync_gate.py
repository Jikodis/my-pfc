"""Tests for daily_sync_gate: when the hourly launch agent firing should do a real run."""

import socket

import daily_sync_gate as g

TODAY = "2025-01-02"
YESTERDAY_CLEAN = "2025-01-01 05:02:31 DONE ok=6 fail=0\n"
TIMEOUT_RUN = (
    "2025-01-02 05:11:40 RUN attempt 1\n"
    "2025-01-02 05:11:46 START trello sync\n"
    "Traceback (most recent call last):\n"
    "TimeoutError: The read operation timed out\n"
    "2025-01-02 05:56:29 FAIL trello sync (exit 1)\n"
    "2025-01-02 05:56:29 OK trello sync changed nothing\n"
    "2025-01-02 06:13:14 OK email reconcile\n"
    "2025-01-02 07:11:14 OK calendar cache\n"
    "2025-01-02 07:15:16 DONE ok=5 fail=1\n"
)


def test_a_fresh_day_runs_once_the_network_is_up():
    assert g.decide(YESTERDAY_CLEAN, TODAY, network_up=True) == (True, "run")


def test_no_network_waits():
    assert g.decide(YESTERDAY_CLEAN, TODAY, network_up=False) == (False, "no network")


def test_a_clean_finish_ends_the_day():
    log = YESTERDAY_CLEAN + "2025-01-02 05:00:02 RUN attempt 1\n2025-01-02 05:03:00 DONE ok=6 fail=0\n"
    assert g.decide(log, TODAY, network_up=True) == (False, "already finished today with no failures")


def test_a_run_with_a_failed_step_is_tried_again():
    assert g.decide(TIMEOUT_RUN, TODAY, network_up=True) == (True, "run")


def test_the_latest_done_line_decides():
    log = TIMEOUT_RUN + "2025-01-02 08:00:03 RUN attempt 2\n2025-01-02 08:00:20 DONE ok=6 fail=0\n"
    assert g.decide(log, TODAY, network_up=True)[0] is False


def test_it_stops_after_three_attempts():
    log = "".join(f"2025-01-02 0{h}:00:02 RUN attempt {n}\n2025-01-02 0{h}:01:00 DONE ok=5 fail=1\n"
                  for n, h in ((1, 5), (2, 6), (3, 7)))
    assert g.decide(log, TODAY, network_up=True) == (False, "already tried 3 times today")


def test_a_guard_skip_does_not_use_up_an_attempt():
    # A dirty tree or a busy lock ends the run before `RUN attempt` is logged.
    log = "".join(f"2025-01-02 {h:02d}:00:01 FAIL dirty tree, skipped\n2025-01-02 {h:02d}:00:01 DONE ok=0 fail=1\n"
                  for h in range(5, 12))
    assert g.decide(log, TODAY, network_up=True) == (True, "run")


def test_steps_ok_names_only_todays_ok_lines():
    lines = g.todays_lines(YESTERDAY_CLEAN + "2025-01-01 05:00:17 OK trello sync\n" + TIMEOUT_RUN, TODAY)
    assert g.steps_ok(lines) == {"trello sync changed nothing", "email reconcile", "calendar cache"}
    assert "trello sync" not in g.steps_ok(lines)


def test_untimestamped_output_is_ignored():
    lines = g.todays_lines("OK trello sync\n| DONE ok=9 fail=0 |\n", TODAY)
    assert lines == []


def test_network_up_is_false_when_a_host_refuses(monkeypatch):
    def refuse(addr, timeout):
        raise OSError("unreachable")
    monkeypatch.setattr(socket, "create_connection", refuse)
    assert g.network_up() is False


def test_cli_logs_the_wait_once_a_day(tmp_path, monkeypatch):
    log = tmp_path / "sync.log"
    monkeypatch.setenv("PFC_DAILY_SYNC_LOG", str(log))
    monkeypatch.setattr(g, "network_up", lambda: False)
    assert g.main(["should-run"]) == 1
    assert g.main(["should-run"]) == 1
    assert log.read_text().count("WAIT no network") == 1


def test_cli_begin_numbers_the_attempts_and_step_done_reads_them(tmp_path, monkeypatch):
    log = tmp_path / "sync.log"
    monkeypatch.setenv("PFC_DAILY_SYNC_LOG", str(log))
    g.main(["begin"])
    g.main(["begin"])
    assert [l.split(" ", 2)[2] for l in log.read_text().splitlines()] == ["RUN attempt 1", "RUN attempt 2"]
    g._append(log, "OK calendar cache")
    assert g.main(["step-done", "calendar cache"]) == 0
    assert g.main(["step-done", "never ran"]) == 1
