import datetime as dt

import pandas as pd

from quantpulse.data.quality import benchmark_gaps, failed_checks, run_quality_checks


def make_bars(days: list[dt.date], tickers: list[str]) -> pd.DataFrame:
    rows = []
    for ticker in tickers:
        for i, day in enumerate(days):
            price = 100.0 + i
            rows.append(
                {
                    "ticker": ticker,
                    "date": day,
                    "open": price,
                    "high": price * 1.01,
                    "low": price * 0.99,
                    "close": price,
                    "volume": 1_000_000,
                }
            )
    return pd.DataFrame(rows)


DAYS = [dt.date(2024, 7, d) for d in (1, 2, 3, 5, 8)]
TICKERS = ["AAPL", "SPY"]


def test_clean_frame_passes_all_checks() -> None:
    results = run_quality_checks(make_bars(DAYS, TICKERS), DAYS, TICKERS)
    assert failed_checks(results) == []


def test_empty_frame_fails_non_empty() -> None:
    results = run_quality_checks(pd.DataFrame(), DAYS, TICKERS)
    assert [r.name for r in failed_checks(results)] == ["non_empty"]


def test_null_and_negative_prices_detected() -> None:
    bars = make_bars(DAYS, TICKERS)
    bars.loc[0, "close"] = None
    bars.loc[1, "low"] = -5.0
    failed = {r.name for r in failed_checks(run_quality_checks(bars, DAYS, TICKERS))}
    assert "no_nulls" in failed
    assert "prices_valid" in failed


def test_missing_days_fail_completeness() -> None:
    bars = make_bars(DAYS[:2], TICKERS)  # only 2 of 5 expected days
    results = run_quality_checks(bars, DAYS, TICKERS)
    completeness = next(r for r in results if r.name == "completeness")
    assert not completeness.passed
    assert set(completeness.details["below"]) == set(TICKERS)


def test_duplicate_keys_detected() -> None:
    bars = make_bars(DAYS, TICKERS)
    bars = pd.concat([bars, bars.head(1)], ignore_index=True)
    failed = {r.name for r in failed_checks(run_quality_checks(bars, DAYS, TICKERS))}
    assert "unique_keys" in failed


def test_extreme_move_detected() -> None:
    bars = make_bars(DAYS, ["AAPL"])
    bars.loc[bars.index[-1], "close"] = 500.0  # ~5x jump
    failed = {r.name for r in failed_checks(run_quality_checks(bars, DAYS, ["AAPL"]))}
    assert "no_extreme_moves" in failed


# --- benchmark freshness ---
#
# A benchmark bar went missing and nothing flagged it. Both existing guards were
# working as designed: the catch-up coverage floor is a share of the universe (28/29 = 0.97
# against 0.8), and per-ticker completeness scores one absent day in thirty at 0.967 against
# 0.95. One missing ticker *should* be ignored — unless it is the one the CAPM marts
# inner-join, which silently drops the whole day from fct_alpha_beta.

SESSIONS = [dt.date(2026, 8, d) for d in (5, 6, 7, 11, 12)]


def test_complete_benchmark_passes() -> None:
    result = benchmark_gaps("STX40.JO", SESSIONS, SESSIONS)
    assert result.passed
    assert result.details["missing_days"] == []
    assert result.details["last_bar"] == "2026-08-12"


def test_a_single_missing_day_fails_and_names_it() -> None:
    """The exact case the 0.95 completeness ratio waves through at 0.967."""
    have = [d for d in SESSIONS if d != dt.date(2026, 8, 11)]
    result = benchmark_gaps("STX40.JO", SESSIONS, have)
    assert not result.passed
    assert result.details["missing_days"] == ["2026-08-11"]
    assert result.details["benchmark"] == "STX40.JO"


def test_sessions_the_market_never_ingested_are_not_benchmark_gaps() -> None:
    """An outage is the catch-up sensor's alarm. If the market has no bars for a day, the
    benchmark missing it too is the same fact reported twice, on a day already loud."""
    outage_day = dt.date(2026, 8, 12)
    ingested = [d for d in SESSIONS if d != outage_day]
    assert benchmark_gaps("STX40.JO", ingested, ingested).passed


def test_a_benchmark_outside_the_universe_is_a_permanent_failure() -> None:
    """Nothing ingests a ticker the universe does not list, so this never self-heals —
    it must not read as a transient data gap."""
    result = benchmark_gaps("STX40.JO", SESSIONS, SESSIONS, in_universe=False)
    assert not result.passed
    assert "not an active universe member" in result.details["reason"]


def test_a_benchmark_with_no_bars_at_all_reports_no_last_bar() -> None:
    result = benchmark_gaps("STX40.JO", SESSIONS, [])
    assert not result.passed
    assert result.details["last_bar"] is None
    assert len(result.details["missing_days"]) == len(SESSIONS)


def test_one_missing_day_in_a_full_window_still_fails() -> None:
    """The discriminating case, and the one that actually happened.

    A five-day fixture cannot catch a ratio threshold — 1/5 = 0.2 fails any of them. The
    bug only appears at realistic window sizes: 1 absent day in 30 is 0.033, which slides
    under the 0.05 that `completeness` allows. This test is the reason the check is a
    set difference and not a ratio; it fails if anyone reintroduces one.
    """
    window = [dt.date(2026, 7, 1) + dt.timedelta(days=i) for i in range(30)]
    have = [d for d in window if d != window[15]]
    result = benchmark_gaps("STX40.JO", window, have)
    assert not result.passed, "a ratio threshold would wave this through at 0.967"
    assert result.details["missing_days"] == [str(window[15])]
