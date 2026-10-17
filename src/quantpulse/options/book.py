"""The paper options book: the stock signal held through spreads instead of shares (ADR 0008).

It varies one thing from the 21-session share book, the instrument. Each cohort opens on that
book's rebalance dates, on the same names, read from its stored positions: a bull call spread for
each long name, a bear put spread for each short one, with the strike rule the Options tab
illustrates. Each closes at the next rebalance, so both books hold for the same window.

Prices are the pessimistic side of every quote — buy at the ask, sell at the bid — with commission
per contract per leg. A contract missing from a day's snapshot is valued at intrinsic, clamped to
the spread's width, and a spread whose expiry passes settles at intrinsic. Each cohort risks
RISK_BUDGET of equity, split equally across its spreads; a debit spread cannot lose more than its
debit, so neither can the cohort.

The simulation reads the market through `Market`, so the same code runs against the database and
against frames in a test.
"""

import bisect
import datetime as dt
import logging
import math
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Any, Protocol, cast

import pandas as pd
from sqlalchemy import Engine, delete, insert, text
from sqlalchemy.orm import Session

from quantpulse.data.calendar import get_exchange, trading_days
from quantpulse.db import OptionBookDay, OptionBookPosition
from quantpulse.ml.portfolio import HORIZON_BOOK
from quantpulse.options.strategy import Direction, spread_strikes
from quantpulse.utils import chunked

logger = logging.getLogger(__name__)

BOOK = "spread_horizon"
#: The share book this one shadows; the holding window is its rebalance interval.
SHARE_BOOK = HORIZON_BOOK.variant
HOLD_SESSIONS = HORIZON_BOOK.rebalance_days
#: Share of equity each cohort puts at risk. A convention: results scale with it.
RISK_BUDGET = 0.10
COMMISSION_PER_LEG = 0.65  # dollars per contract per leg, each way
CONTRACT = 100
#: Cohorts opened from this date are live; earlier ones are a replay of rules fixed before any
#: options P&L was seen. If the rules change, this moves with them.
LIVE_SINCE = dt.date(2026, 10, 19)
#: A quote a trader could deal at: a real bid below the ask, a gap no wider than this share of the
#: midpoint, and at least this many contracts open. After-hours quotes on thin strikes are often
#: stale or absurd — a put bid 2.50 and asked 10.00 with five contracts open — and paying such an
#: ask, or selling into such a bid, books a loss no real trade would take.
#: The gap may also be up to MAX_QUOTE_CENTS wide whatever the price, or every cheap option fails:
#: 0.50 bid / 0.70 asked is an ordinary market and 33% of its midpoint. Measured on three snapshot
#: days, 84% of quotes with a bid pass the combined rule; the exchanges' market-maker width table,
#: written for trading hours, passes only 41% of these after-hours quotes.
MAX_QUOTE_WIDTH = 0.25
MAX_QUOTE_CENTS = 0.25
MIN_OPEN_INTEREST = 10


@dataclass(frozen=True)
class Cohort:
    opened: dt.date
    closes: dt.date | None  # the share book's next rebalance; None while it is still open
    longs: tuple[str, ...]
    shorts: tuple[str, ...]
    model_version: str | None


class Market(Protocol):
    def chain(self, day: dt.date, tickers: list[str]) -> pd.DataFrame:
        """ticker, expiry, strike, option_type, bid, ask, open_interest, underlying_close."""
        ...

    def legs(
        self, contracts: list[tuple[str, dt.date, float, str]], start: dt.date, end: dt.date
    ) -> pd.DataFrame:
        """snapshot_date, ticker, expiry, strike, option_type, bid, ask, underlying_close."""
        ...

    def closes(self, tickers: list[str], start: dt.date, end: dt.date) -> pd.DataFrame:
        """ticker, date, close."""
        ...

    def snapshot_dates(self, start: dt.date, end: dt.date) -> list[dt.date]: ...


def _price(value: object) -> float | None:
    """A quote as a number, or None when it is missing — pandas reads a missing quote as NaN."""
    if value is None or not isinstance(value, int | float) or math.isnan(value) or value < 0:
        return None
    return float(value)


def sound(bid: object, ask: object) -> bool:
    """Whether a quote is one a trader could deal at: a real bid, below the ask, not too wide."""
    b, a = _price(bid), _price(ask)
    if not b or not a or a <= b:
        return False
    return a - b <= MAX_QUOTE_CENTS or (a - b) / ((a + b) / 2) <= MAX_QUOTE_WIDTH


