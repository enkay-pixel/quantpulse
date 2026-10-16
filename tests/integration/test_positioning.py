"""The positioning marts and endpoints against seeded rows whose answers are worked by hand.

What has to hold (ADR 0007):
- dollar gamma per 1% move is gamma x OI x 100 x spot^2 x 0.01, calls and puts apart;
- contracts that would swamp it — expiring that day, junk near-zero IV — are left out;
- short interest is joined as of the day it became known, never by settlement date;
- the latest view pairs the newest snapshot with the newest short interest known now.

With spot 100, each contract's figure is gamma x OI x 10,000, which keeps the arithmetic visible.
"""

import datetime as dt
from collections.abc import Callable, Iterator

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

from quantpulse.api.app import create_app
from quantpulse.api.deps import engine_dep, session_dep
from quantpulse.data.universe import UniverseEntry, sync_universe
from quantpulse.db import OptionQuote, Price, ShortInterest

pytestmark = pytest.mark.integration

SNAPSHOT = dt.date(2026, 7, 20)
SPOT = 100.0
VOLUME = 1_000_000  # with close 100: $100M a day, so a share of ADV is gamma / 1e8


def _quote(
    ticker: str,
    strike: float,
    kind: str,
    days: int,
    oi: int,
    gamma: float,
    iv: float = 0.30,
) -> OptionQuote:
    return OptionQuote(
        snapshot_date=SNAPSHOT,
        ticker=ticker,
        expiry=SNAPSHOT + dt.timedelta(days=days),
        strike=strike,
        option_type=kind,
        underlying_close=SPOT,
        bid=1.0,
        ask=1.1,
        last_price=1.05,
        volume=10,
        open_interest=oi,
        implied_volatility=iv,
        in_the_money=False,
        theo_value=1.05,
        delta=0.5,
        gamma=gamma,
        theta=-0.01,
        vega=0.1,
    )


def _seed(engine: Engine) -> None:
    with Session(engine) as session:
        sync_universe(session, [UniverseEntry("AAPL", "stock"), UniverseEntry("SPY", "etf")])
        session.commit()
    with Session(engine) as session:
        for day in pd.bdate_range(end=SNAPSHOT, periods=20):
            for ticker in ("AAPL", "SPY"):
                session.add(
                    Price(
                        ticker=ticker,
                        date=day.date(),
                        open=SPOT,
                        high=SPOT,
                        low=SPOT,
                        close=SPOT,
                        volume=VOLUME,
                        source="yfinance",
                    )
                )
        session.add_all(
            [
                _quote("AAPL", 100.0, "call", days=10, oi=1000, gamma=0.05),  # 500,000, near term
                _quote("AAPL", 110.0, "call", days=60, oi=500, gamma=0.02),  # 100,000, beyond 30d
                _quote("AAPL", 90.0, "put", days=10, oi=2000, gamma=0.01),  # 200,000
                # Excluded: each would dwarf the rest if counted.
                _quote("AAPL", 95.0, "call", days=0, oi=5000, gamma=1.0),  # expires today
                _quote("AAPL", 105.0, "call", days=10, oi=5000, gamma=1.0, iv=0.005),  # junk IV
                _quote("AAPL", 120.0, "call", days=10, oi=0, gamma=0.03),  # no open interest
                _quote("SPY", 100.0, "call", days=5, oi=100, gamma=0.04),  # 40,000
            ]
        )
        session.add_all(
            [
                # Known before the snapshot: this is what the snapshot day could see.
                ShortInterest(
                    ticker="AAPL",
                    settlement_date=dt.date(2026, 6, 30),
                    shares_short=100,
                    shares_short_prior=80,
                    short_pct_float=0.01,
                    days_to_cover=2.0,
                    source="yfinance",
                    ingested_at=dt.datetime(2026, 7, 10, 12, tzinfo=dt.UTC),
                ),
                # Settled before the snapshot, but not public until the day after it.
                ShortInterest(
                    ticker="AAPL",
                    settlement_date=dt.date(2026, 7, 15),
                    shares_short=150,
                    shares_short_prior=100,
                    short_pct_float=0.015,
                    days_to_cover=3.0,
                    source="yfinance",
                    ingested_at=dt.datetime(2026, 7, 21, 12, tzinfo=dt.UTC),
                ),
            ]
        )
        session.commit()


