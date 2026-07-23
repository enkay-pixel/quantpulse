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