def entry_debit(long_ask: object, short_bid: object, width: float) -> float | None:
    """What opening costs per share: the long leg at its ask, less the short leg at its bid.

    A short leg with no bid is sold for nothing, which is what selling into no bid gets. None when
    the long leg has no ask, or the result is not a sane debit: at or above the width would pay
    more than the spread can ever be worth.
    """
    ask = _price(long_ask)
    if not ask:
        return None
    debit = ask - (_price(short_bid) or 0.0)
    return debit if 0 < debit < width else None


def liquidation_value(long_bid: object, short_ask: object, width: float) -> float | None:
    """What closing would raise per share: the long leg at its bid, less buying back the short leg
    at its ask, clamped to [0, width]. None when either quote is missing, so the caller falls back
    to intrinsic rather than reading a gap in the data as a worthless spread."""
    bid, ask = _price(long_bid), _price(short_ask)
    if bid is None or not ask:
        return None
    return min(max(bid - ask, 0.0), width)


def intrinsic(option_type: str, spot: float, long_strike: float, short_strike: float) -> float:
    """The spread's value at expiry, per share."""
    if option_type == "call":
        return min(max(spot - long_strike, 0.0), short_strike - long_strike)
    return min(max(long_strike - spot, 0.0), long_strike - short_strike)


def choose_expiry(expiries: list[dt.date], due: dt.date) -> dt.date | None:
    """The first expiry on or after the cohort is due to close; None if none reaches it."""
    later = [e for e in expiries if e >= due]
    return min(later) if later else None


def due_date(opened: dt.date, exchange: str) -> dt.date:
    """When a cohort opened today is expected to close: HOLD_SESSIONS sessions on. Projected from
    the calendar, so the choice of expiry uses nothing a trader would not have known."""
    days = trading_days(
        opened + dt.timedelta(days=1), opened + dt.timedelta(days=2 * HOLD_SESSIONS + 30), exchange
    )
    return days[HOLD_SESSIONS - 1]


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """A frame's rows as plain dicts — what the simulation reads, so it never depends on how
    pandas types a row."""
    return cast("list[dict[str, Any]]", frame.to_dict("records"))


def cohorts_from_book(rows: pd.DataFrame) -> list[Cohort]:
    """Cohorts from the share book's stored days: a new cohort wherever its positions changed.

    rows: date, positions (ticker -> weight), model_version, sorted by date.
    """
    cohorts: list[Cohort] = []
    previous: dict[str, float] | None = None
    for row in _records(rows):
        positions: dict[str, float] = dict(row["positions"])
        day: dt.date = row["date"]
        if positions != previous:
            longs = tuple(sorted(t for t, w in positions.items() if w > 0))
            shorts = tuple(sorted(t for t, w in positions.items() if w < 0))
            if cohorts:
                cohorts[-1] = replace(cohorts[-1], closes=day)
            cohorts.append(Cohort(day, None, longs, shorts, row["model_version"]))
            previous = positions
    return cohorts


@dataclass
class _Spread:
    ticker: str
    side: str
    option_type: str
    expiry: dt.date
    long_strike: float
    short_strike: float
    debit: float
    quantity: float = 0.0
    mark: float = 0.0
    mark_date: dt.date | None = None
    basis: str = "quote"
    #: The last sound (bid, ask) seen for each leg, by strike — what a leg is valued at on a day
    #: its own quote is missing or unsound.
    last: dict[float, tuple[float, float]] = field(default_factory=dict)

    @property
    def width(self) -> float:
        return abs(self.short_strike - self.long_strike)


