"""Quality checks for an option-chain snapshot.

Measured empirically: a post-close snapshot averages ~33% ATM implied volatility, while
a pre-market one averages ~2% — the feed reports stale near-zero IV for contracts that
haven't traded. That lesson only lived in the runbook; these checks enforce it, so a
junk snapshot is flagged instead of silently entering a dataset we cannot re-fetch.
"""

import pandas as pd

from quantpulse.data.quality import CheckResult

MIN_TICKER_COVERAGE = 0.8  # share of the active universe expected in a snapshot
MIN_PLAUSIBLE_MEDIAN_IV = 0.05  # below this the feed is almost certainly stale
MAX_PLAUSIBLE_MEDIAN_IV = 3.0  # 300% median IV means something is badly wrong
MIN_TRADED_SHARE = 0.05  # some contracts must carry open interest


def run_option_quality_checks(quotes: pd.DataFrame, n_active_tickers: int) -> list[CheckResult]:
    """Validate one snapshot. `quotes` needs ticker, implied_volatility, open_interest,
    and the Greek columns."""
    results = [CheckResult("non_empty", not quotes.empty, {"rows": len(quotes)})]
    if quotes.empty:
        return results

    tickers = quotes["ticker"].nunique()
    coverage = tickers / n_active_tickers if n_active_tickers else 0.0
    results.append(
        CheckResult(
            "ticker_coverage",
            coverage >= MIN_TICKER_COVERAGE,
            {"tickers": tickers, "expected": n_active_tickers, "coverage": round(coverage, 3)},
        )
    )

    # The headline staleness gate: median IV among contracts that actually trade.
    traded = quotes[quotes["open_interest"] > 0]
    median_iv = float(traded["implied_volatility"].median()) if not traded.empty else 0.0
    results.append(
        CheckResult(
            "implied_vol_plausible",
            MIN_PLAUSIBLE_MEDIAN_IV <= median_iv <= MAX_PLAUSIBLE_MEDIAN_IV,
            {
                "median_iv": round(median_iv, 4),
                "min": MIN_PLAUSIBLE_MEDIAN_IV,
                "max": MAX_PLAUSIBLE_MEDIAN_IV,
                "hint": "near-zero median IV means a stale/pre-market snapshot",
            },
        )
    )

    traded_share = len(traded) / len(quotes)
    results.append(
        CheckResult(
            "has_traded_contracts",
            traded_share >= MIN_TRADED_SHARE,
            {"traded_share": round(traded_share, 3)},
        )
    )

    greek_cols = ["delta", "gamma", "theta", "vega", "theo_value"]
    null_greeks = int(quotes[greek_cols].isna().any(axis=1).sum())
    results.append(CheckResult("greeks_present", null_greeks == 0, {"null_rows": null_greeks}))

    return results