@pytest.fixture(scope="module")
def client(test_db_url: str, dbt_build: Callable[..., None]) -> Iterator[TestClient]:
    engine = create_engine(test_db_url)
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE prices, option_quotes, short_interest, universe RESTART IDENTITY CASCADE"
            )
        )
    _seed(engine)
    dbt_build(test_db_url, "+fct_positioning")

    app = create_app()
    app.dependency_overrides[engine_dep] = lambda: engine

    def _session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[session_dep] = _session
    yield TestClient(app)
    engine.dispose()


def _mart_row(test_db_url: str, ticker: str) -> dict[str, object]:
    engine = create_engine(test_db_url)
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT * FROM analytics.fct_positioning WHERE ticker = :t"), {"t": ticker}
        ).mappings()
        out = dict(row.one())
    engine.dispose()
    return out


def test_dollar_gamma_counts_only_live_sane_contracts(client: TestClient) -> None:
    rows = {r["ticker"]: r for r in client.get("/research/positioning").json()["rows"]}
    aapl = rows["AAPL"]
    assert aapl["call_gamma_usd_1pct"] == pytest.approx(600_000)
    assert aapl["put_gamma_usd_1pct"] == pytest.approx(200_000)
    assert aapl["call_oi"] == 1500 and aapl["put_oi"] == 2000
    assert aapl["call_gamma_near_share"] == pytest.approx(500_000 / 600_000)


def test_gamma_is_read_against_twenty_sessions_of_dollar_volume(client: TestClient) -> None:
    aapl = {r["ticker"]: r for r in client.get("/research/positioning").json()["rows"]}["AAPL"]
    assert aapl["adv_usd_20d"] == pytest.approx(SPOT * VOLUME)
    assert aapl["call_gamma_share_of_adv"] == pytest.approx(600_000 / 1e8)
    assert aapl["put_gamma_share_of_adv"] == pytest.approx(200_000 / 1e8)


def test_etfs_are_labelled_so_the_page_can_keep_them_apart(client: TestClient) -> None:
    rows = {r["ticker"]: r for r in client.get("/research/positioning").json()["rows"]}
    assert rows["SPY"]["asset_type"] == "etf"
    assert rows["AAPL"]["asset_type"] == "stock"


def test_history_never_shows_short_interest_before_it_was_public(
    test_db_url: str, client: TestClient
) -> None:
    """The 07-15 settlement was stored on 07-21, so the 07-20 snapshot must carry 06-30's."""
    row = _mart_row(test_db_url, "AAPL")
    assert row["short_settlement_date"] == dt.date(2026, 6, 30)
    assert row["shares_short"] == 100
    assert row["short_change"] == pytest.approx(0.25)


def test_the_latest_view_shows_the_newest_short_interest_known_now(client: TestClient) -> None:
    """The page answers "what is known today", so it pairs the snapshot with 07-15's figure,
    and says when that figure settled and when it became known."""
    aapl = {r["ticker"]: r for r in client.get("/research/positioning").json()["rows"]}["AAPL"]
    assert aapl["short_settlement_date"] == "2026-07-15"
    assert aapl["short_known_from"] == "2026-07-21"
    assert aapl["short_change"] == pytest.approx(0.5)
    spy = {r["ticker"]: r for r in client.get("/research/positioning").json()["rows"]}["SPY"]
    assert spy["shares_short"] is None


def test_profile_lists_each_strike_with_calls_and_puts_apart(client: TestClient) -> None:
    body = client.get("/research/positioning/aapl/profile").json()
    assert body["spot"] == pytest.approx(SPOT)
    by_strike = {s["strike"]: s for s in body["strikes"]}
    assert set(by_strike) == {90.0, 100.0, 110.0}, "an excluded contract reached the profile"
    assert by_strike[100.0]["call_gamma_usd_1pct"] == pytest.approx(500_000)
    assert by_strike[90.0]["put_gamma_usd_1pct"] == pytest.approx(200_000)
    assert by_strike[90.0]["call_gamma_usd_1pct"] == 0


def test_a_market_without_chains_is_empty_not_an_error(client: TestClient) -> None:
    body = client.get("/research/positioning", params={"exchange": "XJSE"}).json()
    assert body == {"exchange": "XJSE", "snapshot_date": None, "rows": []}