def _open_cohort(
    cohort: Cohort, market: Market, exchange: str
) -> tuple[list[_Spread], list[dict[str, Any]]]:
    """Spreads that can be opened, and a skip row for each name that cannot, with the reason."""
    names = list(cohort.longs) + list(cohort.shorts)
    chain = market.chain(cohort.opened, names)
    due = due_date(cohort.opened, exchange)
    spreads: list[_Spread] = []
    skipped: list[dict[str, Any]] = []
    for side, tickers in (("long", cohort.longs), ("short", cohort.shorts)):
        option_type = "call" if side == "long" else "put"
        direction: Direction = "bullish" if side == "long" else "bearish"
        for ticker in tickers:
            mine = chain[(chain["ticker"] == ticker) & (chain["option_type"] == option_type)]
            reason = None
            if mine.empty:
                reason = "no chain captured on the open date"
            else:
                expiry = choose_expiry(sorted(set(mine["expiry"])), due)
                if expiry is None:
                    reason = "no captured expiry reaches the exit"
                else:
                    liquid = {
                        r["strike"]: (float(r["bid"]), float(r["ask"]))
                        for r in _records(mine[mine["expiry"] == expiry])
                        if sound(r["bid"], r["ask"]) and r["open_interest"] >= MIN_OPEN_INTEREST
                    }
                    spot = float(mine["underlying_close"].iloc[0])
                    picked = spread_strikes(direction, spot, list(liquid))
                    if picked is None:
                        reason = "fewer than two liquid strikes"
                    else:
                        long_k, short_k = picked
                        debit = entry_debit(
                            liquid[long_k][1], liquid[short_k][0], abs(short_k - long_k)
                        )
                        if debit is None:
                            reason = "quotes imply no sane debit"
                        else:
                            spread = _Spread(
                                ticker, side, option_type, expiry, long_k, short_k, debit
                            )
                            spread.last = {long_k: liquid[long_k], short_k: liquid[short_k]}
                            spreads.append(spread)
            if reason:
                skipped.append({"ticker": ticker, "side": side, "note": reason})
    return spreads, skipped


def _close_on_or_before(series: list[tuple[dt.date, float]], day: dt.date) -> float | None:
    """An expiry can fall on a holiday: settle on the last close on or before it."""
    i = bisect.bisect_right([d for d, _ in series], day)
    return series[i - 1][1] if i else None


