"""The catch-up sensor's rescue guarantees, evaluated against an ephemeral instance.

The pure pieces (ingest_overdue, next_ingest_attempt) are unit-tested in
tests/unit/test_catchup_budget.py; here we prove the sensor wires them correctly —
fresh suffixed run_keys, and a window that excludes today until its ingest is overdue.
"""

import datetime as dt

import pytest

import dagster as dg
from quantpulse.data import calendar
from quantpulse.orchestration import catchup, definitions

TODAY = dt.date(2026, 7, 24)
MISSED = dt.date(2026, 7, 20)


@pytest.fixture
def patched(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """Freeze the clock and make XNYS miss one session; XJSE is fully covered."""
    windows: dict[str, dt.date] = {}

    def fake_trading_days(start: dt.date, end: dt.date, exchange: str | None = None) -> list:
        windows[exchange or "XNYS"] = end
        return [MISSED] if exchange == "XNYS" and end >= MISSED else []

    monkeypatch.setattr(definitions, "market_today", lambda exchange=None: TODAY)
    monkeypatch.setattr(calendar, "trading_days", fake_trading_days)
    monkeypatch.setattr(
        catchup, "missing_trading_days", lambda expected, exchange=None: list(expected)
    )
    return {"windows": windows, "monkeypatch": monkeypatch}


def _evaluate() -> dg.SensorResult:
    with dg.DagsterInstance.ephemeral() as instance:
        context = dg.build_sensor_context(instance=instance)
        return definitions.missed_partition_catchup_sensor(context)


def test_missed_day_gets_a_fresh_suffixed_run_key(patched: dict[str, object]) -> None:
    patched["monkeypatch"].setattr(catchup, "ingest_overdue", lambda now=None, exchange=None: True)  # type: ignore[attr-defined]
    result = _evaluate()
    assert isinstance(result, dg.SensorResult)
    (request,) = result.run_requests or []
    # Attempt-numbered key: with no prior history this is attempt 1. A fixed key here
    # would be deduplicated forever after any premature or failed attempt.
    assert request.run_key == f"catchup-XNYS-{MISSED}-1"
    assert request.partition_key == f"{MISSED}|XNYS"


def test_today_is_not_expected_until_its_ingest_is_overdue(patched: dict[str, object]) -> None:
    patched["monkeypatch"].setattr(catchup, "ingest_overdue", lambda now=None, exchange=None: False)  # type: ignore[attr-defined]
    _evaluate()
    windows = patched["windows"]
    # Pre-overdue, the expected window must end at *yesterday*: at 00:08 exchange time
    # the date has flipped but the session hasn't traded, and requesting it would burn
    # the rescue attempt on a day that does not exist yet.
    assert windows == {"XNYS": TODAY - dt.timedelta(days=1), "XJSE": TODAY - dt.timedelta(days=1)}


def test_exhausted_sessions_are_reported_as_exhausted_not_as_healthy(
    patched: dict[str, object],
) -> None:
    """Two silences that mean opposite things must not read the same.

    On 2026-08-11 an outage burned every session's attempts; the sensor then reported "no
    missed trading days in the lookback window" while two sessions sat unrecovered. The
    message a human reads has to distinguish "nothing to do" from "I have given up".
    """
    mp = patched["monkeypatch"]
    mp.setattr(catchup, "ingest_overdue", lambda now=None, exchange=None: True)  # type: ignore[attr-defined]
    mp.setattr(catchup, "next_ingest_attempt", lambda *a, **k: None)  # type: ignore[attr-defined]

    result = _evaluate()
    assert not (result.run_requests or [])
    message = str(result.skip_reason)
    assert "out of attempts" in message
    assert "retrying tomorrow" in message
    assert str(MISSED) in message, "name the sessions, so the gap is actionable"


def test_nothing_missing_still_reads_as_nothing_missing(patched: dict[str, object]) -> None:
    """The other branch must stay quiet and unalarming — a sensor that cries exhaustion
    on a healthy day trains the reader to ignore it."""
    mp = patched["monkeypatch"]
    mp.setattr(catchup, "ingest_overdue", lambda now=None, exchange=None: True)  # type: ignore[attr-defined]
    mp.setattr(catchup, "missing_trading_days", lambda expected, exchange=None: [])  # type: ignore[attr-defined]

    result = _evaluate()
    assert "no missed trading days" in str(result.skip_reason)
    assert "out of attempts" not in str(result.skip_reason)
