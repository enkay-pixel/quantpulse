"""Turning the vendor's quote summary into short-interest rows, without the network."""

import datetime as dt

import pytest

from quantpulse.research.short_interest import (
    NoShortInterestReturned,
    fetch_short_interest,
    parse_info,
)

SEPT_30 = int(dt.datetime(2026, 9, 30, tzinfo=dt.UTC).timestamp())
AUG_31 = int(dt.datetime(2026, 8, 31, tzinfo=dt.UTC).timestamp())

FULL = {
    "sharesShort": 42_673_721,
    "sharesShortPriorMonth": 56_990_026,
    "dateShortInterest": SEPT_30,
    "sharesShortPreviousMonthDate": AUG_31,
    "shortRatio": 4.27,
    "shortPercentOfFloat": 0.0917,
    "floatShares": 460_412_648,
    "sharesOutstanding": 504_500_990,
}


def test_a_full_summary_becomes_one_row_with_dates() -> None:
    row = parse_info("GME", FULL)
    assert row is not None
    assert row["settlement_date"] == dt.date(2026, 9, 30)
    assert row["prior_settlement_date"] == dt.date(2026, 8, 31)
    assert row["shares_short"] == 42_673_721
    assert row["days_to_cover"] == pytest.approx(4.27)
    assert row["short_pct_float"] == pytest.approx(0.0917)


@pytest.mark.parametrize("missing", ["sharesShort", "dateShortInterest"])
def test_a_count_without_its_date_or_a_date_without_its_count_is_no_row(missing: str) -> None:
    """Either half alone cannot be placed in history: it is what a partial response looks like."""
    assert parse_info("GME", {k: v for k, v in FULL.items() if k != missing}) is None


def test_garbage_fields_become_none_rather_than_wrong_numbers() -> None:
    row = parse_info("GME", {**FULL, "shortPercentOfFloat": "n/a", "floatShares": -1})
    assert row is not None
    assert row["short_pct_float"] is None
    assert row["float_shares"] is None


def test_one_ticker_failing_does_not_cost_the_others() -> None:
    def fetch(ticker: str) -> dict[str, object]:
        if ticker == "BAD":
            raise ConnectionError("vendor hiccup")
        if ticker == "ETF":
            return {"quoteType": "ETF"}  # no short interest: ordinary
        return FULL

    rows = fetch_short_interest(["GME", "BAD", "ETF"], fetch=fetch)
    assert [r["ticker"] for r in rows] == ["GME"]


def test_nothing_at_all_from_a_whole_list_is_an_error() -> None:
    with pytest.raises(NoShortInterestReturned):
        fetch_short_interest(["A", "B"], fetch=lambda t: {})


def test_an_empty_list_is_a_no_op_not_an_error() -> None:
    assert fetch_short_interest([], fetch=lambda t: FULL) == []
