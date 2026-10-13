"""Daily-bar ingestion from yfinance, with idempotent Postgres upserts.

All fetchers return a normalized long DataFrame with columns:
ticker, date, open, high, low, close, volume, source
"""

import datetime as dt
import logging
from typing import cast

import pandas as pd
import yfinance as yf
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from quantpulse.data.cleaning import repair_price_units
from quantpulse.db import Price
from quantpulse.utils import chunked

logger = logging.getLogger(__name__)

BAR_COLUMNS = ["ticker", "date", "open", "high", "low", "close", "volume", "source"]


class IngestionError(RuntimeError):
    pass


@retry(
    retry=retry_if_exception_type(Exception),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    stop=stop_after_attempt(3),
    reraise=True,
)
def _download_yfinance(tickers: list[str], start: dt.date, end: dt.date) -> pd.DataFrame:
    # yfinance treats `end` as exclusive; add a day so the range is inclusive.
    return yf.download(
        tickers,
        start=str(start),
        end=str(end + dt.timedelta(days=1)),
        group_by="ticker",
        auto_adjust=True,
        threads=True,
        progress=False,
    )


def normalize_yfinance(raw: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    """Flatten yfinance's (ticker, field) wide format into the long bar format."""
    frames: list[pd.DataFrame] = []
    for ticker in tickers:
        if isinstance(raw.columns, pd.MultiIndex):
            if ticker not in raw.columns.get_level_values(0):
                continue
            block = cast(pd.DataFrame, raw[ticker])
        else:  # single-ticker download without MultiIndex
            block = raw
        block = block.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]]
        block = block.dropna(subset=["close"])
        if block.empty:
            continue
        frame = block.reset_index().rename(columns={"Date": "date", "index": "date"})
        frame["date"] = pd.to_datetime(frame["date"]).dt.date
        frame["ticker"] = ticker
        frame["source"] = "yfinance"
        frames.append(frame[BAR_COLUMNS])
    if not frames:
        return pd.DataFrame(columns=BAR_COLUMNS)
    return pd.concat(frames, ignore_index=True)


def clean_bars(df: pd.DataFrame) -> pd.DataFrame:
    """Drop rows that would violate DB constraints; enforce dtypes and key uniqueness."""
    if df.empty:
        return df
    df = df.dropna(subset=["open", "high", "low", "close", "volume"]).copy()
    price_cols = ["open", "high", "low", "close"]
    df = df[(df[price_cols] > 0).all(axis=1) & (df["high"] >= df["low"]) & (df["volume"] >= 0)]
    df["volume"] = df["volume"].astype("int64")
    df = df.drop_duplicates(subset=["ticker", "date"], keep="last")
    return df.reset_index(drop=True)


def fetch_daily_bars(tickers: list[str], start: dt.date, end: dt.date) -> pd.DataFrame:
    """Fetch bars for all tickers from yfinance, in one batch.

    There is no second source, deliberately. A ticker the batch does not return is left absent
    rather than filled from another vendor: bars from two vendors can differ in units and in
    how they are adjusted, and a missing bar is usually a late one, which a later re-fetch from
    the same vendor recovers. The absence is logged here by name and reported by the post-close
    check. A batch that fails outright, or returns nothing usable, raises, so the run fails
    loudly and the catch-up sensor retries it.
    """
    try:
        raw = _download_yfinance(tickers, start, end)
        bars = normalize_yfinance(raw, tickers)
    except Exception as exc:
        raise IngestionError(
            f"yfinance batch failed after retries for {len(tickers)} tickers {start}..{end}"
        ) from exc

    missing = sorted(set(tickers) - set(bars["ticker"].unique()))
    if missing:
        logger.warning(
            "yfinance returned no bars for %d of %d tickers %s..%s: %s",
            len(missing),
            len(tickers),
            start,
            end,
            ", ".join(missing),
        )

    cleaned = clean_bars(bars)
    if cleaned.empty:
        raise IngestionError(f"No usable bars fetched for {len(tickers)} tickers {start}..{end}")
    return cleaned


def upsert_prices(session: Session, bars: pd.DataFrame) -> int:
    """Idempotent insert-or-update on (ticker, date). Returns number of rows written.

    Vendor unit glitches are repaired first (see data.cleaning): Yahoo intermittently
    reports a JSE close in Rand rather than cents, which reads as a -99% day followed by
    a +100x day. Needs neighbouring rows to judge, so this is a no-op on the single-day
    ingest and does its work on backfills and sweeps.
    """
    if bars.empty:
        return 0
    bars, _ = repair_price_units(bars)
    records = bars[BAR_COLUMNS].to_dict(orient="records")
    for chunk in chunked(records):
        stmt = pg_insert(Price).values(list(chunk))
        stmt = stmt.on_conflict_do_update(
            index_elements=[Price.ticker, Price.date],
            set_={
                "open": stmt.excluded.open,
                "high": stmt.excluded.high,
                "low": stmt.excluded.low,
                "close": stmt.excluded.close,
                "volume": stmt.excluded.volume,
                "source": stmt.excluded.source,
            },
        )
        session.execute(stmt)
    return len(records)
