"""The advisor brief (ADR 0007): one page per stock, to take to a licensed financial advisor.

It sets out what the public evidence on these pages shows about one name — price history, the
model's view and how far that view can be trusted, short interest, option hedging, attention and
ownership filings — and turns it into points that lean each way, risks worth raising, questions to
ask, and what the page cannot know. Every sentence is filled from numbers by fixed rules (no
language model writes any of it, per ADR 0004), so the same evidence always reads the same way.

It assesses; it never says to buy, sell or hold. The step from evidence to a decision needs the
reader's circumstances, which only they and their advisor know.
"""

import datetime as dt
import math
import re
from dataclasses import dataclass, field
from itertools import pairwise
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from quantpulse.data.calendar import get_exchange
from quantpulse.ml.portfolio import DAILY_BOOK

DISCLAIMER = (
    "An assessment of public evidence, prepared for a conversation with a licensed financial "
    "advisor. It is not a recommendation to buy, sell or hold anything, and it knows nothing of "
    "your circumstances, which decide what is suitable for you."
)

#: The model's top or bottom fifth of a market: the share its paper books hold on each side.
MODEL_EDGE = 0.2
#: An alpha this many standard errors from zero is the usual bar for telling it from luck.
SEPARATED_T = 2.0
#: Short interest above this share of the float is high for a large company.
HIGH_SHORT = 0.10
#: The Positioning page's own mark for unusual attention.
UNUSUAL_ATTENTION = 3.0
#: Call hedging per 1% move above this share of a normal day's trading is large.
LARGE_GAMMA = 0.25
#: A year's volatility above this is high for a single stock.
HIGH_VOLATILITY = 0.50
#: A fall from the 12-month high deeper than this is worth raising.
DEEP_FALL = -0.30
#: Unplanned insider selling above this is worth naming when no insider bought.
NOTABLE_SELLING = 1_000_000.0


@dataclass
class Evidence:
    """Every number the brief reads, each None when its source has nothing for the name."""

    ticker: str
    exchange: str
    followed_by: str
    name: str | None = None
    has_options: bool = True
    as_of: dt.date | None = None
    close: float | None = None
    returns: dict[str, float | None] = field(default_factory=dict)  # '1m', '3m', '12m'
    volatility: float | None = None
    from_high: float | None = None
    model_rank: int | None = None
    model_count: int | None = None
    model_date: dt.date | None = None
    book_side: str | None = None
    live_sessions: int | None = None
    live_alpha: float | None = None
    live_alpha_se: float | None = None
    live_alpha_t: float | None = None
    short_pct_float: float | None = None
    days_to_cover: float | None = None
    short_settlement_date: dt.date | None = None
    call_gamma_share_of_adv: float | None = None
    attention_ratio: float | None = None
    bought_usd_90d: float | None = None
    buyers_90d: int | None = None
    sold_usd_90d: float | None = None
    planned_sold_share_90d: float | None = None
    top_holder: str | None = None
    top_holder_percent: float | None = None
    top_holder_class: str | None = None
    activist_holder: bool = False
    option_spread: str | None = None


@dataclass
class Fact:
    fact: str
    value: str
    note: str | None = None


@dataclass
class Brief:
    ticker: str
    name: str | None
    exchange: str
    followed_by: str
    as_of: dt.date | None
    summary: str
    facts: list[Fact]
    for_points: list[str]
    against_points: list[str]
    risks: list[str]
    questions: list[str]
    limits: list[str]
    disclaimer: str = DISCLAIMER


def _pct(v: float | None, digits: int = 0, signed: bool = True) -> str:
    if v is None:
        return "—"
    sign = "+" if signed and v > 0 else ""
    return f"{sign}{v * 100:.{digits}f}%"


def _usd(v: float) -> str:
    for size, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(v) >= size:
            return f"${v / size:.1f}{suffix}" if abs(v) < 10 * size else f"${v / size:.0f}{suffix}"
    return f"${v:.0f}"


def _date(d: dt.date) -> str:
    return f"{d.day} {d:%b %Y}"


def share_class(title: str | None) -> str | None:
    """ "Class A" from a filing's class title, or None for a company with one class of stock.

    The class matters only where there are several: Berkshire's largest holder reports 38% of
    Class A, which is not the Class B the universe tracks.
    """
    match = re.search(r"\bclass\s+([A-Z])\b", title or "", re.IGNORECASE)
    return f"Class {match.group(1).upper()}" if match else None


