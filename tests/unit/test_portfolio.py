"""The two paper books must differ in rebalance frequency and nothing else — that is
what makes comparing them a measurement rather than a coincidence."""

import numpy as np
import pandas as pd
import pytest

from quantpulse.ml.portfolio import (
    BOOKS,
    DAILY_BOOK,
    HORIZON_BOOK,
    BookConfig,
    build_book,
)

N_DAYS = 84  # four horizon periods
N_TICKERS = 10


def make_frames(seed: int = 3) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Random walks plus scores that reshuffle daily, so a daily book churns hard."""
    rng = np.random.default_rng(seed)
    dates = [d.date() for d in pd.bdate_range("2024-01-01", periods=N_DAYS)]
    tickers = [f"T{i}" for i in range(N_TICKERS)]

    price_rows, pred_rows = [], []
    for t in tickers:
        close = 100.0
        for d in dates:
            close *= 1 + rng.normal(0.0004, 0.012)
            price_rows.append({"ticker": t, "date": d, "close": close})
    for d in dates:
        for t in tickers:
            pred_rows.append({"ticker": t, "date": d, "model_version": "1", "score": rng.normal()})
    return (
        pd.DataFrame(pred_rows).sort_values(["date", "ticker"]),
        pd.DataFrame(price_rows).sort_values(["ticker", "date"]),
    )


def test_books_differ_only_in_rebalance_frequency() -> None:
    """Guards the comparison itself: if any other field diverges, the gap between the
    books stops being attributable to horizon."""
    shared = {
        f: getattr(DAILY_BOOK, f)
        for f in ("long_q", "short_q", "cost_per_turnover", "borrow_rate", "side_weight")
    }
    for book in BOOKS:
        for field, value in shared.items():
            assert getattr(book, field) == value, f"{book.variant} diverges on {field}"
    assert DAILY_BOOK.rebalance_days != HORIZON_BOOK.rebalance_days


def test_horizon_book_trades_far_less_than_the_daily_book() -> None:
    preds, prices = make_frames()
    daily = pd.DataFrame(build_book(preds, prices, DAILY_BOOK))
    horizon = pd.DataFrame(build_book(preds, prices, HORIZON_BOOK))
    assert horizon["turnover"].mean() < daily["turnover"].mean() / 5


def test_held_days_pay_no_turnover() -> None:
    preds, prices = make_frames()
    horizon = pd.DataFrame(build_book(preds, prices, HORIZON_BOOK))
    # Only every 21st day rebalances; the rest are pure holds.
    assert (horizon["turnover"] == 0).sum() > len(horizon) * 0.9


def test_both_books_cover_the_same_days() -> None:
    """Comparability depends on identical date coverage."""
    preds, prices = make_frames()
    daily = pd.DataFrame(build_book(preds, prices, DAILY_BOOK))
    horizon = pd.DataFrame(build_book(preds, prices, HORIZON_BOOK))
    assert list(daily["date"]) == list(horizon["date"])


def test_final_date_is_dropped_not_recorded_flat() -> None:
    """The last date has no next-day return; nansum would silently call that a 0.0 day."""
    preds, prices = make_frames()
    book = build_book(preds, prices, DAILY_BOOK)
    assert book[-1]["date"] < max(prices["date"])


def test_borrow_accrues_on_every_day_held() -> None:
    preds, prices = make_frames()
    free = build_book(preds, prices, BookConfig("x", 1, borrow_rate=0.0, cost_per_turnover=0.0))
    charged = build_book(preds, prices, BookConfig("x", 1, borrow_rate=0.10, cost_per_turnover=0.0))
    assert all(c["daily_return"] < f["daily_return"] for c, f in zip(charged, free, strict=True))


def test_gross_exposure_is_dollar_neutral() -> None:
    preds, prices = make_frames()
    book = pd.DataFrame(build_book(preds, prices, DAILY_BOOK))
    assert book["gross_exposure"].to_numpy() == pytest.approx(1.0)
    assert book["net_exposure"].to_numpy() == pytest.approx(0.0, abs=1e-12)
