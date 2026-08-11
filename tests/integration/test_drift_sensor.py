"""The retrain sensor reads drift per market and remembers per market.

Written after the fact: the per-market rewrite shipped with no test at all, which is the
same asymmetry that produced the bug it fixed — the calculation got tests, the thing
consuming the calculation did not. A sensor that silently stops firing looks exactly like
a system with no drift.
"""

import datetime as dt
import json

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

import dagster as dg
from quantpulse.db import DriftMetric
from quantpulse.orchestration.definitions import drift_retrain_sensor

pytestmark = pytest.mark.integration

TODAY = dt.date(2026, 8, 11)


@pytest.fixture(autouse=True)
def wired(db_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    import quantpulse.db as db

    monkeypatch.setattr(db, "get_session", lambda: Session(db_engine))


def _record(session: Session, exchange: str, share: float, drifted: bool, day: dt.date) -> None:
    session.add(
        DriftMetric(
            date=day,
            exchange=exchange,
            feature_version="v1",
            metric_name="share_drifted",
            value=share,
            drifted=drifted,
        )
    )


def _evaluate(cursor: str | None = None) -> dg.SensorResult:
    with dg.DagsterInstance.ephemeral() as instance:
        return drift_retrain_sensor(dg.build_sensor_context(instance=instance, cursor=cursor))


def test_only_the_drifting_market_is_retrained(db_engine: Engine) -> None:
    """The reason this is per market: retraining a calm market on another's drift spends
    an hour of compute to replace a champion for no reason."""
    with Session(db_engine) as session:
        _record(session, "XJSE", 0.45, True, TODAY)
        _record(session, "XNYS", 0.05, False, TODAY)
        session.commit()

    result = _evaluate()
    (request,) = result.run_requests or []
    assert request.tags["exchange"] == "XJSE"
    assert request.run_key == f"drift-retrain-XJSE-{TODAY}"


def test_both_markets_drifting_gives_two_runs(db_engine: Engine) -> None:
    with Session(db_engine) as session:
        _record(session, "XJSE", 0.45, True, TODAY)
        _record(session, "XNYS", 0.51, True, TODAY)
        session.commit()

    result = _evaluate()
    assert {r.tags["exchange"] for r in result.run_requests or []} == {"XJSE", "XNYS"}


def test_a_market_already_retrained_does_not_fire_again(db_engine: Engine) -> None:
    with Session(db_engine) as session:
        _record(session, "XJSE", 0.45, True, TODAY)
        session.commit()

    assert not (_evaluate(cursor=json.dumps({"XJSE": str(TODAY)})).run_requests or [])


def test_one_markets_cursor_cannot_lock_out_the_other(db_engine: Engine) -> None:
    """The bug a single shared cursor would reintroduce: a JSE retrain recorded yesterday
    silently swallowing today's NYSE trigger, with nothing to show it happened."""
    with Session(db_engine) as session:
        _record(session, "XJSE", 0.45, True, TODAY)
        _record(session, "XNYS", 0.51, True, TODAY)
        session.commit()

    result = _evaluate(cursor=json.dumps({"XJSE": str(TODAY)}))
    (request,) = result.run_requests or []
    assert request.tags["exchange"] == "XNYS"
    # The JSE entry must survive, or it fires again on the next tick.
    assert json.loads(result.cursor or "{}") == {"XJSE": str(TODAY), "XNYS": str(TODAY)}


def test_drift_below_the_threshold_is_a_skip(db_engine: Engine) -> None:
    with Session(db_engine) as session:
        _record(session, "XJSE", 0.10, False, TODAY)
        _record(session, "XNYS", 0.05, False, TODAY)
        session.commit()

    result = _evaluate()
    assert not (result.run_requests or [])
    assert result.skip_reason is not None


def test_only_the_newest_reading_counts(db_engine: Engine) -> None:
    """Yesterday's drift is not a reason to retrain today; the sensor takes the latest
    row per market, not any row that ever crossed the line."""
    with Session(db_engine) as session:
        _record(session, "XNYS", 0.60, True, TODAY - dt.timedelta(days=1))
        _record(session, "XNYS", 0.05, False, TODAY)
        session.commit()

    assert not (_evaluate().run_requests or [])


def test_pooled_legacy_rows_are_invisible(db_engine: Engine) -> None:
    """Rows written before drift was per-market are stamped POOLED. They measured both
    markets mixed together, so they must never trigger a retrain of either."""
    with Session(db_engine) as session:
        _record(session, "POOLED", 0.90, True, TODAY)
        session.commit()

    assert not (_evaluate().run_requests or [])


# --- option_snapshot_repair_sensor: the other Tier 1 sensor ---
#
# `summarize_capture_runs` beneath it is well tested; the wiring is not. The wiring is
# what decides whether the one irreplaceable dataset gets captured tonight, and its
# failure mode is a skip — indistinguishable from "nothing needed doing".


def test_capture_sensor_stands_down_before_the_close(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pre-market IV is ~2% against ~33% post-close. Capturing early does not merely waste
    a run, it writes junk into a table that cannot be refetched."""
    from quantpulse.orchestration import catchup, definitions

    monkeypatch.setattr(catchup, "is_post_close", lambda *a, **k: False)
    with dg.DagsterInstance.ephemeral() as instance:
        result = definitions.option_snapshot_repair_sensor(
            dg.build_sensor_context(instance=instance)
        )
    assert not (result.run_requests or [])
    assert "before the close" in str(result.skip_reason)


def test_capture_sensor_skips_when_today_is_already_complete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from quantpulse.orchestration import catchup, definitions

    monkeypatch.setattr(catchup, "is_post_close", lambda *a, **k: True)
    monkeypatch.setattr(catchup, "option_snapshot_incomplete", lambda *a, **k: None)
    with dg.DagsterInstance.ephemeral() as instance:
        result = definitions.option_snapshot_repair_sensor(
            dg.build_sensor_context(instance=instance)
        )
    assert not (result.run_requests or [])
    assert "already complete" in str(result.skip_reason)


def test_capture_sensor_requests_a_run_when_the_day_is_thin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing or partial snapshot post-close must produce a request with a fresh
    run_key — Dagster deduplicates keys forever, so a reused one would silently vanish."""
    from quantpulse.orchestration import catchup, definitions

    monkeypatch.setattr(catchup, "is_post_close", lambda *a, **k: True)
    monkeypatch.setattr(catchup, "option_snapshot_incomplete", lambda *a, **k: 0.4)
    with dg.DagsterInstance.ephemeral() as instance:
        result = definitions.option_snapshot_repair_sensor(
            dg.build_sensor_context(instance=instance)
        )
    (request,) = result.run_requests or []
    assert request.run_key.startswith("option-snapshot-")
    assert request.run_key.endswith("-1"), "first attempt of the day"


def test_capture_sensor_stops_after_the_daily_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    """A feed that is genuinely down must not be retried all evening. The budget counts
    runs that reached the vendor, so three executed attempts close the day."""
    from quantpulse.orchestration import catchup, definitions

    monkeypatch.setattr(catchup, "is_post_close", lambda *a, **k: True)
    monkeypatch.setattr(catchup, "option_snapshot_incomplete", lambda *a, **k: 0.5)
    monkeypatch.setattr(
        catchup,
        "summarize_capture_runs",
        lambda runs: (False, definitions.MAX_OPTION_REPAIRS_PER_DAY),
    )
    with dg.DagsterInstance.ephemeral() as instance:
        result = definitions.option_snapshot_repair_sensor(
            dg.build_sensor_context(instance=instance)
        )
    assert not (result.run_requests or [])
    assert "reached the feed" in str(result.skip_reason)


def test_capture_sensor_will_not_run_two_captures_at_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """A snapshot is ~500 network calls over ten minutes; a second one racing it would
    double the vendor load for no extra coverage."""
    from quantpulse.orchestration import catchup, definitions

    monkeypatch.setattr(catchup, "is_post_close", lambda *a, **k: True)
    monkeypatch.setattr(catchup, "option_snapshot_incomplete", lambda *a, **k: 0.5)
    monkeypatch.setattr(catchup, "summarize_capture_runs", lambda runs: (True, 1))
    with dg.DagsterInstance.ephemeral() as instance:
        result = definitions.option_snapshot_repair_sensor(
            dg.build_sensor_context(instance=instance)
        )
    assert not (result.run_requests or [])
    assert "in flight" in str(result.skip_reason)
