"""Data-quality checks over bar frames. Reused by the CLI and Dagster asset checks."""

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

COMPLETENESS_THRESHOLD = 0.95
EXTREME_DAILY_MOVE = 0.5  # |return| beyond this is suspicious for large caps


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    details: dict[str, Any] = field(default_factory=dict)


def run_quality_checks(
    bars: pd.DataFrame,
    expected_days: list[dt.date],
    tickers: list[str],
) -> list[CheckResult]:
    """Validate a long bar frame (ticker, date, open, high, low, close, volume)."""
    results = [
        CheckResult("non_empty", not bars.empty, {"rows": len(bars)}),
    ]
    if bars.empty:
        return results

    nulls = bars[["open", "high", "low", "close", "volume"]].isna().sum()
    results.append(
        CheckResult(
            "no_nulls",
            bool((nulls == 0).all()),
            {str(c): int(n) for c, n in nulls.items() if n > 0},
        )
    )

    bad_prices = bars[
        (bars[["open", "high", "low", "close"]] <= 0).any(axis=1) | (bars["high"] < bars["low"])
    ]
    results.append(
        CheckResult(
            "prices_valid",
            bad_prices.empty,
            {"bad_rows": len(bad_prices)},
        )
    )

    duplicates = int(bars.duplicated(subset=["ticker", "date"]).sum())
    results.append(CheckResult("unique_keys", duplicates == 0, {"duplicates": duplicates}))

    incomplete: dict[str, float] = {}
    if expected_days:
        counts = bars.groupby("ticker")["date"].nunique()
        for ticker in tickers:
            ratio = counts.get(ticker, 0) / len(expected_days)
            if ratio < COMPLETENESS_THRESHOLD:
                incomplete[ticker] = round(ratio, 3)
    results.append(
        CheckResult(
            "completeness",
            not incomplete,
            {"threshold": COMPLETENESS_THRESHOLD, "below": incomplete},
        )
    )

    returns = bars.sort_values(["ticker", "date"]).groupby("ticker")["close"].pct_change().abs()
    extreme = int((returns > EXTREME_DAILY_MOVE).sum())
    results.append(CheckResult("no_extreme_moves", extreme == 0, {"extreme_rows": extreme}))

    return results


def failed_checks(results: list[CheckResult]) -> list[CheckResult]:
    return [r for r in results if not r.passed]
