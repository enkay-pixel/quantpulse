"""The late-bars sensor's wiring, evaluated against an ephemeral instance.

The DB-backed pieces (`rescore_candidate`) are tested against Postgres in
tests/integration/test_catchup.py and the attempt budget in tests/unit/test_rescore_attempt.py;
here we prove the sensor turns a candidate into one suffixed, tagged request.
"""

import datetime as dt

import pytest

import dagster as dg
from quantpulse.orchestration import catchup, definitions

DAY = dt.date(2026, 10, 23)
LATE = ["AAPL", "MSFT"]


def _evaluate(instance: dg.DagsterInstance) -> dg.SensorResult:
    return definitions.late_bars_rescore_sensor(dg.build_sensor_context(instance=instance))


def test_a_late_session_gets_one_tagged_request(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        catchup,
        "rescore_candidate",
        lambda exchange=None: (DAY, LATE) if exchange == "XNYS" else None,
    )
    with dg.DagsterInstance.ephemeral() as instance:
        result = _evaluate(instance)
    (request,) = result.run_requests or []
    # Attempt-numbered: a fixed key would be deduplicated forever after one failed pass.
    assert request.run_key == f"rescore-XNYS-{DAY}-1"
    assert request.tags[catchup.RESCORE_TAG] == f"XNYS|{DAY}"
    assert request.tags[catchup.UNSCORED_TAG] == "2"


def test_nothing_late_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(catchup, "rescore_candidate", lambda exchange=None: None)
    with dg.DagsterInstance.ephemeral() as instance:
        result = _evaluate(instance)
    assert not result.run_requests
    assert "no late, unscored listings" in str(result.skip_reason)


def test_a_spent_budget_is_reported_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        catchup,
        "rescore_candidate",
        lambda exchange=None: (DAY, LATE) if exchange == "XNYS" else None,
    )
    monkeypatch.setattr(catchup, "rescore_attempt", lambda unscored, runs: None)
    with dg.DagsterInstance.ephemeral() as instance:
        result = _evaluate(instance)
    assert not result.run_requests
    assert "XNYS 2026-10-23: 2 late listing(s) unscored, not re-scoring" in str(result.skip_reason)
