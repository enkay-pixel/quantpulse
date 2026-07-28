"""Failure alerts round-trip through Postgres.

These were unit tests against a JSONL file until 2026-07-28, when two real ingest failures
were recorded correctly and still surfaced as an empty `/alerts`: the daemon wrote to a
path inside its own container that the API could not read and `compose up` erased. The log
now lives in the database both containers already share — which makes these integration
tests, and makes the cross-container path the thing actually under test.
"""

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from quantpulse.monitoring import alerts

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def alert_db(db_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Point the module's sessions at the disposable test database."""
    import quantpulse.db as db

    monkeypatch.setattr(db, "get_session", lambda: Session(db_engine))
    # Never fire a real desktop notification during tests.
    monkeypatch.setattr(alerts, "_notify_macos", lambda *a, **k: None)
    yield


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
    # A limit takes the newest N, still ordered oldest-first.
    assert [a["run_id"] for a in alerts.read_alerts(limit=2)] == ["run-3", "run-4"]


def test_log_is_trimmed_to_max(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(alerts, "MAX_ALERTS", 3)
    for i in range(6):
        alerts.record_failure("j", f"run-{i}", "e")
    got = alerts.read_alerts()
    assert len(got) == 3
    assert got[-1]["run_id"] == "run-5"  # the newest survive, not the oldest


def test_long_errors_are_truncated() -> None:
    """The column is 500 chars; an unbounded traceback must not fail the insert and
    thereby lose the alert about the failure it is describing."""
    alerts.record_failure("j", "r", "x" * 900)
    assert len(alerts.read_alerts()[0]["error"]) == 500


def test_timestamps_are_timezone_aware() -> None:
    alerts.record_failure("j", "r", "e")
    assert alerts.read_alerts()[0]["timestamp"].endswith(("+00:00", "Z"))


def test_a_broken_database_degrades_instead_of_masking_the_failure(
    db_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Recording an alert happens *because* a run already failed. If the alert write
    itself explodes, it must not replace the original failure with a database error."""
    with Session(db_engine) as session:
        session.execute(text("ALTER TABLE pipeline_alerts RENAME TO pipeline_alerts_hidden"))
        session.commit()
    try:
        alerts.record_failure("ingest_job", "run-x", "the real cause")  # must not raise
        assert alerts.read_alerts() == []  # and reading degrades rather than 500-ing
    finally:
        with Session(db_engine) as session:
            session.execute(text("ALTER TABLE pipeline_alerts_hidden RENAME TO pipeline_alerts"))
            session.commit()
