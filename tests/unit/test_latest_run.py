"""`make status` flags a job only when its latest run reported a problem, so it must find that run.

It used to take the lines stamped with the log's last minute. A health check reported the stopped
paper book at 08:00 on 2026-11-07, appended a diagnosis at 08:04, and the status showed the job as
healthy for two days, because 08:04 was the last minute (incident 41).
"""

import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "latest-run.awk"


def latest_run(tmp_path: Path, log: str) -> list[str]:
    path = tmp_path / "job.log"
    path.write_text(log)
    out = subprocess.run(
        ["awk", "-f", str(SCRIPT), str(path)], capture_output=True, text=True, check=True
    )
    return out.stdout.splitlines()


def test_a_diagnosis_appended_minutes_later_keeps_the_problem_in_the_run(tmp_path: Path) -> None:
    run = latest_run(
        tmp_path,
        "2026-11-06 08:00:08 ok: 6/6 containers, no gaps, coverage nominal\n"
        "2026-11-07 08:00:05 PROBLEMS (1):\n"
        "2026-11-07 08:00:05   - 2 prediction dates have no portfolio snapshot\n"
        "2026-11-07 08:00:05 asking for a diagnosis...\n"
        "2026-11-07 08:04:42 --- diagnosis ---\n"
        "    ## Root cause: a bind-param overflow\n"
        "2026-11-07 08:04:42 --- end of diagnosis ---\n",
    )
    assert run[0] == "2026-11-07 08:00:05 PROBLEMS (1):"
    assert run[-1] == "2026-11-07 08:04:42 --- end of diagnosis ---"
    assert "    ## Root cause: a bind-param overflow" in run


def test_an_earlier_runs_problem_cleared_by_a_later_run_is_not_read(tmp_path: Path) -> None:
    run = latest_run(
        tmp_path,
        "2026-11-08 13:11:02 WARN: sleep disabled on battery (92%)\n"
        "2026-11-08 15:11:03 ok (SleepDisabled=1, battery=no)\n",
    )
    assert run == ["2026-11-08 15:11:03 ok (SleepDisabled=1, battery=no)"]


def test_runs_half_an_hour_apart_stay_separate(tmp_path: Path) -> None:
    """The most frequent job runs every 30 minutes."""
    run = latest_run(
        tmp_path,
        "2026-11-08 15:12:00 PROBLEMS (1):\n2026-11-08 15:42:00 ok: nothing new\n",
    )
    assert run == ["2026-11-08 15:42:00 ok: nothing new"]


def test_a_run_across_midnight_is_one_run(tmp_path: Path) -> None:
    run = latest_run(
        tmp_path,
        "2026-12-31 23:00:00 ok\n"
        "2026-12-31 23:58:00 PROBLEMS (1):\n"
        "2026-12-31 23:58:00   - something\n"
        "2027-01-01 00:03:00 --- end of diagnosis ---\n",
    )
    assert run[0] == "2026-12-31 23:58:00 PROBLEMS (1):"
    assert len(run) == 3


@pytest.mark.parametrize("log", ["", "no timestamps here\n"])
def test_a_log_without_a_stamped_line_has_no_run(tmp_path: Path, log: str) -> None:
    assert latest_run(tmp_path, log) == []
