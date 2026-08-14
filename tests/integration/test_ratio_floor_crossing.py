"""What the API serves once a phase finally has enough days to publish ratios.

Every existing test of this contract checks the *suppressing* half: below
`min_days_for_ratios` (20) the marts null Sharpe, volatility, win rate, beta, alpha and
information ratio, and the API passes the nulls through. Nothing checked the other half.
That asymmetry means a floor accidentally raised, or a guard that nulled unconditionally,
would keep every test green while the dashboard said "not enough data" forever — and the
failure would look exactly like a young track record, which is what the project genuinely
had for weeks.

The first moment the platform can publish an earned ratio is a bad moment to discover the
path was never exercised.

Seeds 40 sessions with the promotion at index 10, so the two phases sit on opposite sides
of the floor in a single build: replay 10 days (suppressed), live 30 (published). That also
pins the floor as *per phase* rather than global.
"""

import datetime as dt
import math
import os
from collections.abc import Iterator
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, make_url, text
from sqlalchemy.orm import Session

from quantpulse.api.app import create_app
from quantpulse.api.deps import engine_dep, session_dep
from quantpulse.data.ingest import BAR_COLUMNS, upsert_prices
from quantpulse.data.universe import UniverseEntry, sync_universe
from quantpulse.db import ModelRun, PortfolioSnapshot, Prediction

pytestmark = pytest.mark.integration

TRANSFORM_DIR = Path(__file__).parents[2] / "transform"
DATES = [d.date() for d in pd.bdate_range("2024-07-01", periods=40)]
LIVE_CUTOVER = DATES[10]  # 10 replay days (below the floor), 30 live (above it)
RATIOS = ("sharpe", "annualized_volatility", "win_rate")


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
            raise AssertionError(f"dbt build failed: {result.exception or result.result}")
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _seed(engine: Engine) -> None:
    with Session(engine) as session:
        sync_universe(session, [UniverseEntry("AAPL", "stock"), UniverseEntry("SPY", "etf")])
        bars = []
        for i, day in enumerate(DATES):
            # Benchmark and strategy move differently, or beta is degenerate and the
            # regression has nothing to find.
            bars.append(["AAPL", day, 100.0 + i, 102.0 + i, 99.0 + i, 101.0 + i, 1000, "yfinance"])
            drift = 500.0 + i * 0.5
            bars.append(["SPY", day, drift, drift + 2, drift - 1, drift + 1, 5000, "yfinance"])
        upsert_prices(session, pd.DataFrame(bars, columns=BAR_COLUMNS))

        equity = 1.0
        for i, day in enumerate(DATES):
            # Varied returns: a constant series has zero variance, which the marts null on
            # purpose, so it would prove nothing about the published path.
            ret = (0.012, -0.004, 0.007, -0.009, 0.003)[i % 5]
            equity *= 1 + ret
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
                    model_version="1",
                )
            )
            session.add(Prediction(ticker="AAPL", date=day, model_version="1", score=0.05))
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


@pytest.fixture(scope="module")
def crossed(test_db_url: str) -> Iterator[TestClient]:
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


def _phases(client: TestClient, path: str) -> dict[str, dict]:
    return {row["phase"]: row for row in client.get(path).json()["phases"]}


def test_a_phase_over_the_floor_actually_publishes_its_ratios(crossed: TestClient) -> None:
    """The half nothing tested. Without this, ratios nulled forever look like a young
    track record and no test disagrees."""
    live = _phases(crossed, "/track-record")["live"]
    assert live["n_days"] == 30
    for field in RATIOS:
        assert live[field] is not None, f"{field} withheld at 30 days, above the 20-day floor"


def test_the_floor_is_applied_per_phase_not_globally(crossed: TestClient) -> None:
    """Both phases come from one build. A global check would publish the young phase's
    ratios too, which is how a 3-day Sharpe of -54.93 reached the dashboard."""
    phases = _phases(crossed, "/track-record")
    assert phases["replay"]["n_days"] == 10
    for field in RATIOS:
        assert phases["replay"][field] is None, f"replay has 10 days; {field} must stay withheld"
    assert phases["replay"]["total_return"] is not None, "counts and totals survive any sample"


def test_published_ratios_are_finite_numbers(crossed: TestClient) -> None:
    """JSON has no NaN or Infinity. A ratio that divides by a near-zero denominator would
    either break the response or arrive as something the dashboard cannot render — and this
    only becomes reachable once a phase is allowed to publish at all."""
    live = _phases(crossed, "/track-record")["live"]
    for field in RATIOS:
        value = live[field]
        assert isinstance(value, int | float), f"{field} is {type(value).__name__}"
        assert math.isfinite(value), f"{field} is not finite: {value}"


def test_the_capm_decomposition_publishes_once_over_the_floor(crossed: TestClient) -> None:
    """fct_alpha_beta nulls on the same threshold and is served by a different endpoint,
    so it needs its own crossing — the two marts count days independently."""
    live = _phases(crossed, "/portfolio/alpha-beta")["live"]
    assert live["n_days"] >= 20
    for field in ("beta", "alpha_annualized", "information_ratio"):
        value = live[field]
        assert value is not None, f"{field} withheld above the floor"
        assert math.isfinite(value), f"{field} is not finite: {value}"
