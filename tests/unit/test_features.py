import datetime as dt

import numpy as np
import pandas as pd
import pytest

from quantpulse.features.engineering import (
    FEATURE_COLUMNS,
    build_training_frame,
    compute_features,
    make_forward_returns,
)


@pytest.fixture(scope="module")
def bars() -> pd.DataFrame:
    """~150 business days of synthetic bars for 8 tickers with distinct trends."""
    rng = np.random.default_rng(7)
    dates = pd.bdate_range("2024-01-02", periods=150).date
    rows = []
    for i, ticker in enumerate([f"T{i}" for i in range(8)]):
        drift = (i - 4) * 0.001
        prices = 100 * np.cumprod(1 + drift + rng.normal(0, 0.01, len(dates)))
        for d, p in zip(dates, prices, strict=True):
            rows.append({"ticker": ticker, "date": d, "close": p, "volume": 1_000_000 + i})
    return pd.DataFrame(rows)


def test_compute_features_shape_and_columns(bars: pd.DataFrame) -> None:
    features = compute_features(bars)
    assert list(features.columns) == ["ticker", "date", *FEATURE_COLUMNS]
    assert not features.isna().any().any()
    # 63-day momentum needs warm-up: first ~63 dates per ticker drop out.
    assert features.groupby("ticker").size().min() >= 150 - 70


def test_cross_sectional_rank_bounds(bars: pd.DataFrame) -> None:
    features = compute_features(bars)
    for col in [c for c in FEATURE_COLUMNS if c.endswith("_cs_rank")]:
        assert features[col].between(0, 1).all()


def test_forward_returns_known_values() -> None:
    dates = pd.bdate_range("2024-01-02", periods=4).date
    bars = pd.DataFrame(
        {
            "ticker": ["A"] * 4,
            "date": dates,
            "close": [100.0, 110.0, 121.0, 133.1],
            "volume": [1] * 4,
        }
    )
    fwd = make_forward_returns(bars, horizon=1)
    assert len(fwd) == 3  # last row has no future
    assert fwd["fwd_ret"].round(6).tolist() == [0.1, 0.1, 0.1]


def test_no_lookahead_in_features(bars: pd.DataFrame) -> None:
    """Truncating the future must not change past feature values."""
    full = compute_features(bars)
    cutoff = dt.date(2024, 6, 3)
    truncated = compute_features(bars[bars["date"] <= cutoff])
    merged = full[full["date"] <= cutoff].merge(
        truncated, on=["ticker", "date"], suffixes=("_full", "_trunc")
    )
    assert not merged.empty
    for col in FEATURE_COLUMNS:
        pd.testing.assert_series_equal(
            merged[f"{col}_full"], merged[f"{col}_trunc"], check_names=False
        )


def test_build_training_frame_inner_join(bars: pd.DataFrame) -> None:
    features = compute_features(bars)
    targets = make_forward_returns(bars, horizon=5)
    frame = build_training_frame(features, targets)
    assert {"ticker", "date", "fwd_ret"}.issubset(frame.columns)
    assert frame["date"].max() < bars["date"].max()  # last horizon days have no target


def test_cross_sectional_ranks_never_mix_exchanges() -> None:
    """The core M11 fix. Ranking every ticker against every other on a date would compare
    Naspers to Apple — different currency, session and macro. Ranks must be per-exchange,
    and this degrades silently rather than failing, so it needs its own test."""
    dates = [d.date() for d in pd.bdate_range("2024-01-01", periods=90)]
    rows = []
    for ticker, exchange, level in [
        ("AAPL", "XNYS", 100.0),
        ("MSFT", "XNYS", 200.0),
        ("NPN.JO", "XJSE", 79000.0),  # quoted in cents: three orders of magnitude larger
        ("SOL.JO", "XJSE", 19000.0),
    ]:
        px = level
        for d in dates:
            px *= 1.001 if ticker in {"AAPL", "NPN.JO"} else 0.999
            rows.append(
                {"ticker": ticker, "date": d, "exchange": exchange, "close": px, "volume": 1e6}
            )
    feats = compute_features(pd.DataFrame(rows))

    exchange_of = {"AAPL": "XNYS", "MSFT": "XNYS", "NPN.JO": "XJSE", "SOL.JO": "XJSE"}
    feats["exchange"] = feats["ticker"].map(exchange_of)
    # With two names per exchange, per-exchange percentile ranks are exactly {0.5, 1.0}.
    for _, group in feats.groupby(["date", "exchange"]):
        assert sorted(group["ret_5_cs_rank"].round(6)) == [0.5, 1.0]


def test_features_without_an_exchange_column_still_work(bars: pd.DataFrame) -> None:
    """Single-market callers pass no exchange; behaviour must be unchanged."""
    assert "exchange" not in bars.columns
    feats = compute_features(bars)
    assert not feats.empty
    assert feats["ret_5_cs_rank"].between(0, 1).all()
