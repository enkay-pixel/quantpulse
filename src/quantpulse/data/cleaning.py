"""Repair vendor unit glitches in price series.

Yahoo intermittently reports a JSE close in Rand instead of cents — SBK.JO went
22,775 → 228.86 → 23,322 across 2025-04-24/25/29, with entirely normal volume. Left
alone that is a -99% day followed by a +100x day, which compounds into nonsense: the
first JSE book built over this data finished at 8,788x.

The correction is safe precisely because the artefact is impossible: no equity falls 99%
and recovers 100-fold in two sessions. A close that sits a clean factor of 100 away from
*both* neighbours is a units error, not a price.

Deliberately narrow — it only repairs the exact 100x signature, and only when both
neighbours agree. Anything less clear-cut is left alone and surfaced by the quality
checks instead, because silently "fixing" ambiguous data is how a platform starts lying
to itself.
"""

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

#: Cents-per-major-unit. JSE quotes in ZAc, so the glitch is always a factor of 100.
UNIT_FACTOR = 100.0
#: How close the observed ratio must be to the factor before we call it a units error.
TOLERANCE = 0.15
#: Columns that carry a price and must be scaled together.
PRICE_COLUMNS = ("open", "high", "low", "close")


def _glitch_mask(close: pd.Series) -> pd.Series:
    """Rows whose close is a clean factor of 100 away from both neighbours."""
    prev_close, next_close = close.shift(1), close.shift(-1)
    ratio_prev, ratio_next = close / prev_close, close / next_close

    def near(ratio: pd.Series, target: float) -> pd.Series:
        return (ratio - target).abs() / target <= TOLERANCE

    too_small = near(ratio_prev, 1 / UNIT_FACTOR) & near(ratio_next, 1 / UNIT_FACTOR)
    too_large = near(ratio_prev, UNIT_FACTOR) & near(ratio_next, UNIT_FACTOR)
    return (too_small | too_large).fillna(False)


def repair_price_units(bars: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Rescale rows whose price is off by exactly the unit factor. Returns (frame, n_fixed).

    Needs neighbouring rows to judge, so it is a no-op on a single-day frame — the daily
    ingest cannot see the glitch, but the next backfill or sweep will.
    """
    if bars.empty or "close" not in bars.columns:
        return bars, 0

    out = bars.sort_values(["ticker", "date"]).copy()
    fixed = 0
    for ticker, group in out.groupby("ticker", sort=False):
        if len(group) < 3:
            continue
        mask = _glitch_mask(group["close"])
        if not mask.any():
            continue
        idx = group.index[mask]
        # Direction per row: scale up when it is too small, down when too large.
        scale = np.where(
            group.loc[idx, "close"] < group["close"].shift(1).loc[idx], UNIT_FACTOR, 1 / UNIT_FACTOR
        )
        for column in PRICE_COLUMNS:
            if column in out.columns:
                out.loc[idx, column] = out.loc[idx, column].to_numpy() * scale
        fixed += len(idx)
        logger.warning(
            "Repaired %d unit glitch(es) in %s on %s",
            len(idx),
            ticker,
            [str(d) for d in group.loc[idx, "date"]][:5],
        )
    return out, fixed
