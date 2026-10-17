"""The research watchlist (ADR 0007): names the research branch follows that the model does not.

Configured in configs/watchlist.yaml. Each name gets daily bars and, where its market has listed
options, a nightly chain, in tables of its own; the morning research run adds its short interest
and Wikipedia attention beside the universe's. A name in the universe is refused: the model's
tables keep their foreign key to the universe, and the watchlist must never become a way round it.
"""

import datetime as dt
import logging
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yaml
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from quantpulse.config import get_settings
from quantpulse.data.calendar import EXCHANGES, get_exchange, is_post_close, market_today
from quantpulse.data.cleaning import repair_price_units
from quantpulse.data.ingest import fetch_daily_bars
from quantpulse.db import UniverseMember, WatchlistName, WatchlistOptionQuote, WatchlistPrice
from quantpulse.options.ingest import (
    OffHoursSnapshotError,
    _fetch_ticker_chain,
    _rows_for_ticker,
    _upsert,
)
from quantpulse.utils import chunked

logger = logging.getLogger(__name__)

ASSET_TYPES = ("stock", "etf")


class WatchlistError(ValueError):
    """The watchlist file is malformed, or names a ticker the model already follows."""


class NoWatchlistChains(RuntimeError):
    """Not one watchlist name with listed options returned a chain.

    One name without a chain is ordinary. All of them without one is the same observation that
    fails the universe's capture, and the marks cannot be fetched again later.
    """


@dataclass(frozen=True)
class WatchName:
    ticker: str
    exchange: str
    asset_type: str
    why: str
    wikipedia: str | None = None

    @property
    def has_options(self) -> bool:
        return get_exchange(self.exchange).has_options


def load_watchlist(path: Path | None = None) -> list[WatchName]:
    """The configured names, validated: a known market, a known asset type, a reason, no repeats."""
    path = path or get_settings().quantpulse_watchlist_file
    data = yaml.safe_load(path.read_text()) or {}
    entries = (data.get("names") or []) if isinstance(data, dict) else []
    names: list[WatchName] = []
    for i, raw in enumerate(entries):
        if not isinstance(raw, dict):
            raise WatchlistError(f"entry {i} is not a mapping")
        ticker = str(raw.get("ticker") or "").strip()
        exchange = str(raw.get("exchange") or "").strip()
        asset_type = str(raw.get("asset_type") or "stock").strip()
        why = " ".join(str(raw.get("why") or "").split())
        wikipedia = raw.get("wikipedia")
        if not ticker:
            raise WatchlistError(f"entry {i} has no ticker")
        if exchange not in EXCHANGES:
            raise WatchlistError(f"{ticker}: exchange must be one of {sorted(EXCHANGES)}")
        if asset_type not in ASSET_TYPES:
            raise WatchlistError(f"{ticker}: asset_type must be one of {ASSET_TYPES}")
        if not why:
            raise WatchlistError(f"{ticker}: say why it is followed, in a sentence")
        names.append(
            WatchName(ticker, exchange, asset_type, why, str(wikipedia) if wikipedia else None)
        )
    tickers = [n.ticker for n in names]
    repeats = sorted({t for t in tickers if tickers.count(t) > 1})
    if repeats:
        raise WatchlistError(f"listed more than once: {repeats}")
    return names


def sync_watchlist(session: Session, names: list[WatchName]) -> dict[str, Any]:
    """Make the `watchlist` table match the file. A name already in the universe is refused.

    A removed name's row goes, but its bars and chains stay: the marts follow the current list,
    and the history is there if the name comes back.
    """
    universe = set(session.scalars(select(UniverseMember.ticker)))
    overlap = sorted({n.ticker for n in names} & universe)
    if overlap:
        raise WatchlistError(
            f"already in the model's universe, so not a watchlist name: {overlap}. "
            "Remove them from configs/watchlist.yaml."
        )
    if names:
        stmt = pg_insert(WatchlistName).values(
            [
                {
                    "ticker": n.ticker,
                    "exchange": n.exchange,
                    "asset_type": n.asset_type,
                    "why": n.why,
                    "wikipedia": n.wikipedia,
                }
                for n in names
            ]
        )
        session.execute(
            stmt.on_conflict_do_update(
                index_elements=[WatchlistName.ticker],
                set_={
                    c: getattr(stmt.excluded, c)
                    for c in ("exchange", "asset_type", "why", "wikipedia")
                },
            )
        )
    removed = sorted(set(session.scalars(select(WatchlistName.ticker))) - {n.ticker for n in names})
    if removed:
        session.execute(delete(WatchlistName).where(WatchlistName.ticker.in_(removed)))
    return {"names": len(names), "removed": removed}


