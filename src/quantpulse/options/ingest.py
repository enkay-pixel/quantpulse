"""Snapshot live option chains from yfinance, enrich with Black-Scholes Greeks, and
upsert into `option_quotes`. There is no free historical chain data, so this asset is
what *builds* our options history — one snapshot per run, accumulating going forward.
"""

import datetime as dt
import logging
from collections.abc import Callable, Hashable, Mapping
from contextlib import AbstractContextManager
from typing import Any

import pandas as pd
import yfinance as yf
from sqlalchemy import Engine, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from quantpulse.config import get_settings
from quantpulse.data.calendar import is_post_close, market_today
from quantpulse.db import HeldOptionQuote, OptionQuote
from quantpulse.options.pricing import OptionType, black_scholes, years_to_expiry
from quantpulse.utils import chunked

logger = logging.getLogger(__name__)


class OffHoursSnapshotError(RuntimeError):
    """A snapshot was attempted while the vendor's marks are not yet meaningful.

    Raised rather than returning 0, because a silent no-op is indistinguishable from
    "the feed had nothing today" — the Dagster asset would materialize green and the
    evening's real snapshot would never be chased.
    """


class EmptyUniverseSnapshotError(RuntimeError):
    """No chain came back for any ticker in the universe.

    The case OffHoursSnapshotError's docstring names as the ambiguity, closed from the other
    side. One ticker without a chain is ordinary; the whole universe without one is not, and
    the two are indistinguishable in a return value of 0.

    Names the observation, not a cause. An unreachable network, a vendor outage and a
    credential problem are identical from inside the loop, and the incident log records
    exactly that trap: the loss on 2026-08-11 was a local internet outage, and an error that
    blamed the feed would have sent the reader to check the wrong thing.

    Worth an exception rather than a warning because option marks cannot be refetched: a
    session missed is a session gone. Failing puts it in pipeline_alerts and turns the asset
    red the same night, instead of the clean exit that let three repair runs report SUCCESS
    having captured zero rows.
    """


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


#: The contracts the paper options book holds, by ticker: (expiry, strike, option_type).
HeldContracts = Mapping[str, set[tuple[dt.date, float, str]]]


def _quote_row(
    ticker: str,
    spot: float,
    expiry: dt.date,
    kind: OptionType,
    row: Mapping[Hashable, Any],
    snapshot_date: dt.date,
    rate: float,
) -> dict[str, object]:
    iv = float(row["impliedVolatility"])
    strike = float(row["strike"])
    greeks = black_scholes(
        spot, strike, years_to_expiry((expiry - snapshot_date).days), rate, iv, kind
    )
    return {
        "snapshot_date": snapshot_date,
        "ticker": ticker,
        "expiry": expiry,
        "strike": strike,
        "option_type": kind,
        "underlying_close": spot,
        "bid": float(row["bid"]) if pd.notna(row["bid"]) else None,
        "ask": float(row["ask"]) if pd.notna(row["ask"]) else None,
        "last_price": float(row["lastPrice"]) if pd.notna(row["lastPrice"]) else None,
        "volume": int(row["volume"]) if pd.notna(row["volume"]) else 0,
        "open_interest": int(row["openInterest"]) if pd.notna(row["openInterest"]) else 0,
        "implied_volatility": iv,
        "in_the_money": bool(row["inTheMoney"]),
        "theo_value": greeks.price,
        "delta": greeks.delta,
        "gamma": greeks.gamma,
        "theta": greeks.theta,
        "vega": greeks.vega,
    }


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
        kind: OptionType
        for kind, frame in (("call", calls), ("put", puts)):
            near = frame[(frame["strike"] >= lo) & (frame["strike"] <= hi)]
            for row in near.to_dict(orient="records"):
                rows.append(_quote_row(ticker, spot, expiry, kind, row, snapshot_date, rate))
    return rows


def held_rows(
    ticker: str,
    spot: float,
    chains: list[tuple[dt.date, pd.DataFrame, pd.DataFrame]],
    snapshot_date: dt.date,
    held: set[tuple[dt.date, float, str]],
    rate: float,
) -> tuple[list[dict[str, object]], set[tuple[dt.date, float, str]]]:
    """The held contracts found in a downloaded chain, at any strike, and those not found.

    No extra download is needed: a held expiry was one of the nearest captured when the spread
    opened, and only gets nearer. A contract not found is reported, since its spread then falls
    back to its last quote.
    """
    rows: list[dict[str, object]] = []
    for expiry, calls, puts in chains:
        kind: OptionType
        for kind, frame in (("call", calls), ("put", puts)):
            strikes = {k for e, k, t in held if e == expiry and t == kind}
            if not strikes:
                continue
            for row in frame[frame["strike"].isin(strikes)].to_dict(orient="records"):
                rows.append(_quote_row(ticker, spot, expiry, kind, row, snapshot_date, rate))
    found = {(r["expiry"], r["strike"], r["option_type"]) for r in rows}
    return rows, {c for c in held if c not in found}


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


def _upsert(session: Session, rows: list[dict[str, object]], table: Any) -> int:
    if not rows:
        return 0
    deduped = dedupe_rows(rows)
    if len(deduped) != len(rows):
        logger.info("Dropped %d duplicate contracts (adjusted)", len(rows) - len(deduped))

    updatable = [c for c in QUOTE_COLUMNS if c not in _PK_COLUMNS]
    for chunk in chunked(deduped):
        stmt = pg_insert(table).values(list(chunk))
        stmt = stmt.on_conflict_do_update(
            index_elements=[
                table.snapshot_date,
                table.ticker,
                table.expiry,
                table.strike,
                table.option_type,
            ],
            set_={c: getattr(stmt.excluded, c) for c in updatable},
        )
        session.execute(stmt)
    return len(deduped)


