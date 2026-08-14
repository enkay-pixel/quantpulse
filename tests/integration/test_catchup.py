"""Catch-up detection against real price coverage."""

import datetime as dt

import pandas as pd
import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from quantpulse.data.ingest import BAR_COLUMNS, upsert_prices
from quantpulse.data.universe import UniverseEntry, sync_universe
from quantpulse.db import OptionQuote
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


def _quote(day: dt.date, ticker: str) -> OptionQuote:
    return OptionQuote(
        snapshot_date=day,
        ticker=ticker,
        expiry=day + dt.timedelta(days=30),
        strike=100.0,
        option_type="call",
        underlying_close=101.0,
        implied_volatility=0.3,
        in_the_money=False,
        theo_value=1.0,
        delta=0.5,
        gamma=0.1,
        theta=-0.1,
        vega=0.2,
        volume=10,
        open_interest=50,
    )


def test_missing_option_snapshot_is_a_gap_not_skipped(seeded: Engine) -> None:
    """The whole point of surviving stack up/down: if the 19:00 schedule never fired
    (stack down), a *missing* today-snapshot must still trigger capture post-close — not
    be deferred to a schedule that already came and went."""
    day = DAYS[0]
    assert catchup.option_snapshot_incomplete(day) == 0.0  # nothing captured -> full gap


def test_thin_option_snapshot_is_a_gap(seeded: Engine) -> None:
    day = DAYS[0]
    with Session(seeded) as session:
        for t in TICKERS[:3]:  # 3 of 10 -> 30%, below the 80% floor
            session.add(_quote(day, t))
        session.commit()
    cov = catchup.option_snapshot_incomplete(day)
    assert cov is not None and cov == pytest.approx(0.3)


def test_complete_option_snapshot_needs_no_capture(seeded: Engine) -> None:
    day = DAYS[0]
    with Session(seeded) as session:
        for t in TICKERS:  # all 10 -> 100%
            session.add(_quote(day, t))
        session.commit()
    assert catchup.option_snapshot_incomplete(day) is None


# --- benchmark-only gaps ---
#
# A missing benchmark costs 1/11th of coverage here and 1/29th on the real JSE, so
# missing_trading_days rightly calls the day complete — while fct_alpha_beta, which
# inner-joins the benchmark, silently loses the whole day.

BENCHMARK = "SPY"  # the XNYS benchmark, per data.calendar


def _benchmark_bar(day: dt.date) -> pd.DataFrame:
    return pd.DataFrame(
        [[BENCHMARK, day, 100.0, 102.0, 99.0, 101.0, 1000, "yfinance"]], columns=BAR_COLUMNS
    )


@pytest.fixture
def seeded_with_benchmark(db_engine: Engine, monkeypatch) -> Engine:  # type: ignore[no-untyped-def]
    """Full coverage on all three days; the benchmark is absent on the middle one."""
    monkeypatch.setattr(catchup, "get_engine", lambda: db_engine)
    with Session(db_engine) as session:
        sync_universe(
            session,
            [UniverseEntry(t, "stock") for t in TICKERS] + [UniverseEntry(BENCHMARK, "etf")],
        )
        for day in DAYS:
            upsert_prices(session, _bars(day, 10))
        upsert_prices(session, _benchmark_bar(DAYS[0]))
        upsert_prices(session, _benchmark_bar(DAYS[2]))
        session.commit()
    return db_engine


def test_a_benchmark_gap_is_found_on_an_otherwise_complete_day(
    seeded_with_benchmark: Engine,
) -> None:
    """The exact STX40.JO shape: every other ticker present, benchmark absent."""
    assert catchup.missing_trading_days(DAYS) == [], "coverage must consider the day fine"
    assert catchup.benchmark_missing_days(DAYS) == [DAYS[1]]


def test_a_complete_benchmark_asks_for_nothing(seeded_with_benchmark: Engine) -> None:
    assert catchup.benchmark_missing_days([DAYS[0], DAYS[2]]) == []


def test_days_outside_the_expected_window_are_ignored(seeded_with_benchmark: Engine) -> None:
    """The sensor passes its lookback window; a gap outside it is not this tick's business."""
    assert catchup.benchmark_missing_days([DAYS[0]]) == []


def test_empty_expectation_is_noop_for_benchmarks(seeded_with_benchmark: Engine) -> None:
    assert catchup.benchmark_missing_days([]) == []


def test_a_day_with_no_data_at_all_is_not_a_benchmark_gap(db_engine: Engine, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """It belongs to missing_trading_days. Claiming it here too would spend the session's
    retry budget twice over for one underlying cause."""
    monkeypatch.setattr(catchup, "get_engine", lambda: db_engine)
    with Session(db_engine) as session:
        sync_universe(
            session,
            [UniverseEntry(t, "stock") for t in TICKERS] + [UniverseEntry(BENCHMARK, "etf")],
        )
        upsert_prices(session, _bars(DAYS[0], 10))
        upsert_prices(session, _benchmark_bar(DAYS[0]))
        session.commit()  # DAYS[1] and DAYS[2] absent entirely
    assert catchup.missing_trading_days(DAYS) == [DAYS[1], DAYS[2]]
    assert catchup.benchmark_missing_days(DAYS) == []
