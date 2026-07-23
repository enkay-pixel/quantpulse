"""Each paper book must vary exactly one field from the baseline — that is what makes
comparing it to the baseline a measurement rather than a coincidence."""

from dataclasses import fields

import numpy as np
import pandas as pd
import pytest

from quantpulse.ml.portfolio import (
    BASELINE,
    BOOKS,
    DAILY_BOOK,
    HORIZON_BOOK,
    LONG_ONLY_BOOK,
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


def test_each_book_varies_exactly_one_field_from_the_baseline() -> None:
    """Guards the comparison itself. Each book is a variation from one baseline, differing
    in exactly the field it declares — otherwise the gap stops being attributable."""
    assert BASELINE.varies is None, "the baseline varies nothing by definition"
    compared = [f.name for f in fields(BookConfig) if f.name not in {"variant", "varies"}]

    for book in BOOKS:
        differing = {f for f in compared if getattr(book, f) != getattr(BASELINE, f)}
        if book is BASELINE:
            assert not differing, f"baseline must equal itself, differs on {differing}"
            continue
        assert differing == {book.varies}, (
            f"{book.variant} declares varies={book.varies!r} but actually differs on {differing}"
        )


def test_variations_are_not_compared_to_each_other() -> None:
    """horizon vs long_only differs in two dimensions, so that pairing is meaningless.
    Documented here so nobody adds it to the dashboard as a comparison."""
    diffs = {
        f.name
        for f in fields(BookConfig)
        if f.name not in {"variant", "varies"}
        and getattr(HORIZON_BOOK, f.name) != getattr(LONG_ONLY_BOOK, f.name)
    }
    assert len(diffs) > 1


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


def test_long_only_book_holds_no_shorts_and_is_fully_exposed() -> None:
    preds, prices = make_frames()
    book = pd.DataFrame(build_book(preds, prices, LONG_ONLY_BOOK))
    assert all(w > 0 for row in book["positions"] for w in row.values())
    # Same capital deployed as long/short (gross 1.0), but fully exposed rather than netted.
    assert book["gross_exposure"].to_numpy() == pytest.approx(1.0)
    assert book["net_exposure"].to_numpy() == pytest.approx(1.0)


def test_long_only_book_pays_no_borrow() -> None:
    """Borrow is a fee on the short leg; a book with no shorts must not be charged it."""
    preds, prices = make_frames()
    free = build_book(preds, prices, BookConfig("x", 1, short_enabled=False, borrow_rate=0.0))
    charged = build_book(preds, prices, BookConfig("x", 1, short_enabled=False, borrow_rate=0.5))
    assert [r["daily_return"] for r in charged] == [r["daily_return"] for r in free]


def test_books_are_tagged_with_their_exchange() -> None:
    preds, prices = make_frames()
    book = build_book(preds, prices, DAILY_BOOK, exchange="XJSE")
    assert {r["exchange"] for r in book} == {"XJSE"}


def test_gross_exposure_is_dollar_neutral() -> None:
    preds, prices = make_frames()
    book = pd.DataFrame(build_book(preds, prices, DAILY_BOOK))
    assert book["gross_exposure"].to_numpy() == pytest.approx(1.0)
    assert book["net_exposure"].to_numpy() == pytest.approx(0.0, abs=1e-12)
