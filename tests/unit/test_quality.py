import datetime as dt

import pandas as pd

from quantpulse.data.quality import failed_checks, run_quality_checks


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
