"""The advisor brief's endpoints against seeded rows (ADR 0007).

Only what this module seeds is asserted: the analytics schema is shared across the test session,
so marts built by other modules may hold rows for the same tickers.
"""

import datetime as dt
from collections.abc import Callable, Iterator

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from quantpulse.api.app import create_app
from quantpulse.api.deps import engine_dep, session_dep
from quantpulse.data.universe import UniverseEntry, sync_universe
from quantpulse.db import Prediction, Price, WatchlistName, WatchlistPrice

pytestmark = pytest.mark.integration

LAST = dt.date(2026, 10, 16)
NAMES = ["AAPL", "MSFT", "NVDA", "AMD", "KO"]


@pytest.fixture(scope="module")
def client(test_db_url: str, dbt_build: Callable[..., None]) -> Iterator[TestClient]:
    engine = create_engine(test_db_url)
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE prices, predictions, watchlist, watchlist_prices, universe "
                "RESTART IDENTITY CASCADE"
            )
        )
    with Session(engine) as session:
        sync_universe(session, [UniverseEntry(t, "stock") for t in NAMES])
        session.commit()
    days = [d.date() for d in pd.bdate_range(end=LAST, periods=300)]
    with Session(engine) as session:
        for i, day in enumerate(days):
            close = 100.0 + i * 0.1
            session.add(
                Price(
                    ticker="AAPL",
                    date=day,
                    open=close,
                    high=close,
                    low=close,
                    close=close,
                    volume=1_000_000,
                    source="yfinance",
                )
            )
            session.add(
                WatchlistPrice(
                    ticker="GME",
                    date=day,
                    open=25.0,
                    high=25.0,
                    low=25.0,
                    close=25.0,
                    volume=1_000_000,
                )
            )
        # AAPL is the model's third choice of five on the newest day; an older day must not count.
        for rank, ticker in enumerate(["NVDA", "MSFT", "AAPL", "AMD", "KO"]):
            session.add(
                Prediction(ticker=ticker, date=LAST, model_version="v3", score=0.05 - rank / 100)
            )
            session.add(
                Prediction(ticker=ticker, date=days[-2], model_version="v3", score=rank / 100)
            )
        session.add(
            WatchlistName(
                ticker="GME", exchange="XNYS", asset_type="stock", why="The 2021 squeeze."
            )
        )
        session.commit()
    dbt_build(test_db_url, "+stg_research_names")

    app = create_app()
    app.dependency_overrides[engine_dep] = lambda: engine

    def _session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[session_dep] = _session
    yield TestClient(app)
    engine.dispose()


def test_the_index_lists_the_models_names_then_the_watchlist(client: TestClient) -> None:
    names = client.get("/research/briefs?exchange=XNYS").json()["names"]
    assert [(n["ticker"], n["followed_by"]) for n in names] == [
        *[(t, "model") for t in sorted(NAMES)],
        ("GME", "watchlist"),
    ]


def test_a_model_name_reads_its_rank_on_the_newest_day_and_its_price(client: TestClient) -> None:
    brief = client.get("/research/brief/aapl").json()
    facts = {f["fact"]: f for f in brief["facts"]}
    assert facts["The model's rank today"]["value"] == "3 of 5 on XNYS (middle)"
    assert facts["Last close"]["value"] == "$129.90"
    assert brief["as_of"] == str(LAST)
    assert "not a recommendation" in brief["disclaimer"]


def test_a_watchlist_name_has_a_brief_without_a_model_view(client: TestClient) -> None:
    brief = client.get("/research/brief/GME").json()
    facts = {f["fact"]: f["value"] for f in brief["facts"]}
    assert brief["followed_by"] == "watchlist"
    assert facts["The model's view"] == "None"
    assert facts["Last close"] == "$25.00"


def test_a_name_nobody_follows_is_not_found(client: TestClient) -> None:
    response = client.get("/research/brief/ZZZZ")
    assert response.status_code == 404
    assert "neither in the model's universe nor on the watchlist" in response.json()["detail"]
