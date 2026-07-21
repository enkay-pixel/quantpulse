"""Options endpoints against seeded quotes (Tier 1 summary/chain, Tier 2 idea)."""

import datetime as dt
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from quantpulse.api.app import create_app
from quantpulse.api.deps import engine_dep, session_dep
from quantpulse.db import OptionQuote, Prediction

pytestmark = pytest.mark.integration

SNAPSHOT = dt.date(2026, 7, 20)
NEAR = dt.date(2026, 7, 24)  # short-dated
FAR = dt.date(2026, 8, 21)  # past the 14-day preference
SPOT = 100.0
# Realistic monotone pricing: calls cheapen as strike rises, puts richen.
CALL_PRICES = {90.0: 12.0, 100.0: 5.0, 110.0: 1.5}
PUT_PRICES = {90.0: 1.5, 100.0: 5.0, 110.0: 12.0}


def _quote(expiry: dt.date, strike: float, kind: str, price: float) -> OptionQuote:
    return OptionQuote(
        snapshot_date=SNAPSHOT,
        ticker="AAPL",
        expiry=expiry,
        strike=strike,
        option_type=kind,
        underlying_close=SPOT,
        bid=price - 0.05,
        ask=price + 0.05,
        last_price=price,
        volume=10,
        open_interest=100 if kind == "call" else 150,
        implied_volatility=0.30,
        in_the_money=(strike < SPOT if kind == "call" else strike > SPOT),
        theo_value=price,
        delta=0.5 if kind == "call" else -0.5,
        gamma=0.02,
        theta=-0.01,
        vega=0.10,
    )


@pytest.fixture
def client(db_engine: Engine) -> Iterator[TestClient]:
    with Session(db_engine) as session:
        for expiry in (NEAR, FAR):
            for strike in (90.0, 100.0, 110.0):
                session.add(_quote(expiry, strike, "call", CALL_PRICES[strike]))
                session.add(_quote(expiry, strike, "put", PUT_PRICES[strike]))
        session.add(Prediction(ticker="AAPL", date=SNAPSHOT, model_version="1", score=0.05))
        session.commit()

    app = create_app()
    app.dependency_overrides[engine_dep] = lambda: db_engine

    def _session_override() -> Iterator[Session]:
        with Session(db_engine) as session:
            yield session

    app.dependency_overrides[session_dep] = _session_override
    yield TestClient(app)


def test_summary_reports_spot_and_expiries(client: TestClient) -> None:
    body = client.get("/options/aapl/summary").json()
    assert body["ticker"] == "AAPL"
    assert body["underlying_close"] == pytest.approx(SPOT)
    assert body["expiries"] == []  # analytics marts not built in this fixture
    assert body["snapshot_date"] is None  # degrades without the dbt mart


def test_chain_defaults_to_nearest_expiry_with_greeks(client: TestClient) -> None:
    body = client.get("/options/aapl/chain").json()
    assert body["expiry"] == str(NEAR)
    assert body["snapshot_date"] == str(SNAPSHOT)
    assert len(body["contracts"]) == 6  # 3 strikes x call/put
    first = body["contracts"][0]
    assert {"delta", "gamma", "theta", "vega", "implied_volatility"} <= set(first)


def test_chain_honors_explicit_expiry(client: TestClient) -> None:
    body = client.get(f"/options/aapl/chain?expiry={FAR}").json()
    assert body["expiry"] == str(FAR)
    assert len(body["contracts"]) == 6


def test_idea_builds_bull_spread_from_bullish_signal(client: TestClient) -> None:
    body = client.get("/options/aapl/idea").json()
    assert body["available"] is True
    assert body["direction"] == "bullish"
    assert body["structure"] == "bull call spread"
    assert body["expiry"] == str(FAR)  # prefers the >=14-day expiry
    assert [leg["action"] for leg in body["legs"]] == ["buy", "sell"]
    assert body["max_loss"] == pytest.approx(body["net_debit"])
    assert body["breakeven"] > SPOT


def test_idea_unavailable_for_unknown_ticker(client: TestClient) -> None:
    body = client.get("/options/ZZZZ/idea").json()
    assert body["available"] is False
    assert body["legs"] == []


def test_endpoints_degrade_with_no_option_data(client: TestClient) -> None:
    chain = client.get("/options/ZZZZ/chain").json()
    assert chain["contracts"] == []
    assert chain["snapshot_date"] is None
    summary = client.get("/options/ZZZZ/summary").json()
    assert summary["atm_iv"] is None
