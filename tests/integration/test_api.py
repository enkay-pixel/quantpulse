"""API integration tests: the FastAPI app pointed at the disposable test database."""

import datetime as dt
from collections.abc import Iterator

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from quantpulse.api.app import create_app
from quantpulse.api.deps import engine_dep, session_dep
from quantpulse.data.ingest import BAR_COLUMNS, upsert_prices
from quantpulse.data.universe import UniverseEntry, sync_universe
from quantpulse.db import DriftMetric, ModelRun, PortfolioSnapshot, Prediction

pytestmark = pytest.mark.integration

DATES = [dt.date(2024, 7, 1), dt.date(2024, 7, 2), dt.date(2024, 7, 3)]


@pytest.fixture
def client(db_engine: Engine) -> Iterator[TestClient]:
    with Session(db_engine) as session:
        sync_universe(session, [UniverseEntry("AAPL", "stock"), UniverseEntry("SPY", "etf")])
        bars = pd.DataFrame(
            [
                ["AAPL", d, 100.0 + i, 102.0 + i, 99.0 + i, 101.0 + i, 1_000_000, "yfinance"]
                for i, d in enumerate(DATES)
            ]
            + [["SPY", DATES[0], 500.0, 502.0, 499.0, 501.0, 5_000_000, "yfinance"]],
            columns=BAR_COLUMNS,
        )
        upsert_prices(session, bars)
        session.add_all(
            [
                Prediction(ticker="AAPL", date=DATES[-1], model_version="3", score=0.05),
                Prediction(ticker="SPY", date=DATES[-1], model_version="3", score=-0.01),
                ModelRun(
                    run_type="train",
                    mlflow_run_id="abc123",
                    model_version="3",
                    metrics={"holdout_sharpe": 1.1, "holdout_ic": 0.03},
                    decision="promoted",
                ),
                PortfolioSnapshot(
                    date=DATES[1],
                    equity=1.01,
                    daily_return=0.01,
                    gross_exposure=2.0,
                    net_exposure=0.0,
                    turnover=1.0,
                    positions={"AAPL": 0.5, "SPY": -0.5},
                    model_version="3",
                ),
                DriftMetric(
                    date=DATES[-1],
                    feature_version="v1",
                    metric_name="psi:ret_5",
                    value=0.31,
                    drifted=True,
                ),
                DriftMetric(
                    date=DATES[-1],
                    feature_version="v1",
                    metric_name="share_drifted",
                    value=0.08,
                    drifted=False,
                ),
            ]
        )
        session.commit()

    app = create_app()

    def _engine_override() -> Engine:
        return db_engine

    def _session_override() -> Iterator[Session]:
        with Session(db_engine) as session:
            yield session

    app.dependency_overrides[engine_dep] = _engine_override
    app.dependency_overrides[session_dep] = _session_override
    yield TestClient(app)


def test_root_redirects_to_docs(client: TestClient) -> None:
    res = client.get("/", follow_redirects=False)
    assert res.status_code == 307
    assert res.headers["location"] == "/docs"


def test_health(client: TestClient) -> None:
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["database"] is True
    assert body["latest_price_date"] == str(DATES[-1])


def test_universe(client: TestClient) -> None:
    body = client.get("/universe").json()
    assert [m["ticker"] for m in body] == ["AAPL", "SPY"]


def test_prices_with_window_and_404(client: TestClient) -> None:
    body = client.get(f"/prices/aapl?start={DATES[1]}").json()
    assert body["ticker"] == "AAPL"
    assert len(body["points"]) == 2
    assert client.get("/prices/ZZZZ").status_code == 404


def test_signal_history_series(client: TestClient) -> None:
    body = client.get("/signals/history/aapl").json()
    assert body["ticker"] == "AAPL"
    assert len(body["points"]) == 1
    assert body["points"][0]["score"] == pytest.approx(0.05)
    assert client.get("/signals/history/ZZZZ").json()["points"] == []


def test_latest_predictions_ranked(client: TestClient) -> None:
    body = client.get("/predictions/latest").json()
    assert body["date"] == str(DATES[-1])
    assert body["model_version"] == "3"
    assert [r["ticker"] for r in body["rows"]] == ["AAPL", "SPY"]
    assert body["rows"][0]["rank"] == 1


def test_equity_curve(client: TestClient) -> None:
    body = client.get("/portfolio/equity-curve").json()
    assert len(body["points"]) == 1
    assert body["total_return"] == pytest.approx(0.01)


def test_current_model(client: TestClient) -> None:
    body = client.get("/models/current").json()
    assert body["model_version"] == "3"
    assert body["metrics"]["holdout_sharpe"] == pytest.approx(1.1)


def test_drift_status(client: TestClient) -> None:
    body = client.get("/drift/latest").json()
    assert body["share_drifted"] == pytest.approx(0.08)
    assert body["features"][0]["feature"] == "ret_5"
    assert body["features"][0]["drifted"] is True


def test_freshness(client: TestClient) -> None:
    body = client.get("/freshness").json()
    assert body["latest_price_date"] == str(DATES[-1])
    assert body["latest_feature_date"] is None