def upsert_quotes(session: Session, rows: list[dict[str, object]]) -> int:
    """Idempotent upsert of option quotes (deduped on the primary key first)."""
    return _upsert(session, rows, OptionQuote)


def upsert_held_quotes(session: Session, rows: list[dict[str, object]]) -> int:
    """Idempotent upsert of the held contracts' quotes into their own table."""
    return _upsert(session, rows, HeldOptionQuote)


def snapshot_option_chains(
    session_factory: Callable[[], AbstractContextManager[Session]],
    tickers: list[str],
    snapshot_date: dt.date | None = None,
    *,
    force: bool = False,
    held: HeldContracts | None = None,
) -> int:
    """Fetch, enrich, and upsert an option-chain snapshot, COMMITTING PER TICKER.

    `held` names the contracts the paper options book holds. They are written to
    `held_option_quotes` at any distance from spot, from the same download, in the same
    transaction as the ticker's band; the return value counts `option_quotes` rows only.

    A full universe takes ~10 minutes of network calls; committing per ticker means an
    interruption (timeout, crash, rate limit) keeps everything already fetched and the
    run is simply resumable. Per-ticker failures are logged and skipped.

    Refuses to run outside post-close (`OffHoursSnapshotError`) unless `force=True`,
    which exists only for deliberate off-hours testing against a throwaway
    `snapshot_date`. Never force against a real trading date.
    """
    # The gate lives HERE, in the data layer, so every caller inherits it: the CLI, the
    # Dagster asset, the repair sensor's job, and whatever gets added next. It used to
    # sit only in the sensor, which meant `quantpulse options-snapshot` at 08:00 — or a
    # manual materialize from the Dagster UI — captured pre-market chains (≈2.1% IV vs
    # ≈33% post-close) and, because the upsert is keyed on (snapshot_date, ticker, ...),
    # OVERWROTE good post-close rows for every ticker it reached. One snapshot_date, two
    # incompatible qualities of data, in a dataset that cannot be rebuilt.
    #
    # Checked against the default (XNYS) clock because XNYS is the only exchange with
    # has_options (data/calendar.py) — so it is the only market whose chains this can
    # actually capture, whatever else is in `tickers`.
    #
    # Deliberately independent of `snapshot_date`: the marks always come from the vendor
    # NOW, so what makes them trustworthy is the wall clock, not the date we stamp.
    if not force and not is_post_close():
        raise OffHoursSnapshotError(
            "Refusing to snapshot option chains before the close — vendor IV is stale "
            "off-hours (≈2.1% vs ≈33% post-close) and this upsert would overwrite good "
            "post-close rows. Re-run after 16:00 ET on a trading day, or pass --force "
            "(testing only)."
        )

    settings = get_settings()
    # Exchange time, not the container's UTC clock — see calendar.market_today().
    snapshot_date = snapshot_date or market_today()
    total = 0
    # Counted separately from `total`: a ticker can return a chain and still write nothing
    # when every strike falls outside the moneyness band. That is a real snapshot with no
    # rows; a vendor outage is no snapshot at all, and only the second is worth failing on.
    fetched = 0
    for ticker in tickers:
        try:
            spot, chains = _fetch_ticker_chain(ticker, settings.quantpulse_option_expiries)
        except Exception:
            logger.warning("Option chain fetch failed for %s", ticker, exc_info=True)
            continue
        if spot is None or not chains:
            logger.info("No option chain for %s", ticker)
            continue
        fetched += 1
        rows = _rows_for_ticker(
            ticker,
            spot,
            chains,
            snapshot_date,
            settings.quantpulse_option_moneyness,
            settings.quantpulse_risk_free_rate,
        )
        kept, missing = held_rows(
            ticker,
            spot,
            chains,
            snapshot_date,
            (held or {}).get(ticker, set()),
            settings.quantpulse_risk_free_rate,
        )
        if missing:
            logger.warning(
                "%s: %d held contracts not in the chain, marked at their last quote: %s",
                ticker,
                len(missing),
                sorted(missing),
            )
        try:
            with session_factory() as session:  # one transaction per ticker
                written = upsert_quotes(session, rows)
                if kept:
                    upsert_held_quotes(session, kept)
        except Exception:
            logger.warning("Option quote upsert failed for %s", ticker, exc_info=True)
            continue
        total += written
        logger.info("%s: %d option quotes, %d held", ticker, written, len(kept))

    # Guarded on `tickers` so an empty universe stays a legitimate no-op rather than an
    # outage — there is nothing to be served when nothing was asked for.
    if tickers and not fetched:
        raise EmptyUniverseSnapshotError(
            f"No option chain returned for any of {len(tickers)} tickers on "
            f"{snapshot_date}. Nothing was written, and these marks cannot be captured "
            "later. Cause is not determined here — connectivity, the vendor and credentials "
            "all look the same from inside the loop; check the network first."
        )

    logger.info("Snapshot %s: wrote %d option quotes", snapshot_date, total)
    return total


def latest_snapshot_date(engine: Engine) -> dt.date | None:
    with engine.connect() as conn:
        return conn.execute(text("SELECT max(snapshot_date) FROM option_quotes")).scalar()
