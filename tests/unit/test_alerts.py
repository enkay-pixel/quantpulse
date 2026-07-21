import json

import pytest

from quantpulse.monitoring import alerts


@pytest.fixture(autouse=True)
def alert_home(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("DAGSTER_HOME", str(tmp_path))
    # Never fire a real desktop notification during tests.
    monkeypatch.setattr(alerts, "_notify_macos", lambda *a, **k: None)


def test_no_alerts_when_nothing_failed() -> None:
    assert alerts.read_alerts() == []


def test_records_and_reads_back_a_failure() -> None:
    alerts.record_failure("process_job", "run-1", "yfinance timeout")
    got = alerts.read_alerts()
    assert len(got) == 1
    assert got[0]["job_name"] == "process_job"
    assert got[0]["error"] == "yfinance timeout"
    assert got[0]["timestamp"]


def test_alerts_accumulate_newest_last_and_respect_limit() -> None:
    for i in range(5):
        alerts.record_failure("ingest_job", f"run-{i}", f"boom {i}")
    assert alerts.read_alerts()[-1]["run_id"] == "run-4"
    assert [a["run_id"] for a in alerts.read_alerts(limit=2)] == ["run-3", "run-4"]


def test_log_is_trimmed_to_max(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(alerts, "MAX_ALERTS", 3)
    for i in range(6):
        alerts.record_failure("j", f"run-{i}", "e")
    assert len(alerts.read_alerts()) == 3


def test_long_errors_are_truncated() -> None:
    alerts.record_failure("j", "r", "x" * 900)
    assert len(alerts.read_alerts()[0]["error"]) == 500


def test_corrupt_log_degrades_to_empty() -> None:
    alerts.record_failure("j", "r", "e")
    alerts.alerts_path().write_text("{not json\n")
    assert alerts.read_alerts() == []


def test_written_records_are_valid_jsonl() -> None:
    alerts.record_failure("j", "r", "e")
    for line in alerts.alerts_path().read_text().splitlines():
        json.loads(line)
