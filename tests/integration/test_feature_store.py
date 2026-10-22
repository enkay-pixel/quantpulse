import datetime as dt

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from quantpulse.features.engineering import FEATURE_COLUMNS
from quantpulse.features.store import load_features, store_features

pytestmark = pytest.mark.integration


def feature_frame(dates: list[dt.date], tickers: list[str]) -> pd.DataFrame:
    rng = np.random.default_rng(5)
    rows = []
    for ticker in tickers:
        for date in dates:
            row: dict[str, object] = {"ticker": ticker, "date": date}
            row.update({c: float(rng.normal()) for c in FEATURE_COLUMNS})
            rows.append(row)
    return pd.DataFrame(rows)


def test_store_and_load_features_roundtrip(db_engine: Engine) -> None:
    from quantpulse.data.universe import UniverseEntry, sync_universe

    dates = [dt.date(2024, 7, 1), dt.date(2024, 7, 2)]
    frame = feature_frame(dates, ["AAPL", "SPY"])

    with Session(db_engine) as session:
        # features FK to universe, as they do in production.
        sync_universe(session, [UniverseEntry("AAPL", "stock"), UniverseEntry("SPY", "etf")])
        assert store_features(session, frame, version="test-v") == 4
        session.commit()
        # Overwrite with new values — upsert must update, not duplicate.
        frame2 = frame.copy()
        frame2[FEATURE_COLUMNS[0]] = 99.0
        assert store_features(session, frame2, version="test-v") == 4
        session.commit()

    loaded = load_features(db_engine, "test-v")
    assert len(loaded) == 4
    assert list(loaded.columns) == ["ticker", "date", *FEATURE_COLUMNS]
    assert (loaded[FEATURE_COLUMNS[0]] == 99.0).all()

    windowed = load_features(db_engine, "test-v", start=dates[1])
    assert set(windowed["date"]) == {dates[1]}

    assert load_features(db_engine, "missing-version").empty


def test_rows_are_stored_across_chunks_and_unchanged_ones_skipped(
    db_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rows are built a chunk at a time; a chunk boundary must neither drop nor repeat one, and
    a row whose values did not change is not written again."""
    from quantpulse.data.universe import UniverseEntry, sync_universe
    from quantpulse.features import store

    monkeypatch.setattr(store, "UPSERT_CHUNK_ROWS", 3)
    dates = [dt.date(2024, 7, d) for d in range(1, 6)]
    frame = feature_frame(dates, ["AAPL", "SPY"])  # 10 rows: chunks of 3, 3, 3, 1

    with Session(db_engine) as session:
        sync_universe(session, [UniverseEntry("AAPL", "stock"), UniverseEntry("SPY", "etf")])
        assert store_features(session, frame, version="chunk-v") == 10
        session.commit()
        assert store_features(session, frame, version="chunk-v") == 0
        changed = frame.copy()
        changed.loc[7, FEATURE_COLUMNS[2]] = -1.0
        assert store_features(session, changed, version="chunk-v") == 1
        session.commit()

    loaded = (
        load_features(db_engine, "chunk-v").sort_values(["ticker", "date"]).reset_index(drop=True)
    )
    expected = changed.sort_values(["ticker", "date"]).reset_index(drop=True)
    assert len(loaded) == 10
    assert np.array_equal(loaded[FEATURE_COLUMNS].to_numpy(), expected[FEATURE_COLUMNS].to_numpy())
