"""Catch-up detection against real price coverage."""

import datetime as dt

import pandas as pd
import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from quantpulse.data.ingest import BAR_COLUMNS, upsert_prices
from quantpulse.data.universe import UniverseEntry, sync_universe
from quantpulse.db import ModelRun, OptionQuote, Price
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
    """Surviving stack up/down means that if the schedule never fired
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


# --- sessions missing particular tickers ---
#
# A missing ticker costs 1/11th of coverage here and 1/29th on the real JSE, so
# missing_trading_days rightly calls the day complete — while that ticker's features stretch
# across the gap, and for the benchmark fct_alpha_beta silently loses the whole day.

BENCHMARK = "SPY"  # the XNYS benchmark, per data.calendar
NEW_YORK = dt.timezone(dt.timedelta(hours=-4))  # EDT, for dating training runs


def _bar(ticker: str, day: dt.date, close: float = 101.0) -> pd.DataFrame:
    return pd.DataFrame(
        [[ticker, day, 100.0, max(102.0, close), 99.0, close, 1000, "yfinance"]],
        columns=BAR_COLUMNS,
    )


def _universe(session: Session) -> None:
    sync_universe(
        session, [UniverseEntry(t, "stock") for t in TICKERS] + [UniverseEntry(BENCHMARK, "etf")]
    )


@pytest.fixture
def seeded_with_benchmark(db_engine: Engine, monkeypatch) -> Engine:  # type: ignore[no-untyped-def]
    """Full coverage on all three days; the benchmark is absent on the middle one."""
    monkeypatch.setattr(catchup, "get_engine", lambda: db_engine)
    with Session(db_engine) as session:
        _universe(session)
        for day in DAYS:
            upsert_prices(session, _bars(day, 10))
        upsert_prices(session, _bar(BENCHMARK, DAYS[0]))
        upsert_prices(session, _bar(BENCHMARK, DAYS[2]))
        session.commit()
    return db_engine


def _trained_on(engine: Engine, day: dt.date) -> None:
    with Session(engine) as session:
        session.add(
            ModelRun(
                run_type="train",
                exchange="XNYS",
                metrics={},
                decision="rejected",
                created_at=dt.datetime.combine(day, dt.time(9), tzinfo=NEW_YORK),
            )
        )
        session.commit()


def test_a_benchmark_gap_is_found_on_an_otherwise_complete_day(
    seeded_with_benchmark: Engine,
) -> None:
    """The exact STX40.JO shape: every other ticker present, benchmark absent."""
    assert catchup.missing_trading_days(DAYS) == [], "coverage must consider the day fine"
    assert catchup.ticker_gap_days(DAYS) == [DAYS[1]]
    assert catchup.missing_tickers(DAYS[1]) == [BENCHMARK]


def test_any_missing_ticker_is_a_gap_not_only_the_benchmark(db_engine: Engine, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """The shape that went unretried in both markets: a few ordinary names absent from a session
    that otherwise landed."""
    monkeypatch.setattr(catchup, "get_engine", lambda: db_engine)
    with Session(db_engine) as session:
        _universe(session)
        for day in DAYS:
            upsert_prices(session, _bars(day, 10))
            upsert_prices(session, _bar(BENCHMARK, day))
        session.query(Price).filter(Price.ticker == "T3", Price.date == DAYS[1]).delete()
        session.commit()
    assert catchup.ticker_gap_days(DAYS) == [DAYS[1]]
    assert catchup.missing_tickers(DAYS[1]) == ["T3"]


def test_a_new_listing_is_not_a_gap(db_engine: Engine, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A ticker with no bar before a session was not trading yet; asking for it would spend
    the retry budget on a listing that did not exist."""
    monkeypatch.setattr(catchup, "get_engine", lambda: db_engine)
    with Session(db_engine) as session:
        _universe(session)
        for day in DAYS:
            upsert_prices(session, _bars(day, 9))  # T9 absent throughout ...
            upsert_prices(session, _bar(BENCHMARK, day))
        upsert_prices(session, _bar("T9", DAYS[2]))  # ... until it lists on the last day
        session.commit()
    assert catchup.ticker_gap_days(DAYS) == []


def test_a_session_a_retrain_has_used_is_not_requested(seeded_with_benchmark: Engine) -> None:
    """Filling it would change what that retrain was fitted on, and its refit would no longer
    reproduce."""
    _trained_on(seeded_with_benchmark, DAYS[1])
    assert catchup.latest_training_day() == DAYS[1]
    assert catchup.ticker_gap_days(DAYS) == []


def test_a_session_after_the_newest_retrain_is_still_requested(
    seeded_with_benchmark: Engine,
) -> None:
    _trained_on(seeded_with_benchmark, DAYS[0])
    assert catchup.ticker_gap_days(DAYS) == [DAYS[1]]


def test_a_complete_session_asks_for_nothing(seeded_with_benchmark: Engine) -> None:
    assert catchup.ticker_gap_days([DAYS[0], DAYS[2]]) == []


def test_days_outside_the_expected_window_are_ignored(seeded_with_benchmark: Engine) -> None:
    """The sensor passes its lookback window; a gap outside it is not this tick's business."""
    assert catchup.ticker_gap_days([DAYS[0]]) == []


def test_empty_expectation_is_noop_for_ticker_gaps(seeded_with_benchmark: Engine) -> None:
    assert catchup.ticker_gap_days([]) == []


def test_a_day_with_no_data_at_all_is_not_a_ticker_gap(db_engine: Engine, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """It belongs to missing_trading_days. Claiming it here too would spend the session's
    retry budget twice over for one underlying cause."""
    monkeypatch.setattr(catchup, "get_engine", lambda: db_engine)
    with Session(db_engine) as session:
        _universe(session)
        upsert_prices(session, _bars(DAYS[0], 10))
        upsert_prices(session, _bar(BENCHMARK, DAYS[0]))
        session.commit()  # DAYS[1] and DAYS[2] absent entirely
    assert catchup.missing_trading_days(DAYS) == [DAYS[1], DAYS[2]]
    assert catchup.ticker_gap_days(DAYS) == []


def test_a_fill_adds_what_is_missing_and_rewrites_nothing(db_engine: Engine) -> None:
    """A fill-only re-ingest must leave every stored bar exactly as it was. A vendor re-serving
    a stored day after a dividend returns a differently adjusted close, and overwriting would
    sit that price between unadjusted neighbours."""
    with Session(db_engine) as session:
        _universe(session)
        upsert_prices(session, _bar("T0", DAYS[0], close=101.0))
        session.commit()
        offered = pd.concat([_bar("T0", DAYS[0], close=99.0), _bar("T1", DAYS[0], close=50.0)])
        written = upsert_prices(session, offered, overwrite=False)
        session.commit()
        closes = dict(
            session.execute(select(Price.ticker, Price.close).where(Price.date == DAYS[0])).all()
        )
    assert written == 1, "only the absent bar is written, and the count says so"
    assert float(closes["T0"]) == pytest.approx(101.0), "a stored bar was rewritten"
    assert float(closes["T1"]) == pytest.approx(50.0)
