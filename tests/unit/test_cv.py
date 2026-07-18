import datetime as dt

import pandas as pd
import pytest

from quantpulse.ml.cv import purged_walk_forward_splits

DATES = list(pd.bdate_range("2023-01-02", periods=300).date)


def test_splits_are_walk_forward_and_disjoint() -> None:
    splits = purged_walk_forward_splits(DATES, n_splits=4, embargo_days=5, min_train_dates=100)
    assert len(splits) == 4
    for split in splits:
        assert max(split.train_dates) < min(split.val_dates)
        assert not set(split.train_dates) & set(split.val_dates)


def test_embargo_gap_enforced() -> None:
    embargo = 10
    splits = purged_walk_forward_splits(
        DATES, n_splits=3, embargo_days=embargo, min_train_dates=100
    )
    for split in splits:
        gap = DATES.index(min(split.val_dates)) - DATES.index(max(split.train_dates))
        assert gap > embargo


def test_validation_blocks_cover_tail_without_overlap() -> None:
    splits = purged_walk_forward_splits(DATES, n_splits=3, embargo_days=5, min_train_dates=100)
    seen: set[dt.date] = set()
    for split in splits:
        assert not seen & set(split.val_dates)
        seen |= set(split.val_dates)
    assert max(seen) == DATES[-1]


def test_insufficient_history_raises() -> None:
    with pytest.raises(ValueError, match="Not enough dates"):
        purged_walk_forward_splits(DATES[:50], n_splits=5, embargo_days=5, min_train_dates=100)
