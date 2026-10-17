"""The paper options book (ADR 0008), on a market small enough to work by hand.

One stock, AAA, at $100. Its call spread buys the 100 strike at the ask and sells the 110 at the
bid; closing does the reverse. Prices are what the book would pay, not what looks fair.
"""

import datetime as dt
import math

import pandas as pd
import pytest

from quantpulse.options.book import (
    COMMISSION_PER_LEG,
    CONTRACT,
    LIVE_SINCE,
    RISK_BUDGET,
    Cohort,
    choose_expiry,
    cohorts_from_book,
    entry_debit,
    intrinsic,
    liquidation_value,
    simulate,
)

OPEN = dt.date(2026, 8, 12)
EXIT = dt.date(2026, 9, 11)
EXPIRY = dt.date(2026, 9, 18)  # the first expiry after the cohort's due date
EARLY = dt.date(2026, 8, 28)  # too soon: expires before the exit


class FrameMarket:
    """`Market` over in-memory frames."""

    def __init__(self, quotes: list[dict[str, object]], closes: list[dict[str, object]]):
        self.quotes = pd.DataFrame(quotes)
        self.prices = pd.DataFrame(closes, columns=["ticker", "date", "close"])

    def chain(self, day: dt.date, tickers: list[str]) -> pd.DataFrame:
        q = self.quotes
        return q[(q["snapshot_date"] == day) & q["ticker"].isin(tickers)]

    def legs(
        self, contracts: list[tuple[str, dt.date, float, str]], start: dt.date, end: dt.date
    ) -> pd.DataFrame:
        q = self.quotes[
            (self.quotes["snapshot_date"] >= start) & (self.quotes["snapshot_date"] <= end)
        ]
        wanted = pd.DataFrame(contracts, columns=["ticker", "expiry", "strike", "option_type"])
        return q.merge(wanted, on=["ticker", "expiry", "strike", "option_type"])

    def closes(self, tickers: list[str], start: dt.date, end: dt.date) -> pd.DataFrame:
        p = self.prices
        return p[p["ticker"].isin(tickers) & (p["date"] <= end)]

    def snapshot_dates(self, start: dt.date, end: dt.date) -> list[dt.date]:
        days = self.quotes["snapshot_date"]
        return sorted({d for d in days if start <= d <= end})


def quote(
    day: dt.date,
    strike: float,
    bid: float,
    ask: float,
    expiry: dt.date = EXPIRY,
    kind: str = "call",
    spot: float = 100.0,
    oi: int = 100,
) -> dict[str, object]:
    return {
        "snapshot_date": day,
        "ticker": "AAA",
        "expiry": expiry,
        "strike": strike,
        "option_type": kind,
        "bid": bid,
        "ask": ask,
        "underlying_close": spot,
        "open_interest": oi,
    }


MID = dt.date(2026, 8, 13)
QUOTES = [
    quote(OPEN, 100, 4.9, 5.0),
    quote(OPEN, 110, 1.0, 1.1),
    quote(OPEN, 100, 9.0, 9.5, expiry=EARLY),  # a nearer expiry the cohort must not choose
    quote(OPEN, 110, 4.0, 4.5, expiry=EARLY),
    quote(MID, 100, 6.0, 6.1),
    quote(MID, 110, 1.5, 1.6),
    quote(EXIT, 100, 7.0, 7.1),
    quote(EXIT, 110, 1.9, 2.0),
]
COHORT = Cohort(OPEN, EXIT, ("AAA",), (), "10")


def test_entry_pays_the_ask_and_receives_the_bid() -> None:
    assert entry_debit(5.0, 1.0, 10) == pytest.approx(4.0)
    assert entry_debit(5.0, math.nan, 10) == pytest.approx(5.0), "no bid sells for nothing"
    assert entry_debit(None, 1.0, 10) is None, "no ask, no trade"
    assert entry_debit(12.0, 1.0, 10) is None, "a debit at or above the width is not sane"


def test_liquidation_is_the_other_side_and_never_reads_a_gap_as_worthless() -> None:
    assert liquidation_value(6.0, 1.6, 10) == pytest.approx(4.4)
    assert liquidation_value(1.0, 2.0, 10) == 0.0
    assert liquidation_value(math.nan, 1.6, 10) is None
    assert liquidation_value(6.0, None, 10) is None


