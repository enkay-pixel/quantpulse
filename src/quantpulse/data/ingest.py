"""Daily-bar ingestion: yfinance primary, Stooq fallback, idempotent Postgres upserts.

All fetchers return a normalized long DataFrame with columns:
ticker, date, open, high, low, close, volume, source
"""

import datetime as dt
import io
import logging
from typing import cast

import httpx
import pandas as pd
import yfinance as yf
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from quantpulse.db import Price
from quantpulse.utils import chunked

logger = logging.getLogger(__name__)

BAR_COLUMNS = ["ticker", "date", "open", "high", "low", "close", "volume", "source"]
_STOOQ_URL = "https://stooq.com/q/d/l/"


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


def _stooq_symbol(ticker: str) -> str:
    return f"{ticker.lower().replace('.', '-')}.us"


def parse_stooq_csv(text: str, ticker: str) -> pd.DataFrame:
    """Parse Stooq's daily CSV export into the long bar format."""
    if not text or text.strip().lower().startswith(("no data", "<html")):
        return pd.DataFrame(columns=BAR_COLUMNS)
    frame = pd.read_csv(io.StringIO(text))
    if "Close" not in frame.columns or frame.empty:
        return pd.DataFrame(columns=BAR_COLUMNS)
    frame = frame.rename(columns=str.lower)[["date", "open", "high", "low", "close", "volume"]]
    frame = frame.dropna(subset=["close"])
    frame["date"] = pd.to_datetime(frame["date"]).dt.date
    frame["ticker"] = ticker
    frame["source"] = "stooq"
    return frame[BAR_COLUMNS]


@retry(
    retry=retry_if_exception_type(httpx.HTTPError),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    stop=stop_after_attempt(3),
    reraise=True,
)
def fetch_stooq(ticker: str, start: dt.date, end: dt.date) -> pd.DataFrame:
    params = {
        "s": _stooq_symbol(ticker),
        "d1": start.strftime("%Y%m%d"),
        "d2": end.strftime("%Y%m%d"),
        "i": "d",
    }
    response = httpx.get(_STOOQ_URL, params=params, timeout=30, follow_redirects=True)
    response.raise_for_status()
    return parse_stooq_csv(response.text, ticker)


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
    """Fetch bars for all tickers: yfinance in one batch, Stooq for whatever it misses."""
    try:
        raw = _download_yfinance(tickers, start, end)
        bars = normalize_yfinance(raw, tickers)
    except Exception:
        logger.warning("yfinance batch download failed after retries; falling back to Stooq")
        bars = pd.DataFrame(columns=BAR_COLUMNS)

    missing = sorted(set(tickers) - set(bars["ticker"].unique()))
    for ticker in missing:
        try:
            fallback = fetch_stooq(ticker, start, end)
        except httpx.HTTPError:
            logger.warning("Stooq fallback failed for %s", ticker)
            continue
        if fallback.empty:
            logger.warning("No data for %s from any source", ticker)
        else:
            bars = pd.concat([bars, fallback], ignore_index=True)

    cleaned = clean_bars(bars)
    if cleaned.empty:
        raise IngestionError(f"No usable bars fetched for {len(tickers)} tickers {start}..{end}")
    return cleaned


def upsert_prices(session: Session, bars: pd.DataFrame) -> int:
    """Idempotent insert-or-update on (ticker, date). Returns number of rows written."""
    if bars.empty:
        return 0
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
