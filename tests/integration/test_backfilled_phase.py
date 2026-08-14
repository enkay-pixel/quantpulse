"""A day scored by a champion promoted *after* it must not count as live evidence.

The scenario is an outage. The machine is off for a stretch; on return the catch-up sensor
backfills the prices and scoring fills the missing days — but if a retrain promoted a new
champion in the meantime, those days get scored by a model that was *trained on them*.
Nothing about the dates reveals it: they sit inside the live window, look out-of-sample,
and flatter the out-of-sample record.

`fct_portfolio_daily` therefore compares each day against the promotion date of the model
that actually scored it, and labels the mismatch 'backfilled'. Built against a real dbt
run, because the labelling lives in SQL and only SQL can prove it.
"""

import datetime as dt
import os
from collections.abc import Iterator
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import Engine, create_engine, make_url, text
from sqlalchemy.orm import Session

from quantpulse.data.ingest import BAR_COLUMNS, upsert_prices
from quantpulse.data.universe import UniverseEntry, sync_universe
from quantpulse.db import ModelRun, PortfolioSnapshot, Prediction

pytestmark = pytest.mark.integration

TRANSFORM_DIR = Path(__file__).parents[2] / "transform"
DATES = [d.date() for d in pd.bdate_range("2024-07-01", periods=10)]
V1_PROMOTED = DATES[2]  # live phase starts here
OUTAGE = DATES[5:8]  # days that went unscored while the machine was off
V2_PROMOTED = DATES[8]  # the retrain that happened before the backfill ran


def _dbt_build(db_url: str) -> None:
    from dbt.cli.main import dbtRunner

    url = make_url(db_url)
    env = {
        "DBT_HOST": url.host or "localhost",
        "DBT_PORT": str(url.port or 5432),
        "POSTGRES_USER": url.username or "quantpulse",
        "POSTGRES_PASSWORD": url.password or "quantpulse",
        "POSTGRES_DB": url.database or "market_test",
    }
    old = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    try:
        result = dbtRunner().invoke(
            ["build", "--project-dir", str(TRANSFORM_DIR), "--profiles-dir", str(TRANSFORM_DIR)]
        )
        if not result.success:
            # A bare "dbt build failed" sends you hunting; name the nodes.
            failures = [
                f"{r.node.name}: {r.message}"
                for r in (result.result or [])
                if str(r.status) not in ("success", "pass", "RunStatus.Success", "TestStatus.Pass")
            ]
            raise AssertionError("dbt build failed:\n" + "\n".join(failures or [str(result)]))
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@pytest.fixture(scope="module")
def marts(test_db_url: str) -> Iterator[Engine]:
    """Seed an outage: v1 scores most days, v2 backfills the gap after being promoted."""
    engine = create_engine(test_db_url)
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE prices, features, predictions, model_runs, portfolio_snapshots, "
                "option_quotes, universe RESTART IDENTITY CASCADE"
            )
        )
    with Session(engine) as session:
        sync_universe(session, [UniverseEntry("AAPL", "stock"), UniverseEntry("SPY", "etf")])
        bars = []
        for i, day in enumerate(DATES):
            bars.append(["AAPL", day, 100.0 + i, 102.0 + i, 99.0 + i, 101.0 + i, 1000, "yfinance"])
            bars.append(["SPY", day, 500.0 + i, 502.0 + i, 499.0 + i, 501.0 + i, 5000, "yfinance"])
        upsert_prices(session, pd.DataFrame(bars, columns=BAR_COLUMNS))

        equity = 1.0
        for i, day in enumerate(DATES):
            ret = 0.01 if i % 2 == 0 else -0.004
            equity *= 1 + ret
            # The outage days carry v2 — the champion that only existed later.
            version = "2" if day in OUTAGE else "1"
            session.add(
                PortfolioSnapshot(
                    date=day,
                    variant="daily",
                    equity=equity,
                    daily_return=ret,
                    gross_exposure=2.0,
                    net_exposure=0.0,
                    turnover=0.5,
                    positions={"AAPL": 0.5, "SPY": -0.5},
                    model_version=version,
                )
            )
            session.add(Prediction(ticker="AAPL", date=day, model_version=version, score=0.05))
        for version, promoted in (("1", V1_PROMOTED), ("2", V2_PROMOTED)):
            session.add(
                ModelRun(
                    run_type="train",
                    mlflow_run_id=f"run{version}",
                    model_version=version,
                    metrics={"holdout_sharpe": 1.0},
                    decision="promoted",
                    created_at=dt.datetime.combine(promoted, dt.time(9)),
                )
            )
        session.commit()

    _dbt_build(test_db_url)
    yield engine
    engine.dispose()


def _phases(engine: Engine) -> dict[dt.date, str]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT date, phase FROM analytics.fct_portfolio_daily ORDER BY date")
        ).all()
    return {r.date: r.phase for r in rows}


def test_outage_days_scored_by_a_later_champion_are_marked_backfilled(marts: Engine) -> None:
    phases = _phases(marts)
    assert [phases[d] for d in OUTAGE] == ["backfilled"] * len(OUTAGE)


def test_those_days_are_not_counted_as_live(marts: Engine) -> None:
    """The point of the exercise: the live record must not absorb in-sample days."""
    with marts.connect() as conn:
        live_days = conn.execute(
            text("SELECT n_days FROM analytics.fct_track_record WHERE phase = 'live'")
        ).scalar_one()
    live_dates = [d for d, p in _phases(marts).items() if p == "live"]
    assert live_days == len(live_dates)
    assert not set(OUTAGE) & set(live_dates)


def test_days_the_incumbent_scored_in_its_own_time_stay_live(marts: Engine) -> None:
    """Only the mismatch is demoted — an ordinary live day is untouched."""
    phases = _phases(marts)
    ordinary = [d for d in DATES if d >= V1_PROMOTED and d not in OUTAGE]
    assert ordinary, "fixture must contain genuine live days"
    assert {phases[d] for d in ordinary} == {"live"}


def test_pre_promotion_history_is_still_replay(marts: Engine) -> None:
    """'backfilled' must not swallow the replay phase: before any champion existed the
    right label is still 'replay', which already means in-sample."""
    phases = _phases(marts)
    assert {phases[d] for d in DATES if d < V1_PROMOTED} == {"replay"}
