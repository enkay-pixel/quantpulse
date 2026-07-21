"""Evidence endpoints tested against REAL dbt-built marts in the throwaway DB.

The module fixture seeds raw tables (with a promotion mid-way so both phases
exist) and runs `dbt build` against market_test, then every endpoint is
exercised over genuine mart output.
"""

import datetime as dt
import os
from collections.abc import Iterator
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, make_url, text
from sqlalchemy.orm import Session

from quantpulse.api.app import create_app
from quantpulse.api.deps import engine_dep, session_dep
from quantpulse.data.ingest import BAR_COLUMNS, upsert_prices
from quantpulse.data.universe import UniverseEntry, sync_universe
from quantpulse.db import ModelRun, PortfolioSnapshot, Prediction

pytestmark = pytest.mark.integration

PROJECT_ROOT = Path(__file__).parents[2]
TRANSFORM_DIR = PROJECT_ROOT / "transform"

DATES = [d.date() for d in pd.bdate_range("2024-07-01", periods=10)]
LIVE_CUTOVER = DATES[6]  # promotion timestamp -> last 4 days are 'live'


def _seed(engine) -> None:  # type: ignore[no-untyped-def]
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
            session.add(
                PortfolioSnapshot(
                    date=day,
                    equity=equity,
                    daily_return=ret,
                    gross_exposure=2.0,
                    net_exposure=0.0,
                    turnover=0.5,
                    positions={"AAPL": 0.5, "SPY": -0.5},
                    model_version="1",
                )
            )
            session.add_all(
                [
                    Prediction(ticker="AAPL", date=day, model_version="1", score=0.05),
                    Prediction(ticker="SPY", date=day, model_version="1", score=-0.01),
                ]
            )
        session.add(
            ModelRun(
                run_type="train",
                mlflow_run_id="run1",
                model_version="1",
                metrics={"holdout_sharpe": 1.0},
                decision="promoted",
                created_at=dt.datetime.combine(LIVE_CUTOVER, dt.time(9)),
            )
        )
        session.commit()


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
            [
                "build",
                "--project-dir",
                str(TRANSFORM_DIR),
                "--profiles-dir",
                str(TRANSFORM_DIR),
            ]
        )
        assert result.success, f"dbt build failed in test DB: {result.exception}"
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@pytest.fixture(scope="module")
def evidence_client(test_db_url: str) -> Iterator[TestClient]:
    engine = create_engine(test_db_url)
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE prices, features, predictions, model_runs, drift_metrics, "
                "portfolio_snapshots, option_quotes, universe RESTART IDENTITY CASCADE"
            )
        )
    _seed(engine)
    _dbt_build(test_db_url)

    app = create_app()
    app.dependency_overrides[engine_dep] = lambda: engine

    def _session_override() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[session_dep] = _session_override
    yield TestClient(app)
    engine.dispose()


def test_track_record_has_both_phases(evidence_client: TestClient) -> None:
    body = evidence_client.get("/track-record").json()
    assert body["live_since"] == str(LIVE_CUTOVER)
    phases = {p["phase"]: p for p in body["phases"]}
    assert set(phases) == {"replay", "live"}
    assert phases["replay"]["n_days"] == 6
    assert phases["live"]["n_days"] == 4
    assert 0 <= phases["live"]["win_rate"] <= 1


def test_equity_curve_gains_phase_and_benchmark(evidence_client: TestClient) -> None:
    body = evidence_client.get("/portfolio/equity-curve").json()
    assert len(body["points"]) == len(DATES)
    first, last = body["points"][0], body["points"][-1]
    assert first["phase"] == "replay"
    assert last["phase"] == "live"
    assert first["benchmark_equity"] == pytest.approx(1.0)
    assert last["benchmark_equity"] == pytest.approx(510.0 / 501.0)


def test_signal_quintiles(evidence_client: TestClient) -> None:
    body = evidence_client.get("/signals/quintiles").json()
    # Only 2 tickers per date -> ntile produces quintiles 1 and 2.
    assert [q["signal_quintile"] for q in body["overall"]] == [1, 2]
    assert body["recent"], "trailing window should not be empty"


def test_portfolio_risk_series(evidence_client: TestClient) -> None:
    body = evidence_client.get("/portfolio/risk").json()
    assert len(body["points"]) == len(DATES)
    assert all(p["drawdown"] <= 1e-9 for p in body["points"])


def test_positions_with_context(evidence_client: TestClient) -> None:
    body = evidence_client.get("/portfolio/positions").json()
    assert body["date"] == str(DATES[-1])
    rows = {r["ticker"]: r for r in body["rows"]}
    assert rows["AAPL"]["side"] == "long"
    assert rows["SPY"]["side"] == "short"
    assert rows["AAPL"]["latest_close"] == pytest.approx(110.0)
    assert rows["AAPL"]["latest_score"] == pytest.approx(0.05)


def test_model_history(evidence_client: TestClient) -> None:
    body = evidence_client.get("/models/history").json()
    assert len(body) == 1
    assert body[0]["decision"] == "promoted"
    assert body[0]["metrics"]["holdout_sharpe"] == pytest.approx(1.0)