def upsert_watchlist_prices(session: Session, bars: pd.DataFrame) -> int:
    """Insert or update each (ticker, date), after the same unit repair `prices` gets."""
    if bars.empty:
        return 0
    bars, _ = repair_price_units(bars)
    records = bars[["ticker", "date", "open", "high", "low", "close", "volume"]].to_dict(
        orient="records"
    )
    for chunk in chunked(records):
        stmt = pg_insert(WatchlistPrice).values(list(chunk))
        session.execute(
            stmt.on_conflict_do_update(
                index_elements=[WatchlistPrice.ticker, WatchlistPrice.date],
                set_={
                    c: getattr(stmt.excluded, c) for c in ("open", "high", "low", "close", "volume")
                },
            )
        )
    return len(records)


def refresh_watchlist_prices(
    session: Session,
    names: list[WatchName],
    end: dt.date | None = None,
    fetch: Callable[[list[str], dt.date, dt.date], pd.DataFrame] = fetch_daily_bars,
) -> int:
    """Refetch every name's full history and store it, so a later adjustment is picked up."""
    if not names:
        return 0
    start = dt.date.fromisoformat(get_settings().quantpulse_history_start)
    bars = fetch([n.ticker for n in names], start, end or dt.date.today())
    return upsert_watchlist_prices(session, bars)


def capture_watchlist_chains(
    session_factory: Callable[[], AbstractContextManager[Session]],
    names: list[WatchName],
    snapshot_date: dt.date | None = None,
    *,
    force: bool = False,
) -> int:
    """Snapshot each optioned name's chain, in the universe's band, committing per name.

    The same post-close gate as the universe's capture: off-hours marks are stale and the upsert
    would overwrite a good evening's rows.
    """
    optioned = [n for n in names if n.has_options]
    if not optioned:
        return 0
    if not force and not is_post_close():
        raise OffHoursSnapshotError(
            "Refusing to snapshot watchlist chains before the close — vendor marks are stale "
            "off-hours. Re-run after 16:00 ET on a trading day."
        )
    settings = get_settings()
    snapshot_date = snapshot_date or market_today()
    total = fetched = 0
    for name in optioned:
        try:
            spot, chains = _fetch_ticker_chain(name.ticker, settings.quantpulse_option_expiries)
        except Exception:
            logger.warning("Watchlist chain fetch failed for %s", name.ticker, exc_info=True)
            continue
        if spot is None or not chains:
            logger.info("No option chain for watchlist name %s", name.ticker)
            continue
        fetched += 1
        rows = _rows_for_ticker(
            name.ticker,
            spot,
            chains,
            snapshot_date,
            settings.quantpulse_option_moneyness,
            settings.quantpulse_risk_free_rate,
        )
        with session_factory() as session:
            total += _upsert(session, rows, WatchlistOptionQuote)
    if not fetched:
        raise NoWatchlistChains(
            f"No chain returned for any of {len(optioned)} watchlist names on {snapshot_date}; "
            "nothing was written. Check the network first."
        )
    return total


def short_interest_tickers(session: Session) -> list[str]:
    """The names to fetch short interest for: the universe's optioned names and the watchlist's US
    names. One definition, so the morning job and the CLI fetch the same set."""
    from quantpulse.data.universe import options_tickers

    return options_tickers(session) + [n.ticker for n in load_watchlist() if n.has_options]


def attention_titles() -> dict[str, str]:
    """Each followed stock's Wikipedia title: the universe's from configs/attention.yaml and the
    watchlist's own. One definition, so the morning job and the CLI count the same articles."""
    from quantpulse.research.attention import load_titles

    titles = load_titles(get_settings().quantpulse_attention_file)
    return titles | {n.ticker: n.wikipedia for n in load_watchlist() if n.wikipedia}