def test_intrinsic_is_clamped_to_the_width() -> None:
    assert intrinsic("call", 104, 100, 110) == pytest.approx(4)
    assert intrinsic("call", 130, 100, 110) == pytest.approx(10)
    assert intrinsic("put", 85, 100, 90) == pytest.approx(10)
    assert intrinsic("put", 105, 100, 90) == 0.0


def test_the_expiry_is_the_first_that_reaches_the_exit() -> None:
    assert choose_expiry([EARLY, EXPIRY, dt.date(2026, 10, 16)], EXIT) == EXPIRY
    assert choose_expiry([EARLY], EXIT) is None


def test_cohorts_follow_the_share_books_rebalances() -> None:
    book = pd.DataFrame(
        [
            {"date": OPEN, "positions": {"AAA": 0.5, "BBB": -0.5}, "model_version": "10"},
            {"date": MID, "positions": {"AAA": 0.5, "BBB": -0.5}, "model_version": "10"},
            {"date": EXIT, "positions": {"CCC": 0.5, "BBB": -0.5}, "model_version": "11"},
        ]
    )
    first, second = cohorts_from_book(book)
    assert (first.opened, first.closes, first.longs, first.shorts) == (
        OPEN,
        EXIT,
        ("AAA",),
        ("BBB",),
    )
    assert (second.opened, second.closes, second.longs) == (EXIT, None, ("CCC",))


def test_a_cohort_is_sized_marked_and_closed_on_the_pessimistic_side() -> None:
    positions, daily = simulate([COHORT], FrameMarket(QUOTES, []), "XNYS", EXIT)
    (spread,) = positions
    assert (spread["long_strike"], spread["short_strike"], spread["expiry"]) == (100, 110, EXPIRY)
    assert spread["entry_debit"] == pytest.approx(4.0)
    cost = 4.0 * CONTRACT + 2 * COMMISSION_PER_LEG
    qty = RISK_BUDGET / cost
    assert spread["quantity"] == pytest.approx(qty)

    by_day = {d["date"]: d for d in daily}
    cash = 1.0 - RISK_BUDGET
    # Open day: marked at once at what closing would raise, 4.9 - 1.1.
    assert by_day[OPEN]["equity"] == pytest.approx(cash + qty * 3.8 * CONTRACT)
    assert by_day[MID]["equity"] == pytest.approx(cash + qty * 4.4 * CONTRACT)
    # Exit: 7.0 - 2.0 = 5.0 a share, less commission to close both legs.
    assert by_day[EXIT]["equity"] == pytest.approx(
        cash + qty * (5.0 * CONTRACT - 2 * COMMISSION_PER_LEG)
    )
    assert by_day[EXIT]["open_positions"] == 0
    assert spread["status"] == "closed" and spread["mark_basis"] == "quote"


def test_a_missing_leg_is_valued_at_its_last_sound_quote_and_says_so() -> None:
    """The day has a snapshot, but the sold 110 call is missing from it — a strike that drifted
    out of the captured band. Valuing that spread at intrinsic would call a month-dated spread
    worthless; it is valued with the last sound ask seen for the missing leg instead."""
    quotes = [q for q in QUOTES if q["snapshot_date"] != MID]
    quotes.append(quote(MID, 100, 6.0, 6.1, spot=104.0))
    still_open = Cohort(OPEN, None, ("AAA",), (), "10")
    positions, daily = simulate([still_open], FrameMarket(quotes, []), "XNYS", MID)
    qty = RISK_BUDGET / (4.0 * CONTRACT + 2 * COMMISSION_PER_LEG)
    mid = next(d for d in daily if d["date"] == MID)
    # 6.0 bid on the bought leg, less the 1.1 ask last seen on the sold leg.
    assert mid["equity"] == pytest.approx(1.0 - RISK_BUDGET + qty * 4.9 * CONTRACT)
    assert positions[0]["mark_basis"] == "last quote"


