"""Persist and load engineered features (JSONB rows keyed by ticker/date/version)."""

import datetime as dt
from collections.abc import Mapping
from typing import Any, cast

import pandas as pd
from sqlalchemy import Engine, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from quantpulse.db import Feature
from quantpulse.features.engineering import FEATURE_COLUMNS
from quantpulse.utils import chunked


def store_features(session: Session, features: pd.DataFrame, version: str) -> int:
    """Idempotent upsert of a feature frame. Returns rows written."""
    if features.empty:
        return 0
    records = [
        {
            "ticker": row["ticker"],
            "date": row["date"],
            "feature_version": version,
            "values": {c: float(row[c]) for c in FEATURE_COLUMNS},
        }
        for row in features.to_dict(orient="records")
    ]
    for chunk in chunked(records):
        stmt = pg_insert(Feature).values(list(chunk))
        stmt = stmt.on_conflict_do_update(
            index_elements=[Feature.ticker, Feature.date, Feature.feature_version],
            # Indexed access: `.values` would resolve to the collection's method,
            # not the column named "values".
            set_={"values": stmt.excluded["values"]},
        )
        session.execute(stmt)
    return len(records)


def load_features(
    engine: Engine,
    version: str,
    start: dt.date | None = None,
    end: dt.date | None = None,
) -> pd.DataFrame:
    """Load stored features back into a wide frame (ticker, date, *FEATURE_COLUMNS)."""
    query = "SELECT ticker, date, values FROM features WHERE feature_version = %(version)s"
    params: dict[str, str | dt.date] = {"version": version}
    if start is not None:
        query += " AND date >= %(start)s"
        params["start"] = start
    if end is not None:
        query += " AND date <= %(end)s"
        params["end"] = end
    raw = pd.read_sql(query, engine, params=params)
    if raw.empty:
        return pd.DataFrame(columns=["ticker", "date", *FEATURE_COLUMNS])
    values = pd.json_normalize(raw["values"])
    frame = pd.concat([raw[["ticker", "date"]], values[FEATURE_COLUMNS]], axis=1)
    return frame.sort_values(["date", "ticker"]).reset_index(drop=True)


def load_price_bars(
    engine: Engine,
    start: dt.date | None = None,
    end: dt.date | None = None,
) -> pd.DataFrame:
    """Load stored bars for feature computation (active universe only)."""
    clauses = ["u.active"]
    params: dict[str, dt.date] = {}
    if start is not None:
        clauses.append("p.date >= :start")
        params["start"] = start
    if end is not None:
        clauses.append("p.date <= :end")
        params["end"] = end
    query = text(
        "SELECT p.ticker, p.date, p.close, p.volume FROM prices p "
        "JOIN universe u ON u.ticker = p.ticker "
        f"WHERE {' AND '.join(clauses)} ORDER BY p.ticker, p.date"
    )
    with engine.connect() as conn:
        return pd.read_sql(query, conn, params=cast("Mapping[str, Any]", params))
