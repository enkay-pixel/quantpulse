"""The research watchlist's sync, bars and chains (ADR 0007), against the test database.

What has to hold: a universe ticker is refused; a removed name leaves the list but keeps its
history; bars are refetched so a later adjustment lands; chains go to the watchlist's own table,
behind the same post-close gate as the universe's, and an evening with none at all fails.
"""

import datetime as dt
from collections.abc import Iterator
from contextlib import contextmanager

import pandas as pd
import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from quantpulse.data.universe import UniverseEntry, sync_universe
from quantpulse.research import watchlist as wl
from quantpulse.research.watchlist import (
    NoWatchlistChains,
    OffHoursSnapshotError,
    WatchlistError,
    WatchName,
    capture_watchlist_chains,
    refresh_watchlist_prices,
    sync_watchlist,
)

pytestmark = pytest.mark.integration

GME = WatchName("GME", "XNYS", "stock", "The 2021 squeeze.", "GameStop")
AMC = WatchName("AMC", "XNYS", "stock", "The other one.", "AMC Theatres")
MTN = WatchName("MTN.JO", "XJSE", "stock", "No chains on this market.")
SNAP = dt.date(2026, 10, 16)


def _count(engine: Engine, sql: str) -> int:
    with engine.connect() as conn:
        return int(conn.execute(text(sql)).scalar() or 0)


def test_a_universe_ticker_is_refused(db_engine: Engine) -> None:
    with Session(db_engine) as session:
        sync_universe(session, [UniverseEntry("GME", "stock")])
        session.commit()
        with pytest.raises(WatchlistError, match="already in the model's universe"):
            sync_watchlist(session, [GME])


def test_a_removed_name_leaves_the_list_but_keeps_its_history(db_engine: Engine) -> None:
    def bars(tickers: list[str], start: dt.date, end: dt.date) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "ticker": t,
                    "date": SNAP,
                    "open": 20.0,
                    "high": 21.0,
                    "low": 19.0,
                    "close": 20.5,
                    "volume": 1000,
                }
                for t in tickers
            ]
        )

    with Session(db_engine) as session:
        sync_watchlist(session, [GME, AMC])
        refresh_watchlist_prices(session, [GME, AMC], end=SNAP, fetch=bars)
        session.commit()
        assert sync_watchlist(session, [GME]) == {"names": 1, "removed": ["AMC"]}
        session.commit()
    assert _count(db_engine, "SELECT count(*) FROM watchlist") == 1
    assert _count(db_engine, "SELECT count(*) FROM watchlist_prices WHERE ticker = 'AMC'") == 1


def test_bars_are_refetched_so_a_later_adjustment_lands(db_engine: Engine) -> None:
    close = {"value": 20.0}

    def bars(tickers: list[str], start: dt.date, end: dt.date) -> pd.DataFrame:
        v = close["value"]
        return pd.DataFrame(
            [
                {
                    "ticker": "GME",
                    "date": SNAP,
                    "open": v,
                    "high": v,
                    "low": v,
                    "close": v,
                    "volume": 1000,
                }
            ]
        )

    with Session(db_engine) as session:
        refresh_watchlist_prices(session, [GME], end=SNAP, fetch=bars)
        close["value"] = 5.0  # a 4:1 split, applied by the vendor to history
        refresh_watchlist_prices(session, [GME], end=SNAP, fetch=bars)
        session.commit()
    assert _count(db_engine, "SELECT close FROM watchlist_prices WHERE ticker = 'GME'") == 5


@pytest.fixture
def chains(db_engine: Engine, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.setattr(wl, "is_post_close", lambda *a, **k: True)
    side = pd.DataFrame(
        [
            {
                "strike": k,
                "bid": 1.0,
                "ask": 1.2,
                "lastPrice": 1.1,
                "volume": 5,
                "openInterest": 50,
                "impliedVolatility": 0.9,
                "inTheMoney": False,
            }
            for k in (18.0, 20.0, 22.0)
        ]
    )
    asked: list[str] = []

    def fake(ticker: str, n: int):  # type: ignore[no-untyped-def]
        asked.append(ticker)
        return 20.0, [(SNAP + dt.timedelta(days=30), side, side)]

    monkeypatch.setattr(wl, "_fetch_ticker_chain", fake)

    @contextmanager
    def make_session() -> Iterator[Session]:
        with Session(db_engine) as s:
            yield s
            s.commit()

    return make_session, asked


def test_chains_go_to_the_watchlists_own_table_for_optioned_names_only(
    db_engine: Engine, chains
) -> None:  # type: ignore[no-untyped-def]
    make_session, asked = chains
    written = capture_watchlist_chains(make_session, [GME, MTN], snapshot_date=SNAP)
    assert written == 6 and asked == ["GME"], "the JSE name has no chains to ask for"
    assert _count(db_engine, "SELECT count(*) FROM watchlist_option_quotes") == 6
    assert _count(db_engine, "SELECT count(*) FROM option_quotes") == 0


def test_the_post_close_gate_applies_to_the_watchlist_too(
    db_engine: Engine, chains, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    make_session, _ = chains
    monkeypatch.setattr(wl, "is_post_close", lambda *a, **k: False)
    with pytest.raises(OffHoursSnapshotError):
        capture_watchlist_chains(make_session, [GME], snapshot_date=SNAP)


def test_an_evening_with_no_chain_at_all_fails(
    db_engine: Engine, chains, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    make_session, _ = chains
    monkeypatch.setattr(wl, "_fetch_ticker_chain", lambda t, n: (None, []))
    with pytest.raises(NoWatchlistChains):
        capture_watchlist_chains(make_session, [GME, AMC], snapshot_date=SNAP)
