"""`refresh_features`: every market's features, computed one market at a time.

One market at a time keeps the nightly step's memory to the largest market instead of the sum.
That is only safe if it stores exactly what the single all-markets frame did, and if a refresh
that changes nothing writes nothing.
"""

import datetime as dt

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from quantpulse.data.ingest import BAR_COLUMNS, upsert_prices
from quantpulse.data.universe import UniverseEntry, sync_universe
from quantpulse.features.engineering import FEATURE_COLUMNS, compute_features
from quantpulse.features.store import load_features, load_price_bars, refresh_features

pytestmark = pytest.mark.integration

VERSION = "refresh-test"
DATES = [d.date() for d in pd.bdate_range("2024-01-01", periods=120)]
MARKETS = {
    "XNYS": ["AAA", "BBB", "CCC"],
    "XJSE": ["XXX.JO", "YYY.JO", "ZZZ.JO"],
    "XLON": ["LLL.L", "MMM.L"],
}


def _bars(tickers: list[str], seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for t in tickers:
        close = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.02, len(DATES))))
        volume = rng.integers(1_000, 5_000, len(DATES))
        for day, c, v in zip(DATES, close, volume, strict=True):
            rows.append([t, day, c, c * 1.01, c * 0.99, c, int(v), "yfinance"])
    return pd.DataFrame(rows, columns=BAR_COLUMNS)


@pytest.fixture
def seeded(db_engine: Engine) -> Engine:
    with Session(db_engine) as session:
        sync_universe(
            session,
            [UniverseEntry(t, "stock", exchange=code) for code, ts in MARKETS.items() for t in ts],
        )
        session.commit()
    with Session(db_engine) as session:
        for i, tickers in enumerate(MARKETS.values()):
            upsert_prices(session, _bars(tickers, seed=i))
        session.commit()
    return db_engine


def _ordered(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.assign(date=pd.to_datetime(frame["date"]).dt.date)
    return frame.sort_values(["ticker", "date"]).reset_index(drop=True)[
        ["ticker", "date", *FEATURE_COLUMNS]
    ]


def _row_versions(engine: Engine) -> dict[tuple[str, dt.date], str]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT ticker, date, xmin::text FROM features WHERE feature_version = :v"),
            {"v": VERSION},
        )
        return {(r[0], r[1]): r[2] for r in rows}


def test_one_market_at_a_time_stores_what_the_single_frame_did(seeded: Engine) -> None:
    expected = _ordered(compute_features(load_price_bars(seeded)))

    refreshed = refresh_features(seeded, VERSION)

    assert sorted(refreshed) == sorted(MARKETS)
    stored = _ordered(load_features(seeded, VERSION))
    pd.testing.assert_frame_equal(stored, expected, check_exact=True)
    for code, tickers in MARKETS.items():
        assert refreshed[code].computed == int(expected["ticker"].isin(tickers).sum())
        assert refreshed[code].written == refreshed[code].computed
        assert refreshed[code].latest_date == DATES[-1]


def test_a_refresh_that_changes_nothing_writes_nothing(seeded: Engine) -> None:
    refresh_features(seeded, VERSION)
    before = _row_versions(seeded)

    again = refresh_features(seeded, VERSION)

    assert {code: r.written for code, r in again.items()} == dict.fromkeys(MARKETS, 0)
    # The same tuple, not a rewrite with equal values: an update leaves a dead row behind.
    assert _row_versions(seeded) == before


def test_a_changed_bar_rewrites_only_its_own_market(seeded: Engine) -> None:
    refresh_features(seeded, VERSION)
    before = _row_versions(seeded)
    with Session(seeded) as session:
        bar = _bars(["YYY.JO"], seed=1).iloc[[-1]].copy()
        bar[["open", "high", "low", "close"]] *= 1.05
        upsert_prices(session, bar)
        session.commit()

    again = refresh_features(seeded, VERSION)

    assert again["XNYS"].written == again["XLON"].written == 0
    # The last day's YYY.JO row, and the JSE ranks on that day it moved.
    assert 1 <= again["XJSE"].written <= len(MARKETS["XJSE"])
    after = _row_versions(seeded)
    changed = {key for key in before if after[key] != before[key]}
    assert changed and all(t in MARKETS["XJSE"] and d == DATES[-1] for t, d in changed)
