"""Persist and load engineered features (JSONB rows keyed by ticker/date/version)."""

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

import pandas as pd
from sqlalchemy import Engine, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from quantpulse.db import Feature
from quantpulse.features.engineering import FEATURE_COLUMNS, compute_features
from quantpulse.utils import UPSERT_CHUNK_ROWS


def store_features(session: Session, features: pd.DataFrame, version: str) -> int:
    """Idempotent upsert of a feature frame. Returns rows inserted or changed.

    A row whose recomputed values match the stored ones is left alone. The nightly refresh
    recomputes the whole history, and rewriting all of it to change a few hundred rows left a
    dead copy of every row behind: 2.36 million updates in the night London arrived.
    """
    if features.empty:
        return 0
    written = 0
    stored = Feature.__table__.c["values"]
    # Rows become dicts a chunk at a time. A dict per row for the whole frame at once was
    # 1.37 KiB a row, 342 MiB of the nightly step's 814 with three markets.
    for start in range(0, len(features), UPSERT_CHUNK_ROWS):
        part = features.iloc[start : start + UPSERT_CHUNK_ROWS]
        records = [
            {
                "ticker": row["ticker"],
                "date": row["date"],
                "feature_version": version,
                "values": {c: float(row[c]) for c in FEATURE_COLUMNS},
            }
            for row in part.to_dict(orient="records")
        ]
        stmt = pg_insert(Feature).values(records)
        stmt = stmt.on_conflict_do_update(
            index_elements=[Feature.ticker, Feature.date, Feature.feature_version],
            # Indexed access: `.values` would resolve to the collection's method,
            # not the column named "values".
            set_={"values": stmt.excluded["values"]},
            where=stored.is_distinct_from(stmt.excluded["values"]),
        )
        # Counted from RETURNING, as for prices: a skipped update returns no row.
        written += len(session.execute(stmt.returning(Feature.ticker)).all())
    return written


@dataclass(frozen=True)
class FeatureRefresh:
    """One market's refresh: rows computed, rows the store had to write, newest date."""

    computed: int
    written: int
    latest_date: dt.date


def refresh_features(engine: Engine, version: str) -> dict[str, FeatureRefresh]:
    """Recompute and store every market's features over its full history, one market at a time.

    One market at a time because the frame is the memory: every market in one frame, stored
    from one list of row dicts, took the nightly step to 814 MiB with three markets, against a
    1.5 GiB container. Ranks are taken within a market (`compute_features`) and every other
    feature within a ticker, so the rows are the same either way; on the stored panel of
    2026-10-22 they were identical to the last bit. The peak follows the largest market instead
    of the sum. Markets are those with active listings, as the single frame's were.
    """
    with engine.connect() as conn:
        codes: list[str] = list(
            conn.execute(
                text("SELECT DISTINCT exchange FROM universe WHERE active ORDER BY exchange")
            ).scalars()
        )
    refreshed: dict[str, FeatureRefresh] = {}
    for code in codes:
        bars = load_price_bars(engine, exchange=code)
        if bars.empty:
            continue
        frame = compute_features(bars)
        del bars
        if frame.empty:
            continue
        with Session(engine) as session, session.begin():
            written = store_features(session, frame, version)
        refreshed[code] = FeatureRefresh(len(frame), written, frame["date"].max())
        del frame
    return refreshed


def load_features(
    engine: Engine,
    version: str,
    start: dt.date | None = None,
    end: dt.date | None = None,
    exchange: str | None = None,
) -> pd.DataFrame:
    """Load stored features back into a wide frame (ticker, date, *FEATURE_COLUMNS).

    `exchange` filters via `universe`; None returns everything stored. The join is added
    only when filtering — joining unconditionally would silently drop features whose
    ticker has since left the universe, which is a different question from "which market
    is this".
    """
    params: dict[str, str | dt.date] = {"version": version}
    if exchange is None:
        query = (
            "SELECT f.ticker, f.date, f.values FROM features f "
            "WHERE f.feature_version = %(version)s"
        )
    else:
        query = (
            "SELECT f.ticker, f.date, f.values FROM features f "
            "JOIN universe u ON u.ticker = f.ticker AND u.exchange = %(exchange)s "
            "WHERE f.feature_version = %(version)s"
        )
        params["exchange"] = exchange
    if start is not None:
        query += " AND f.date >= %(start)s"
        params["start"] = start
    if end is not None:
        query += " AND f.date <= %(end)s"
        params["end"] = end
    raw = pd.read_sql(query, engine, params=params)
    if raw.empty:
        return pd.DataFrame(columns=["ticker", "date", *FEATURE_COLUMNS])
    values = pd.json_normalize(raw["values"].tolist())
    frame = pd.concat([raw[["ticker", "date"]], values[FEATURE_COLUMNS]], axis=1)
    return frame.sort_values(["date", "ticker"]).reset_index(drop=True)


def load_price_bars(
    engine: Engine,
    start: dt.date | None = None,
    end: dt.date | None = None,
    exchange: str | None = None,
    known_by: dt.datetime | None = None,
) -> pd.DataFrame:
    """Load stored bars for feature computation (active universe only).

    Carries `exchange` so cross-sectional features can be ranked within a market rather
    than across all of them. `known_by` keeps only the rows stored by that moment, which is how
    a model fitted then can be refitted later on the panel it actually saw.
    """
    clauses = ["u.active"]
    params: dict[str, dt.date | dt.datetime | str] = {}
    if exchange is not None:
        clauses.append("u.exchange = :exchange")
        params["exchange"] = exchange
    if start is not None:
        clauses.append("p.date >= :start")
        params["start"] = start
    if end is not None:
        clauses.append("p.date <= :end")
        params["end"] = end
    if known_by is not None:
        clauses.append("p.ingested_at <= :known_by")
        params["known_by"] = known_by
    query = text(
        "SELECT p.ticker, p.date, p.close, p.volume, u.exchange FROM prices p "
        "JOIN universe u ON u.ticker = p.ticker "
        f"WHERE {' AND '.join(clauses)} ORDER BY p.ticker, p.date"
    )
    with engine.connect() as conn:
        return pd.read_sql(query, conn, params=cast("Mapping[str, Any]", params))
