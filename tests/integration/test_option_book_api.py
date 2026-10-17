"""The paper options book end to end: rebuilt from a seeded database and read back through the API.

The share book holds AAA long and BBB short from 2026-08-12, then flips them on 2026-09-11. BBB
has no chain, so it is skipped with its reason. AAA's call spread buys the 100 at 5.00 and sells
the 110 at 1.00, a 4.00 debit, and closes at 7.00 - 2.00 = 5.00. After the flip, AAA's put spread
buys the 100 put at 4.00 and sells the 90 at 0.90, a 3.10 debit, valued next day at 4.40 - 1.10.
"""

import datetime as dt
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from quantpulse.api.app import create_app
from quantpulse.api.deps import engine_dep, session_dep
from quantpulse.data.universe import UniverseEntry, sync_universe
from quantpulse.db import OptionQuote, PortfolioSnapshot
from quantpulse.options.book import COMMISSION_PER_LEG, CONTRACT, RISK_BUDGET, rebuild_option_book

pytestmark = pytest.mark.integration

BEFORE, OPEN, NEXT, FLIP, LATEST = (
    dt.date(2026, 8, 11),
    dt.date(2026, 8, 12),
    dt.date(2026, 8, 13),
    dt.date(2026, 9, 11),
    dt.date(2026, 9, 14),
)
CALL_EXPIRY, PUT_EXPIRY = dt.date(2026, 9, 18), dt.date(2026, 10, 16)


def _snapshot(day: dt.date, positions: dict[str, float], equity: float) -> PortfolioSnapshot:
    return PortfolioSnapshot(
        date=day,
        exchange="XNYS",
        variant="horizon",
        equity=equity,
        daily_return=0.0,
        gross_exposure=1.0,
        net_exposure=0.0,
        turnover=0.0,
        positions=positions,
        model_version="10",
    )


def _quote(
    day: dt.date, expiry: dt.date, kind: str, strike: float, bid: float, ask: float
) -> OptionQuote:
    return OptionQuote(
        snapshot_date=day,
        ticker="AAA",
        expiry=expiry,
        strike=strike,
        option_type=kind,
        underlying_close=100.0,
        bid=bid,
        ask=ask,
        last_price=(bid + ask) / 2,
        volume=10,
        open_interest=100,
        implied_volatility=0.3,
        in_the_money=False,
        theo_value=(bid + ask) / 2,
        delta=0.5,
        gamma=0.02,
        theta=-0.01,
        vega=0.1,
    )


@pytest.fixture
def client(db_engine: Engine) -> Iterator[TestClient]:
    with Session(db_engine) as session:
        sync_universe(session, [UniverseEntry("AAA", "stock"), UniverseEntry("BBB", "stock")])
        session.commit()
    with Session(db_engine) as session:
        session.add_all(
            [
                _snapshot(BEFORE, {"CCC": 0.5, "DDD": -0.5}, 0.99),  # before any chain: not traded
                _snapshot(OPEN, {"AAA": 0.5, "BBB": -0.5}, 1.00),
                _snapshot(NEXT, {"AAA": 0.5, "BBB": -0.5}, 1.01),
                _snapshot(FLIP, {"BBB": 0.5, "AAA": -0.5}, 1.03),
                _snapshot(LATEST, {"BBB": 0.5, "AAA": -0.5}, 1.04),
                _quote(OPEN, CALL_EXPIRY, "call", 100, 4.9, 5.0),
                _quote(OPEN, CALL_EXPIRY, "call", 110, 1.0, 1.1),
                _quote(FLIP, CALL_EXPIRY, "call", 100, 7.0, 7.1),
                _quote(FLIP, CALL_EXPIRY, "call", 110, 1.9, 2.0),
                _quote(FLIP, PUT_EXPIRY, "put", 100, 3.9, 4.0),
                _quote(FLIP, PUT_EXPIRY, "put", 90, 0.9, 1.0),
                _quote(LATEST, PUT_EXPIRY, "put", 100, 4.4, 4.5),
                _quote(LATEST, PUT_EXPIRY, "put", 90, 1.0, 1.1),
            ]
        )
        session.commit()
    with Session(db_engine) as session:
        rebuild_option_book(db_engine, session, "XNYS")
        session.commit()

    app = create_app()
    app.dependency_overrides[engine_dep] = lambda: db_engine

    def _session() -> Iterator[Session]:
        with Session(db_engine) as session:
            yield session

    app.dependency_overrides[session_dep] = _session
    yield TestClient(app)


def test_cohorts_follow_the_share_book_and_skip_what_cannot_trade(client: TestClient) -> None:
    body = client.get("/options/book").json()
    first, second = body["cohorts"]
    assert (first["opened"], first["exit_date"], first["spreads"], first["skipped"]) == (
        str(OPEN),
        str(FLIP),
        1,
        1,
    )
    assert second["opened"] == str(FLIP) and second["exit_date"] is None
    assert first["phase"] == "replay"


def test_a_closed_cohorts_return_is_worked_from_the_pessimistic_prices(client: TestClient) -> None:
    first = client.get("/options/book").json()["cohorts"][0]
    cost = 4.0 * CONTRACT + 2 * COMMISSION_PER_LEG
    proceeds = 5.0 * CONTRACT - 2 * COMMISSION_PER_LEG
    assert first["return_on_premium"] == pytest.approx(proceeds / cost - 1)
    assert first["options_return"] == pytest.approx(RISK_BUDGET * (proceeds / cost - 1))
    # The same names as shares over the same window: the share book from 0.99 to 1.01.
    assert first["shares_return"] == pytest.approx(1.01 / 0.99 - 1)


def test_the_newest_cohort_lists_its_spreads_and_its_skips(client: TestClient) -> None:
    positions = {p["ticker"]: p for p in client.get("/options/book").json()["positions"]}
    put = positions["AAA"]
    assert (put["side"], put["option_type"], put["long_strike"], put["short_strike"]) == (
        "short",
        "put",
        100,
        90,
    )
    assert put["entry_debit"] == pytest.approx(3.1)
    assert put["mark_value"] == pytest.approx(3.3) and put["mark_basis"] == "quote"
    assert put["status"] == "open"
    assert positions["BBB"]["status"] == "skipped"
    assert positions["BBB"]["note"] == "no chain captured on the open date"


def test_the_share_book_is_drawn_on_the_options_books_scale(client: TestClient) -> None:
    days = client.get("/options/book").json()["days"]
    assert days[0]["date"] == str(OPEN)
    assert days[0]["share_equity"] == pytest.approx(1.0)


def test_a_market_without_chains_has_an_empty_book(client: TestClient) -> None:
    body = client.get("/options/book", params={"exchange": "XJSE"}).json()
    assert body["days"] == [] and body["cohorts"] == [] and body["positions"] == []
