"""Snapshot live option chains from yfinance, enrich with Black-Scholes Greeks, and
upsert into `option_quotes`. There is no free historical chain data, so this asset is
what *builds* our options history — one snapshot per run, accumulating going forward.
"""

import datetime as dt
import logging
from collections.abc import Callable
from contextlib import AbstractContextManager

import pandas as pd
import yfinance as yf
from sqlalchemy import Engine, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from quantpulse.config import get_settings
from quantpulse.db import OptionQuote
from quantpulse.options.pricing import OptionType, black_scholes, years_to_expiry
from quantpulse.utils import chunked

logger = logging.getLogger(__name__)

QUOTE_COLUMNS = [
    "snapshot_date",
    "ticker",
    "expiry",
    "strike",
    "option_type",
    "underlying_close",
    "bid",
    "ask",
    "last_price",
    "volume",
    "open_interest",
    "implied_volatility",
    "in_the_money",
    "theo_value",
    "delta",
    "gamma",
    "theta",
    "vega",
]
_PK_COLUMNS = {"snapshot_date", "ticker", "expiry", "strike", "option_type"}


@retry(
    retry=retry_if_exception_type(Exception),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def _fetch_ticker_chain(
    ticker: str, n_expiries: int
) -> tuple[float | None, list[tuple[dt.date, pd.DataFrame, pd.DataFrame]]]:
    """Return (spot, [(expiry, calls, puts)]) for the nearest `n_expiries` expiries."""
    t = yf.Ticker(ticker)
    expiries = list(t.options)[:n_expiries]
    if not expiries:
        return None, []
    try:
        spot = float(t.fast_info.last_price)
    except Exception:
        spot = None
    chains = []
    for exp in expiries:
        chain = t.option_chain(exp)
        chains.append((dt.date.fromisoformat(exp), chain.calls, chain.puts))
    return spot, chains


def _rows_for_ticker(
    ticker: str,
    spot: float,
    chains: list[tuple[dt.date, pd.DataFrame, pd.DataFrame]],
    snapshot_date: dt.date,
    moneyness: float,
    rate: float,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    lo, hi = spot * (1 - moneyness), spot * (1 + moneyness)
    for expiry, calls, puts in chains:
        t_years = years_to_expiry((expiry - snapshot_date).days)
        kind: OptionType
        for kind, frame in (("call", calls), ("put", puts)):
            near = frame[(frame["strike"] >= lo) & (frame["strike"] <= hi)]
            for row in near.to_dict(orient="records"):
                iv = float(row["impliedVolatility"])
                strike = float(row["strike"])
                greeks = black_scholes(spot, strike, t_years, rate, iv, kind)
                rows.append(
                    {
                        "snapshot_date": snapshot_date,
                        "ticker": ticker,
                        "expiry": expiry,
                        "strike": strike,
                        "option_type": kind,
                        "underlying_close": spot,
                        "bid": float(row["bid"]) if pd.notna(row["bid"]) else None,
                        "ask": float(row["ask"]) if pd.notna(row["ask"]) else None,
                        "last_price": (
                            float(row["lastPrice"]) if pd.notna(row["lastPrice"]) else None
                        ),
                        "volume": int(row["volume"]) if pd.notna(row["volume"]) else 0,
                        "open_interest": (
                            int(row["openInterest"]) if pd.notna(row["openInterest"]) else 0
                        ),
                        "implied_volatility": iv,
                        "in_the_money": bool(row["inTheMoney"]),
                        "theo_value": greeks.price,
                        "delta": greeks.delta,
                        "gamma": greeks.gamma,
                        "theta": greeks.theta,
                        "vega": greeks.vega,
                    }
                )
    return rows


def dedupe_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Collapse duplicate (snapshot, ticker, expiry, strike, type) keys.

    Yahoo chains can list two contracts at the same strike/expiry/type — a standard
    contract plus an adjusted one (post-split/special-dividend). They collide in a
    single ON CONFLICT batch, so keep the more liquid (higher open interest) row,
    which is the standard contract.
    """
    best: dict[tuple[object, ...], dict[str, object]] = {}
    for row in rows:
        key = tuple(row[c] for c in ("snapshot_date", "ticker", "expiry", "strike", "option_type"))
        current = best.get(key)
        if current is None or int(row["open_interest"]) > int(current["open_interest"]):  # type: ignore[call-overload]
            best[key] = row
    return list(best.values())


def upsert_quotes(session: Session, rows: list[dict[str, object]]) -> int:
    """Idempotent upsert of option quotes (deduped on the primary key first)."""
    if not rows:
        return 0
    deduped = dedupe_rows(rows)
    if len(deduped) != len(rows):
        logger.info("Dropped %d duplicate contracts (adjusted)", len(rows) - len(deduped))

    updatable = [c for c in QUOTE_COLUMNS if c not in _PK_COLUMNS]
    for chunk in chunked(deduped):
        stmt = pg_insert(OptionQuote).values(list(chunk))
        stmt = stmt.on_conflict_do_update(
            index_elements=[
                OptionQuote.snapshot_date,
                OptionQuote.ticker,
                OptionQuote.expiry,
                OptionQuote.strike,
                OptionQuote.option_type,
            ],
            set_={c: getattr(stmt.excluded, c) for c in updatable},
        )
        session.execute(stmt)
    return len(deduped)


def snapshot_option_chains(
    session_factory: Callable[[], AbstractContextManager[Session]],
    tickers: list[str],
    snapshot_date: dt.date | None = None,
) -> int:
    """Fetch, enrich, and upsert an option-chain snapshot, COMMITTING PER TICKER.

    A full universe takes ~10 minutes of network calls; committing per ticker means an
    interruption (timeout, crash, rate limit) keeps everything already fetched and the
    run is simply resumable. Per-ticker failures are logged and skipped.
    """
    settings = get_settings()
    snapshot_date = snapshot_date or dt.date.today()
    total = 0
    for ticker in tickers:
        try:
            spot, chains = _fetch_ticker_chain(ticker, settings.quantpulse_option_expiries)
        except Exception:
            logger.warning("Option chain fetch failed for %s", ticker, exc_info=True)
            continue
        if spot is None or not chains:
            logger.info("No option chain for %s", ticker)
            continue
        rows = _rows_for_ticker(
            ticker,
            spot,
            chains,
            snapshot_date,
            settings.quantpulse_option_moneyness,
            settings.quantpulse_risk_free_rate,
        )
        try:
            with session_factory() as session:  # one transaction per ticker
                written = upsert_quotes(session, rows)
        except Exception:
            logger.warning("Option quote upsert failed for %s", ticker, exc_info=True)
            continue
        total += written
        logger.info("%s: %d option quotes", ticker, written)

    logger.info("Snapshot %s: wrote %d option quotes", snapshot_date, total)
    return total


def latest_snapshot_date(engine: Engine) -> dt.date | None:
    with engine.connect() as conn:
        return conn.execute(text("SELECT max(snapshot_date) FROM option_quotes")).scalar()