def _rank_text(e: Evidence) -> str | None:
    if e.model_rank is None or not e.model_count:
        return None
    return f"{e.model_rank} of {e.model_count}"


def _separated(e: Evidence) -> bool:
    return e.live_alpha_t is not None and abs(e.live_alpha_t) >= SEPARATED_T


def compose(e: Evidence) -> Brief:
    """The brief's text from its evidence, by fixed rules."""
    ex = get_exchange(e.exchange)
    facts: list[Fact] = []
    pros: list[str] = []
    cons: list[str] = []
    risks: list[str] = []
    questions: list[str] = [
        f"How would a position in {e.ticker} fit with what I already own, and how much of my "
        "money should any single stock be?"
    ]
    limits: list[str] = []

    # --- price ---------------------------------------------------------------------------------
    if e.close is not None and e.as_of is not None:
        facts.append(
            Fact(
                "Last close",
                f"{ex.display_symbol}{e.close / ex.display_divisor:,.2f}",
                _date(e.as_of),
            )
        )
    if e.returns:
        facts.append(
            Fact(
                "Return over 1, 3 and 12 months",
                " / ".join(_pct(e.returns.get(k), 1) for k in ("1m", "3m", "12m")),
                "Past returns, not a forecast.",
            )
        )
    if e.volatility is not None:
        facts.append(
            Fact(
                "How much it moves",
                f"{e.volatility * 100:.0f}% a year",
                "Annualized volatility over the past year: a typical year's swing either way.",
            )
        )
        questions.append(
            f"It has moved about {e.volatility * 100:.0f}% a year. How large a fall could I hold "
            "through without needing to sell?"
        )
        if e.volatility >= HIGH_VOLATILITY:
            risks.append(
                f"It swings about {e.volatility * 100:.0f}% a year, which is high for one stock: "
                "a fall of that size within a year would be ordinary for it."
            )
    if e.from_high is not None:
        at_high = e.from_high > -0.005
        facts.append(
            Fact(
                "Below its 12-month high",
                "At its high" if at_high else _pct(e.from_high, 0, signed=False),
            )
        )
        if e.from_high <= DEEP_FALL:
            risks.append(
                f"It is {_pct(-e.from_high, 0, signed=False)} below its 12-month high. A fallen "
                "price is not by itself cheap; ask what changed."
            )

    # --- the model -----------------------------------------------------------------------------
    rank = _rank_text(e)
    if e.followed_by == "watchlist":
        facts.append(
            Fact("The model's view", "None", "A watchlist name: the model does not follow it.")
        )
        limits.append(
            "The model does not follow this name, so there is no forecast for it here — only the "
            "research evidence."
        )
    elif rank is not None and e.model_rank is not None and e.model_count:
        share = e.model_rank / e.model_count
        place = (
            "top fifth"
            if share <= MODEL_EDGE
            else "bottom fifth"
            if share > 1 - MODEL_EDGE
            else "middle"
        )
        facts.append(
            Fact(
                "The model's rank today",
                f"{rank} on {e.exchange} ({place})",
                f"Its forecast for the next month, against its peers, as of {_date(e.model_date)}."
                if e.model_date
                else None,
            )
        )
        if share <= MODEL_EDGE:
            pros.append(
                f"The model ranks it {rank} on this market, in its top fifth: it expects the stock "
                "to beat most of its peers over the next month."
            )
        elif share > 1 - MODEL_EDGE:
            cons.append(
                f"The model ranks it {rank} on this market, in its bottom fifth: it expects the "
                "stock to trail most of its peers over the next month."
            )
        if e.book_side:
            facts.append(Fact("The model's paper book", f"Held {e.book_side}", "Paper only."))
    if e.followed_by == "model" and e.live_sessions:
        alpha = (
            f"{_pct(e.live_alpha, 1)} a year ± {_pct(e.live_alpha_se, 1, signed=False)}"
            if e.live_alpha is not None and e.live_alpha_se is not None
            else "not yet measured"
        )
        facts.append(
            Fact(
                "The model's live record",
                f"{e.live_sessions} sessions; alpha {alpha}",
                "Distinguishable from zero."
                if _separated(e)
                else "Not yet distinguishable from luck: the error band is wider than the result.",
            )
        )
        if not _separated(e):
            limits.append(
                f"The model's live record on this market is {e.live_sessions} sessions, and its "
                "result cannot yet be told apart from luck. Treat its ranking as a hypothesis."
            )
            questions.append(
                "This ranking comes from a model whose live record has not separated from luck. "
                "Should a model's view carry any weight in my decision?"
            )
        else:
            questions.append("How much weight should a model's ranking carry in my decision?")

    # --- positioning ---------------------------------------------------------------------------
    if not e.has_options:
        limits.append(
            "Short interest, listed options and US ownership filings are not published free for "
            "this market, so those measures are missing here."
        )
    if e.short_pct_float is not None:
        note = (
            f"Settled {_date(e.short_settlement_date)}; published a week or two later."
            if e.short_settlement_date
            else None
        )
        cover = f", {e.days_to_cover:.1f} days to cover" if e.days_to_cover is not None else ""
        facts.append(
            Fact(
                "Sold short",
                f"{_pct(e.short_pct_float, 1, signed=False)} of the float{cover}",
                note,
            )
        )
        if e.short_pct_float >= HIGH_SHORT:
            cons.append(
                f"{_pct(e.short_pct_float, 0, signed=False)} of the shares that trade are sold "
                "short: many investors are betting the price will fall."
            )
            risks.append(
                "Heavily shorted stocks can jump when short sellers rush to buy back, as GameStop "
                "did in 2021, and fall hard when they are right. Either way the moves are large."
            )
            questions.append(
                "Much of it is sold short. What would a sharp squeeze, or a collapse, do to a "
                "position, and should I limit either?"
            )
    if e.call_gamma_share_of_adv is not None:
        facts.append(
            Fact(
                "Option hedging per 1% move",
                f"{_pct(e.call_gamma_share_of_adv, 0, signed=False)} of a normal day's trading",
                "An upper bound, if dealers had sold every listed call.",
            )
        )
        if e.call_gamma_share_of_adv >= LARGE_GAMMA:
            risks.append(
                "Option hedging is large against its normal trading, so dealers' hedging could "
                "add to a move in either direction."
            )
    if e.attention_ratio is not None:
        facts.append(
            Fact(
                "Public attention",
                f"{e.attention_ratio:.1f} times its usual level",
                "Wikipedia views, past week.",
            )
        )
        if e.attention_ratio >= UNUSUAL_ATTENTION:
            risks.append(
                f"It is drawing {e.attention_ratio:.0f} times its usual attention. GameStop's "
                "attention peaked with its price, not before it: attention marks a crowd, not a "
                "direction."
            )

    # --- ownership -----------------------------------------------------------------------------
    if e.bought_usd_90d is not None:
        bought = e.bought_usd_90d or 0.0
        sold = e.sold_usd_90d or 0.0
        planned = (
            f", {_pct(e.planned_sold_share_90d, 0, signed=False)} of it planned in advance"
            if e.planned_sold_share_90d is not None and sold
            else ""
        )
        facts.append(
            Fact(
                "Insiders, past 90 days",
                f"bought {_usd(bought) if bought else 'nothing'}; "
                f"sold {_usd(sold) if sold else 'nothing'}{planned}",
                "Open-market trades from Form 4 filings, not shares received as pay.",
            )
        )
        if bought > 0:
            who = (
                f" ({e.buyers_90d} insider{'s' if (e.buyers_90d or 0) != 1 else ''})"
                if e.buyers_90d
                else ""
            )
            pros.append(
                f"Insiders bought {_usd(bought)} of the stock on the open market in the past 90 "
                f"days{who}. Buying with their own money is the rarer, more telling act."
            )
            questions.append(
                "Insiders have been buying. What do you make of that, given their reasons may not "
                "be ones that apply to me?"
            )
        elif sold >= NOTABLE_SELLING and (e.planned_sold_share_90d or 0) < 0.5:
            cons.append(
                f"Insiders sold {_usd(sold)} in the past 90 days and bought none, most of it not "
                "under a plan set in advance. Selling is often routine, so this is weak evidence."
            )
    if e.top_holder and e.top_holder_percent is not None:
        facts.append(
            Fact(
                "Largest holder over 5%",
                f"{e.top_holder}, {e.top_holder_percent:.1f}%"
                + (
                    f" of {share_class(e.top_holder_class)}"
                    if share_class(e.top_holder_class)
                    else ""
                ),
                "Filed a 13D: may seek to influence the company."
                if e.activist_holder
                else "From its latest 13D or 13G filing.",
            )
        )

    if e.option_spread:
        facts.append(Fact("The paper options book", e.option_spread, "Paper only (ADR 0008)."))
        questions.append(
            "The paper options book on these pages has a spread on it. Are options suitable for "
            "me at all, and what could I lose?"
        )

    questions.append("What would buying and holding it cost me, in fees and in tax, where I live?")
    limits.append(
        "Everything here is public and some of it is late: short interest by one to two weeks, "
        "insider trades by up to two days, large stakes by weeks. None of it knows what the "
        "company will report next."
    )

    def points(n: int) -> str:
        return f"{n} point in the evidence leans" if n == 1 else f"{n} points in the evidence lean"

    if pros and cons:
        lean = f"{points(len(pros))} in its favour and {len(cons)} against it"
    elif pros:
        lean = f"{points(len(pros))} in its favour and none against it"
    elif cons:
        lean = f"{points(len(cons))} against it and none in its favour"
    else:
        lean = "Nothing in the evidence here leans clearly either way"
    price = (
        f"{e.ticker} closed at {ex.display_symbol}{e.close / ex.display_divisor:,.2f} on "
        f"{_date(e.as_of)}, {_pct(e.returns.get('12m'), 0)} over the past year. "
        if e.close is not None and e.as_of is not None and e.returns.get("12m") is not None
        else ""
    )
    raise_ = (
        "no risk stands out beyond those of owning any single stock"
        if not risks
        else "1 risk is worth raising"
        if len(risks) == 1
        else f"{len(risks)} risks are worth raising"
    )
    summary = (
        f"{price}{lean}, and {raise_}. This is a list of what the public evidence shows, for a "
        "conversation with a licensed advisor; it does not say what to do."
    )
    return Brief(
        ticker=e.ticker,
        name=e.name,
        exchange=e.exchange,
        followed_by=e.followed_by,
        as_of=e.as_of,
        summary=summary,
        facts=facts,
        for_points=pros,
        against_points=cons,
        risks=risks,
        questions=questions,
        limits=limits,
    )