def simulate(
    cohorts: list[Cohort], market: Market, exchange: str, latest: dt.date
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Run the book through every cohort; returns (position rows, daily rows)."""
    cash = 1.0
    positions: list[dict[str, Any]] = []
    daily: dict[dt.date, dict[str, Any]] = {}
    for cohort in cohorts:
        phase = "live" if cohort.opened >= LIVE_SINCE else "replay"
        base = {
            "book": BOOK,
            "opened": cohort.opened,
            "exchange": exchange,
            "phase": phase,
            "exit_date": cohort.closes,
        }
        spreads, skipped = _open_cohort(cohort, market, exchange)
        positions += [{**base, **s, "status": "skipped"} for s in skipped]
        if not spreads:
            continue

        # Size: RISK_BUDGET of equity across the cohort, equally per spread, commission included.
        per_spread = RISK_BUDGET * cash / len(spreads)
        for s in spreads:
            s.quantity = per_spread / (s.debit * CONTRACT + 2 * COMMISSION_PER_LEG)
        cash -= per_spread * len(spreads)

        end = cohort.closes or latest
        days = sorted(set(market.snapshot_dates(cohort.opened, end)) | {end})
        contracts = [
            (s.ticker, s.expiry, k, s.option_type)
            for s in spreads
            for k in (s.long_strike, s.short_strike)
        ]
        legs = _records(market.legs(contracts, cohort.opened, end))
        quotes: dict[tuple[Any, ...], tuple[object, object]] = {
            (r["snapshot_date"], r["ticker"], r["expiry"], r["strike"], r["option_type"]): (
                r["bid"],
                r["ask"],
            )
            for r in legs
        }
        spots: dict[tuple[dt.date, str], float] = {
            (r["snapshot_date"], r["ticker"]): float(r["underlying_close"]) for r in legs
        }
        price_rows = _records(market.closes([s.ticker for s in spreads], cohort.opened, end))
        closes: dict[tuple[dt.date, str], float] = {
            (r["date"], r["ticker"]): float(r["close"]) for r in price_rows
        }
        history: dict[str, list[tuple[dt.date, float]]] = {}
        for r in sorted(price_rows, key=lambda r: r["date"]):
            history.setdefault(r["ticker"], []).append((r["date"], float(r["close"])))

        for day in days:
            for s in spreads:
                spot = spots.get((day, s.ticker), closes.get((day, s.ticker)))
                if day >= s.expiry:
                    if s.basis != "settled":
                        settle = _close_on_or_before(history.get(s.ticker, []), s.expiry)
                        if settle is not None:
                            s.mark = intrinsic(s.option_type, settle, s.long_strike, s.short_strike)
                            s.basis, s.mark_date = "settled", day
                    continue
                fresh = 0
                for strike in (s.long_strike, s.short_strike):
                    q = quotes.get((day, s.ticker, s.expiry, strike, s.option_type))
                    if q is not None and sound(*q):
                        s.last[strike] = (float(q[0]), float(q[1]))  # type: ignore[arg-type]
                        fresh += 1
                long_q, short_q = s.last.get(s.long_strike), s.last.get(s.short_strike)
                value = (
                    liquidation_value(long_q[0], short_q[1], s.width)
                    if long_q is not None and short_q is not None
                    else None
                )
                if value is not None:
                    # A leg whose own quote is missing or unsound today is valued at its last
                    # sound one, and the row says so.
                    s.mark, s.basis = value, "quote" if fresh == 2 else "last quote"
                elif spot is not None:
                    s.mark = intrinsic(s.option_type, spot, s.long_strike, s.short_strike)
                    s.basis = "intrinsic"
                else:
                    continue  # nothing to value it with today: keep yesterday's mark
                s.mark_date = day
            held = sum(s.quantity * s.mark * CONTRACT for s in spreads)
            daily[day] = {
                "book": BOOK,
                "date": day,
                "exchange": exchange,
                "equity": cash + held,
                "cash": cash,
                "open_positions": len(spreads),
                "phase": phase,
            }

        closed = cohort.closes is not None
        if closed:
            # A spread worth less than the commission to close is left to expire, not sold.
            for s in spreads:
                cash += s.quantity * max(s.mark * CONTRACT - 2 * COMMISSION_PER_LEG, 0.0)
            daily[end] = {**daily[end], "equity": cash, "cash": cash, "open_positions": 0}
        for s in spreads:
            positions.append(
                {
                    **base,
                    "ticker": s.ticker,
                    "side": s.side,
                    "status": "closed" if closed else "open",
                    "option_type": s.option_type,
                    "expiry": s.expiry,
                    "long_strike": s.long_strike,
                    "short_strike": s.short_strike,
                    "entry_debit": s.debit,
                    "quantity": s.quantity,
                    "mark_date": s.mark_date,
                    "mark_value": s.mark,
                    "mark_basis": s.basis,
                    "exit_date": cohort.closes,
                    "model_version": cohort.model_version,
                }
            )
    return positions, [daily[d] for d in sorted(daily)]


# --- reading and writing the database --------------------------------------------------------

POSITION_COLUMNS = [c.name for c in OptionBookPosition.__table__.columns]


class DbMarket:
    """`Market` over the captured chains and stored prices of one exchange."""

    def __init__(self, engine: Engine, exchange: str) -> None:
        self.engine = engine
        self.exchange = exchange

    def _frame(self, sql: str, **params: Any) -> pd.DataFrame:
        with self.engine.connect() as conn:
            return pd.read_sql(text(sql), conn, params=params)

    def chain(self, day: dt.date, tickers: list[str]) -> pd.DataFrame:
        return self._frame(
            "SELECT ticker, expiry, strike, option_type, bid, ask, open_interest, underlying_close "
            "FROM option_quotes WHERE snapshot_date = :d AND ticker = ANY(:t)",
            d=day,
            t=tickers,
        )

    def legs(
        self, contracts: list[tuple[str, dt.date, float, str]], start: dt.date, end: dt.date
    ) -> pd.DataFrame:
        frame = self._frame(
            "SELECT snapshot_date, ticker, expiry, strike, option_type, bid, ask, underlying_close "
            "FROM option_quotes WHERE ticker = ANY(:t) AND expiry = ANY(:e) "
            "AND snapshot_date BETWEEN :s AND :end",
            t=sorted({c[0] for c in contracts}),
            e=sorted({c[1] for c in contracts}),
            s=start,
            end=end,
        )
        wanted = pd.DataFrame(contracts, columns=["ticker", "expiry", "strike", "option_type"])
        return frame.merge(wanted, on=["ticker", "expiry", "strike", "option_type"])

    def closes(self, tickers: list[str], start: dt.date, end: dt.date) -> pd.DataFrame:
        # From a week before the open, so a cohort can settle an expiry against a prior close.
        return self._frame(
            "SELECT ticker, date, close FROM prices WHERE ticker = ANY(:t) "
            "AND date BETWEEN :s AND :end",
            t=tickers,
            s=start - dt.timedelta(days=7),
            end=end,
        )

    def snapshot_dates(self, start: dt.date, end: dt.date) -> list[dt.date]:
        frame = self._frame(
            "SELECT DISTINCT q.snapshot_date FROM option_quotes q "
            "JOIN universe u ON u.ticker = q.ticker AND u.exchange = :ex "
            "WHERE q.snapshot_date BETWEEN :s AND :end ORDER BY 1",
            ex=self.exchange,
            s=start,
            end=end,
        )
        return list(frame["snapshot_date"])


def rebuild_option_book(engine: Engine, session: Session, exchange: str) -> dict[str, Any]:
    """Recompute the book for one market from scratch and replace its rows.

    A full rebuild, like the share books: its inputs — predictions, the share book's positions and
    the captured chains — are never rewritten, so the result only changes when the rules do, and
    then LIVE_SINCE moves with them.
    """
    if not get_exchange(exchange).has_options:
        return {"cohorts": 0, "note": f"{exchange} has no option chains"}
    book = pd.read_sql(
        text(
            "SELECT date, positions, model_version FROM portfolio_snapshots "
            "WHERE exchange = :ex AND variant = :v ORDER BY date"
        ),
        engine,
        params={"ex": exchange, "v": SHARE_BOOK},
    )
    with engine.connect() as conn:
        span = conn.execute(
            text(
                "SELECT min(q.snapshot_date), max(q.snapshot_date) FROM option_quotes q "
                "JOIN universe u ON u.ticker = q.ticker AND u.exchange = :ex"
            ),
            {"ex": exchange},
        ).one()
    first = cast("dt.date | None", span[0])
    latest = cast("dt.date | None", span[1])
    if book.empty or first is None or latest is None:
        return {"cohorts": 0, "note": "no share book or no option history yet"}
    # A cohort that opened before the first captured chain could never have been traded.
    cohorts = [c for c in cohorts_from_book(book) if c.opened >= first]
    positions, daily = simulate(cohorts, DbMarket(engine, exchange), exchange, latest)

    session.execute(
        delete(OptionBookPosition).where(
            OptionBookPosition.book == BOOK, OptionBookPosition.exchange == exchange
        )
    )
    session.execute(
        delete(OptionBookDay).where(OptionBookDay.book == BOOK, OptionBookDay.exchange == exchange)
    )
    rows = [{c: p.get(c) for c in POSITION_COLUMNS} for p in positions]
    for batch in chunked(rows):
        session.execute(insert(OptionBookPosition), list(batch))
    for batch in chunked(daily):
        session.execute(insert(OptionBookDay), list(batch))
    return {
        "cohorts": len(cohorts),
        "spreads": sum(1 for p in positions if p["status"] != "skipped"),
        "skipped": sum(1 for p in positions if p["status"] == "skipped"),
        "equity": daily[-1]["equity"] if daily else None,
    }


# --- reading the book back ---------------------------------------------------------------------


def spread_cash(entry_debit: float, mark: float, quantity: float) -> tuple[float, float]:
    """(premium paid, proceeds if closed at this mark) for one spread, commissions included.

    A spread worth less than the commission to close is left to expire, so its proceeds are zero
    rather than negative.
    """
    premium = quantity * (entry_debit * CONTRACT + 2 * COMMISSION_PER_LEG)
    proceeds = quantity * max(mark * CONTRACT - 2 * COMMISSION_PER_LEG, 0.0)
    return premium, proceeds


def return_on_premium(entry_debit: float, mark: float) -> float:
    """What one spread made or lost, as a share of what it cost to open."""
    premium, proceeds = spread_cash(entry_debit, mark, 1.0)
    return proceeds / premium - 1


def summarize_cohorts(
    positions: list[dict[str, Any]], share_return: Callable[[dt.date, dt.date | None], float | None]
) -> list[dict[str, Any]]:
    """One row per cohort: what it made on the book's equity and on its premium, beside the same
    names held as shares over the same window. An open cohort is valued as if closed today."""
    by_cohort: dict[dt.date, list[dict[str, Any]]] = {}
    for p in positions:
        by_cohort.setdefault(p["opened"], []).append(p)
    rows = []
    for opened in sorted(by_cohort):
        group = by_cohort[opened]
        traded = [p for p in group if p["status"] != "skipped"]
        premium = proceeds = 0.0
        for p in traded:
            paid, raised = spread_cash(p["entry_debit"], p["mark_value"], p["quantity"])
            premium, proceeds = premium + paid, proceeds + raised
        pnl = proceeds - premium
        exit_date = group[0].get("exit_date")
        rows.append(
            {
                "opened": opened,
                "exit_date": exit_date,
                "phase": group[0]["phase"],
                "spreads": len(traded),
                "skipped": len(group) - len(traded),
                # Each cohort risks RISK_BUDGET of equity, so equity at open is premium / budget.
                "options_return": pnl / (premium / RISK_BUDGET) if premium else None,
                "return_on_premium": pnl / premium if premium else None,
                "shares_return": share_return(opened, exit_date),
            }
        )
    return rows
