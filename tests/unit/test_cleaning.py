"""A -99% day followed by a +100x day is a vendor units bug, not a price.

Real case: SBK.JO closed 22775.31 / 228.86 / 23321.98 across three sessions with normal
volume. Left in, the first JSE book compounded to 8,788x.
"""

import datetime as dt

import pandas as pd
import pytest

from quantpulse.data.cleaning import UNIT_FACTOR, repair_price_units


def frame(closes: list[float], ticker: str = "SBK.JO") -> pd.DataFrame:
    days = [dt.date(2025, 4, 1) + dt.timedelta(days=i) for i in range(len(closes))]
    return pd.DataFrame(
        {
            "ticker": ticker,
            "date": days,
            "open": closes,
            "high": [c * 1.01 for c in closes],
            "low": [c * 0.99 for c in closes],
            "close": closes,
            "volume": [1_000_000] * len(closes),
        }
    )


def test_repairs_the_real_sbk_glitch() -> None:
    out, fixed = repair_price_units(frame([22486.48, 22761.32, 22775.31, 228.86, 23321.98]))
    assert fixed == 1
    assert out["close"].iloc[3] == pytest.approx(22886.0, rel=1e-6)


def test_every_price_column_is_rescaled_together() -> None:
    """Rescaling close but not open/high/low would leave an impossible bar."""
    out, _ = repair_price_units(frame([10043.4, 10132.3, 100.92, 9976.4, 10345.2]))
    row = out.iloc[2]
    assert row["close"] == pytest.approx(10092.0, rel=1e-6)
    assert row["low"] < row["close"] < row["high"]


def test_a_hundredfold_spike_is_repaired_downward() -> None:
    out, fixed = repair_price_units(frame([100.0, 101.0, 10250.0, 102.0, 103.0]))
    assert fixed == 1
    assert out["close"].iloc[2] == pytest.approx(102.5, rel=1e-6)


def test_ordinary_volatility_is_left_alone() -> None:
    """Guards against over-correction: a crash is not a units error."""
    original = frame([100.0, 95.0, 60.0, 65.0, 70.0])
    out, fixed = repair_price_units(original)
    assert fixed == 0
    pd.testing.assert_frame_equal(out.reset_index(drop=True), original.reset_index(drop=True))


def test_a_one_sided_jump_is_not_repaired() -> None:
    """A genuine re-denomination persists; only a single-day round trip is a glitch."""
    _, fixed = repair_price_units(frame([10000.0, 10100.0, 101.0, 102.0, 103.0]))
    assert fixed == 0


def test_each_ticker_is_judged_independently() -> None:
    good = frame([100.0, 101.0, 102.0, 103.0, 104.0], ticker="AAA.JO")
    bad = frame([10043.4, 10132.3, 100.92, 9976.4, 10345.2], ticker="BBB.JO")
    out, fixed = repair_price_units(pd.concat([good, bad], ignore_index=True))
    assert fixed == 1
    assert out[out["ticker"] == "AAA.JO"]["close"].tolist() == [100.0, 101.0, 102.0, 103.0, 104.0]


def test_short_and_empty_frames_are_noops() -> None:
    """A single-day ingest has no neighbours to judge against."""
    assert repair_price_units(frame([100.0, 1.0]))[1] == 0
    assert repair_price_units(pd.DataFrame())[1] == 0


def test_factor_matches_the_jse_quote_convention() -> None:
    assert UNIT_FACTOR == 100.0  # ZAc per ZAR
