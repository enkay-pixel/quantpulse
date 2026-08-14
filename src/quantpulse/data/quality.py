"""Data-quality checks over bar frames. Reused by the CLI and Dagster asset checks."""

import datetime as dt
from collections.abc import Iterable
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

    returns = (
        bars.sort_values(["ticker", "date"])
        .groupby("ticker")["close"]
        .pct_change(fill_method=None)
        .abs()
    )
    extreme = int((returns > EXTREME_DAILY_MOVE).sum())
    results.append(CheckResult("no_extreme_moves", extreme == 0, {"extreme_rows": extreme}))

    return results


def benchmark_gaps(
    benchmark: str,
    market_sessions: Iterable[dt.date],
    benchmark_dates: Iterable[dt.date],
    in_universe: bool = True,
) -> CheckResult:
    """Flag sessions the market ingested but its benchmark is missing.

    `completeness` above cannot see this: it judges every ticker against the same ratio, so
    a single absent day passes comfortably. That is right for one ticker among many and
    wrong for the benchmark, which `fct_alpha_beta` and `fct_portfolio_vs_benchmark` join
    inner — each missing bar drops a whole day from the CAPM decomposition while the track
    record keeps it, leaving the two marts disagreeing about the live day count. Hence zero
    tolerance here.

    Compared against sessions the market actually ingested, not the exchange calendar. A day
    nobody has data for is an outage and already the catch-up sensor's to report.
    """
    if not in_universe:
        # Not a data gap but a config error, and a permanent one: nothing ingests a ticker
        # outside the universe, so the marts would quietly never gain another row.
        return CheckResult(
            "benchmark_freshness",
            False,
            {"benchmark": benchmark, "reason": "benchmark is not an active universe member"},
        )
    have = set(benchmark_dates)
    sessions = sorted(market_sessions)
    missing = [day for day in sessions if day not in have]
    return CheckResult(
        "benchmark_freshness",
        not missing,
        {
            "benchmark": benchmark,
            "sessions_checked": len(sessions),
            "missing_days": [str(day) for day in missing],
            "last_bar": str(max(have)) if have else None,
        },
    )


def failed_checks(results: list[CheckResult]) -> list[CheckResult]:
    return [r for r in results if not r.passed]
