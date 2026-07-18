"""Purged, embargoed time-series cross-validation for panel data.

Walk-forward splits over unique dates: each fold validates on a contiguous block
of dates and trains only on dates strictly before it, with an embargo gap so that
overlapping forward-return labels can't leak across the boundary.
"""

import datetime as dt
from dataclasses import dataclass


@dataclass(frozen=True)
class DateSplit:
    train_dates: list[dt.date]
    val_dates: list[dt.date]


def purged_walk_forward_splits(
    dates: list[dt.date],
    n_splits: int = 5,
    embargo_days: int = 5,
    min_train_dates: int = 63,
) -> list[DateSplit]:
    """Split sorted unique `dates` into walk-forward folds.

    The first fold's validation block starts after enough history for training;
    folds whose training window is shorter than `min_train_dates` are dropped.
    `embargo_days` counts trading dates (list positions), not calendar days.
    """
    unique_dates = sorted(set(dates))
    n = len(unique_dates)
    # Reserve enough history that even the first fold trains on >= min_train_dates
    # after the embargo gap is carved out.
    first_val_start = min_train_dates + embargo_days
    fold_span = (n - first_val_start) // n_splits
    if fold_span < 1:
        raise ValueError(f"Not enough dates ({n}) for {n_splits} splits")

    splits: list[DateSplit] = []
    for i in range(n_splits):
        val_start = first_val_start + i * fold_span
        val_end = val_start + fold_span if i < n_splits - 1 else n
        train = unique_dates[: val_start - embargo_days]
        val = unique_dates[val_start:val_end]
        if len(train) < min_train_dates or not val:
            continue
        splits.append(DateSplit(train_dates=train, val_dates=val))
    if not splits:
        raise ValueError("No usable splits produced")
    return splits