# --- gathering --------------------------------------------------------------------------------


def _one(session: Session, sql: str, **params: Any) -> dict[str, Any] | None:
    try:
        row = session.execute(text(sql), params).mappings().first()
    except ProgrammingError:  # a mart not built yet reads as "nothing for this name"
        session.rollback()
        return None
    return dict(row) if row else None


def _price_evidence(e: Evidence, closes: list[tuple[dt.date, float]]) -> None:
    if not closes:
        return
    e.as_of, e.close = closes[-1]
    values = [c for _, c in closes]

    def back(n: int) -> float | None:
        return values[-1] / values[-1 - n] - 1 if len(values) > n and values[-1 - n] else None

    e.returns = {"1m": back(21), "3m": back(63), "12m": back(252)}
    year = values[-253:]
    logs = [math.log(b / a) for a, b in pairwise(year) if a > 0 and b > 0]
    if len(logs) >= 60:
        mean = sum(logs) / len(logs)
        e.volatility = math.sqrt(sum((x - mean) ** 2 for x in logs) / (len(logs) - 1) * 252)
    e.from_high = values[-1] / max(year) - 1


def gather(session: Session, ticker: str) -> Evidence | None:
    """Read every source the brief uses for one name; None when the name is not followed."""
    ticker = ticker.upper()
    who = _one(
        session,
        "SELECT ticker, exchange, name, 'model' AS followed_by FROM universe WHERE ticker = :t "
        "UNION ALL SELECT ticker, exchange, NULL, 'watchlist' FROM watchlist WHERE ticker = :t",
        t=ticker,
    )
    if who is None:
        return None
    e = Evidence(
        ticker=ticker,
        exchange=who["exchange"],
        followed_by=who["followed_by"],
        name=who["name"],
        has_options=get_exchange(who["exchange"]).has_options,
    )
    table = "prices" if e.followed_by == "model" else "watchlist_prices"
    rows = session.execute(
        text(
            f"SELECT date, close FROM {table} WHERE ticker = :t AND date > "
            f"(SELECT max(date) FROM {table} WHERE ticker = :t) - 400 ORDER BY date"
        ),
        {"t": ticker},
    ).all()
    _price_evidence(e, [(r[0], float(r[1])) for r in rows])

    if e.followed_by == "model":
        # The newest forecast day and model version for this market, as /predictions/latest reads.
        ranked = session.execute(
            text(
                "WITH members AS (SELECT ticker FROM universe WHERE exchange = :ex), "
                "latest AS (SELECT max(date) AS d FROM predictions "
                "WHERE ticker IN (SELECT ticker FROM members)), "
                "version AS (SELECT max(model_version) AS v FROM predictions, latest "
                "WHERE date = latest.d AND ticker IN (SELECT ticker FROM members)) "
                "SELECT p.ticker, p.date FROM predictions p, latest, version "
                "WHERE p.date = latest.d AND p.model_version = version.v "
                "AND p.ticker IN (SELECT ticker FROM members) ORDER BY p.score DESC"
            ),
            {"ex": e.exchange},
        ).all()
        order = [r[0] for r in ranked]
        if ticker in order:
            e.model_rank, e.model_count, e.model_date = (
                order.index(ticker) + 1,
                len(order),
                ranked[0][1],
            )
        book = _one(
            session,
            "SELECT positions FROM portfolio_snapshots WHERE exchange = :ex AND variant = :v "
            "ORDER BY date DESC LIMIT 1",
            ex=e.exchange,
            v=DAILY_BOOK.variant,
        )
        weight = (book or {}).get("positions", {}).get(ticker) if book else None
        if weight:
            e.book_side = "long" if weight > 0 else "short"
        live = _one(
            session,
            "SELECT n_days, alpha_annualized, alpha_std_error_annualized, alpha_t_stat "
            "FROM analytics.fct_alpha_beta WHERE exchange = :ex AND phase = 'live'",
            ex=e.exchange,
        )
        if live:
            e.live_sessions = live["n_days"]
            e.live_alpha = live["alpha_annualized"]
            e.live_alpha_se = live["alpha_std_error_annualized"]
            e.live_alpha_t = live["alpha_t_stat"]

    short = _one(
        session,
        "SELECT short_pct_float, days_to_cover, settlement_date FROM analytics.stg_short_interest "
        "WHERE ticker = :t ORDER BY settlement_date DESC LIMIT 1",
        t=ticker,
    )
    if short:
        e.short_pct_float = short["short_pct_float"]
        e.days_to_cover = short["days_to_cover"]
        e.short_settlement_date = short["settlement_date"]
    pos = _one(
        session,
        "SELECT call_gamma_share_of_adv FROM analytics.fct_positioning WHERE ticker = :t "
        "ORDER BY snapshot_date DESC LIMIT 1",
        t=ticker,
    )
    if pos:
        e.call_gamma_share_of_adv = pos["call_gamma_share_of_adv"]
    att = _one(
        session,
        "SELECT attention_ratio FROM analytics.fct_attention WHERE ticker = :t "
        "ORDER BY date DESC LIMIT 1",
        t=ticker,
    )
    if att:
        e.attention_ratio = att["attention_ratio"]
    own = _one(
        session,
        "SELECT bought_usd_90d, buyers_90d, sold_usd_90d, planned_sold_share_90d, top_holder, "
        "top_holder_percent, top_holder_class, activist_holder FROM analytics.fct_ownership "
        "WHERE ticker = :t",
        t=ticker,
    )
    if own:
        e.bought_usd_90d = own["bought_usd_90d"]
        e.buyers_90d = own["buyers_90d"]
        e.sold_usd_90d = own["sold_usd_90d"]
        e.planned_sold_share_90d = own["planned_sold_share_90d"]
        e.top_holder = own["top_holder"]
        e.top_holder_percent = own["top_holder_percent"]
        e.top_holder_class = own["top_holder_class"]
        e.activist_holder = bool(own["activist_holder"])
    spread = _one(
        session,
        "SELECT option_type, long_strike, short_strike, expiry FROM option_book_positions "
        "WHERE ticker = :t AND status = 'open' ORDER BY opened DESC LIMIT 1",
        t=ticker,
    )
    if spread and spread["long_strike"] is not None:
        kind = "Bull call" if spread["option_type"] == "call" else "Bear put"
        e.option_spread = (
            f"{kind} spread {spread['long_strike']:g}/{spread['short_strike']:g}, expiring "
            f"{_date(spread['expiry'])}"
        )
    return e