def test_an_absurd_quote_is_not_believed() -> None:
    """A bid of zero on the bought leg would mark the spread at nothing; the last sound quote
    stands in for it."""
    quotes = [q for q in QUOTES if q["snapshot_date"] != MID]
    quotes += [quote(MID, 100, 0.0, 6.1), quote(MID, 110, 1.5, 1.6)]
    still_open = Cohort(OPEN, None, ("AAA",), (), "10")
    positions, _ = simulate([still_open], FrameMarket(quotes, []), "XNYS", MID)
    # 4.9 bid last seen on the bought leg, less today's sound 1.6 ask on the sold leg.
    assert positions[0]["mark_value"] == pytest.approx(3.3)
    assert positions[0]["mark_basis"] == "last quote"


def test_only_liquid_strikes_are_traded() -> None:
    """The 110 call has too few contracts open, so the sold leg moves to the nearest liquid strike,
    115; a stock with no two liquid strikes is skipped and says why."""
    quotes = [q for q in QUOTES if not (q["snapshot_date"] == OPEN and q["strike"] == 110)]
    quotes += [quote(OPEN, 110, 1.0, 1.1, oi=2), quote(OPEN, 115, 0.5, 0.6)]
    quotes += [quote(OPEN, 100, 2.0, 9.0, kind="put") | {"ticker": "BBB"}]
    quotes += [quote(OPEN, 90, 0.5, 4.0, kind="put") | {"ticker": "BBB"}]
    cohort = Cohort(OPEN, None, ("AAA",), ("BBB",), "10")
    positions, _ = simulate([cohort], FrameMarket(quotes, []), "XNYS", OPEN)
    by_ticker = {p["ticker"]: p for p in positions}
    assert by_ticker["AAA"]["short_strike"] == 115
    assert by_ticker["AAA"]["entry_debit"] == pytest.approx(5.0 - 0.5)
    assert by_ticker["BBB"]["status"] == "skipped"
    assert by_ticker["BBB"]["note"] == "fewer than two liquid strikes"


def test_an_expiry_before_the_exit_settles_at_intrinsic() -> None:
    late_exit = dt.date(2026, 9, 25)
    closes = [{"ticker": "AAA", "date": EXPIRY, "close": 107.0}]
    quotes = [q for q in QUOTES if q["snapshot_date"] != EXIT]
    cohort = Cohort(OPEN, late_exit, ("AAA",), (), "10")
    positions, _ = simulate([cohort], FrameMarket(quotes, closes), "XNYS", late_exit)
    assert positions[0]["mark_basis"] == "settled"
    assert positions[0]["mark_value"] == pytest.approx(7.0)


def test_names_that_cannot_be_traded_are_kept_with_the_reason() -> None:
    quotes = [*QUOTES, quote(OPEN, 100, 9.0, 9.5, expiry=EARLY, kind="put") | {"ticker": "BBB"}]
    cohort = Cohort(OPEN, EXIT, ("AAA", "ZZZ"), ("BBB",), "10")
    positions, _ = simulate([cohort], FrameMarket(quotes, []), "XNYS", EXIT)
    notes = {p["ticker"]: p.get("note") for p in positions if p["status"] == "skipped"}
    assert notes == {
        "ZZZ": "no chain captured on the open date",
        "BBB": "no captured expiry reaches the exit",
    }


def test_cohorts_from_the_live_date_are_live_and_earlier_ones_replay() -> None:
    later = Cohort(LIVE_SINCE, None, ("AAA",), (), "10")
    quotes = [
        q | {"snapshot_date": LIVE_SINCE, "expiry": dt.date(2026, 11, 20)} for q in QUOTES[:2]
    ]
    positions, daily = simulate([later], FrameMarket(quotes, []), "XNYS", LIVE_SINCE)
    assert positions[0]["phase"] == "live" and positions[0]["status"] == "open"
    assert daily[0]["phase"] == "live"
    early, _ = simulate([COHORT], FrameMarket(QUOTES, []), "XNYS", EXIT)
    assert early[0]["phase"] == "replay"


def test_a_cheap_option_with_an_ordinary_gap_is_sound() -> None:
    from quantpulse.options.book import sound

    assert sound(0.50, 0.70), "a 20-cent gap is an ordinary market, though 33% of its midpoint"
    assert sound(10.0, 11.5)
    assert not sound(2.5, 10.0), "a 7.50 gap on a 6 option is not a market"
    assert not sound(0.0, 1.74), "no bid"
    assert not sound(5.0, 5.0)
