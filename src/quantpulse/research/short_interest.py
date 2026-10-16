"""Short interest per ticker, from the vendor's quote summary (ADR 0007).

Short interest is the number of shares sold short and not yet bought back, reported per
settlement date. It reaches the vendor a week or two after it settles, and is revised rarely, so
it is stored insert-only: the first figure seen for a settlement date is kept, and the row's
`ingested_at` says when it became known.

The two derived figures are the vendor's, not recomputed here: the share of float sold short,
and days to cover — shares short over average daily volume, how many days of ordinary trading
it would take every short seller to buy back.
"""

import datetime as dt
import logging
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from quantpulse.db import ShortInterest

logger = logging.getLogger(__name__)

Info = Mapping[str, Any]


class NoShortInterestReturned(RuntimeError):
    """No ticker came back with short interest. One ticker without it is ordinary — ETFs often
    have none — but the whole list without it means the feed changed shape or stopped."""


def _date(epoch: object) -> dt.date | None:
    if not isinstance(epoch, int | float) or epoch <= 0:
        return None
    return dt.datetime.fromtimestamp(epoch, dt.UTC).date()


def _int(value: object) -> int | None:
    return int(value) if isinstance(value, int | float) and value >= 0 else None


def _float(value: object) -> float | None:
    return float(value) if isinstance(value, int | float) and value >= 0 else None


def parse_info(ticker: str, info: Info) -> dict[str, Any] | None:
    """One row from a quote summary, or None when it carries no short interest.

    A row needs both the share count and its settlement date: a count without a date cannot be
    placed in history, and is the shape a partial vendor response takes.
    """
    shares_short = _int(info.get("sharesShort"))
    settlement = _date(info.get("dateShortInterest"))
    if shares_short is None or settlement is None:
        return None
    return {
        "ticker": ticker,
        "settlement_date": settlement,
        "shares_short": shares_short,
        "shares_short_prior": _int(info.get("sharesShortPriorMonth")),
        "prior_settlement_date": _date(info.get("sharesShortPreviousMonthDate")),
        "short_pct_float": _float(info.get("shortPercentOfFloat")),
        "days_to_cover": _float(info.get("shortRatio")),
        "float_shares": _int(info.get("floatShares")),
        "shares_outstanding": _int(info.get("sharesOutstanding")),
        "source": "yfinance",
    }


def _yfinance_info(ticker: str) -> Info:
    import yfinance as yf

    return yf.Ticker(ticker).info


def fetch_short_interest(
    tickers: Iterable[str], fetch: Callable[[str], Info] = _yfinance_info
) -> list[dict[str, Any]]:
    """Rows for every ticker the vendor has short interest for; the rest are logged and skipped.

    Raises NoShortInterestReturned when a non-empty list yields nothing at all.
    """
    tickers = list(tickers)
    rows, missing = [], []
    for ticker in tickers:
        try:
            row = parse_info(ticker, fetch(ticker))
        except Exception as exc:  # one ticker's failure must not cost the others
            logger.warning("short interest for %s failed: %s", ticker, exc)
            row = None
        if row is None:
            missing.append(ticker)
        else:
            rows.append(row)
    if missing:
        logger.info("no short interest for %d ticker(s): %s", len(missing), ", ".join(missing))
    if tickers and not rows:
        raise NoShortInterestReturned(f"no short interest for any of {len(tickers)} tickers")
    return rows


def insert_short_interest(session: Session, rows: list[dict[str, Any]]) -> int:
    """Insert rows not already stored; returns how many were new. Never rewrites a stored row."""
    if not rows:
        return 0
    stmt = insert(ShortInterest).values(rows)
    fresh = session.execute(
        stmt.on_conflict_do_nothing(
            index_elements=[ShortInterest.ticker, ShortInterest.settlement_date]
        ).returning(ShortInterest.ticker)
    )
    return len(fresh.all())
