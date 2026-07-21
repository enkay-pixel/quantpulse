"""Catch-up detection against real price coverage."""

import datetime as dt

import pandas as pd
import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from quantpulse.data.ingest import BAR_COLUMNS, upsert_prices
from quantpulse.data.universe import UniverseEntry, sync_universe
from quantpulse.orchestration import catchup

pytestmark = pytest.mark.integration

DAYS = [dt.date(2026, 7, 13), dt.date(2026, 7, 14), dt.date(2026, 7, 15)]
TICKERS = [f"T{i}" for i in range(10)]


def _bars(day: dt.date, n_tickers: int) -> pd.DataFrame:
    return pd.DataFrame(
        [[TICKERS[i], day, 100.0, 102.0, 99.0, 101.0, 1000, "yfinance"] for i in range(n_tickers)],
        columns=BAR_COLUMNS,
    )


@pytest.fixture
def seeded(db_engine: Engine, monkeypatch) -> Engine:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(catchup, "get_engine", lambda: db_engine)
    with Session(db_engine) as session:
        sync_universe(session, [UniverseEntry(t, "stock") for t in TICKERS])
        upsert_prices(session, _bars(DAYS[0], 10))  # full coverage
        upsert_prices(session, _bars(DAYS[1], 3))  # partial -> counts as missing
        session.commit()  # DAYS[2] absent entirely
    return db_engine


def test_detects_absent_and_partial_sessions(seeded: Engine) -> None:
    missing = catchup.missing_trading_days(DAYS)
    assert missing == [DAYS[1], DAYS[2]]


def test_fully_covered_day_is_not_missing(seeded: Engine) -> None:
    assert catchup.missing_trading_days([DAYS[0]]) == []


def test_empty_expectation_is_noop(seeded: Engine) -> None:
    assert catchup.missing_trading_days([]) == []


def test_no_universe_means_nothing_to_catch_up(db_engine: Engine, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(catchup, "get_engine", lambda: db_engine)
    assert catchup.missing_trading_days(DAYS) == []
