"""A listing quoted in a currency other than its market's is refused before its bars are stored.

Found onboarding London: Yahoo quotes Compass and IHG there in US dollars while every other London
line is in pence. Their bars passed every check, because the moves are real moves in dollars, and
nothing downstream could tell. So the backfill, which is how a listing first arrives, asks the
vendor first. The vendor is stubbed: a test reaching Yahoo measures Yahoo, not the rule.
"""

import logging

import pytest

from quantpulse import cli
from quantpulse.data import ingest
from quantpulse.data.ingest import wrong_currency

QUOTED = {"AZN.L": "GBp", "CPG.L": "USD", "NPN.JO": "ZAc", "AAPL": "USD", "GONE.L": None}


@pytest.fixture(autouse=True)
def _vendor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ingest, "_quote_currency", QUOTED.__getitem__)


def test_a_listing_in_another_currency_is_named_with_what_it_is_quoted_in() -> None:
    wrong, unknown = wrong_currency(["AZN.L", "CPG.L", "GONE.L"], "GBp")
    assert wrong == {"CPG.L": "USD"}
    assert unknown == ["GONE.L"]


def test_each_market_is_held_to_its_own_currency() -> None:
    """Dollars are right on the NYSE and wrong in London: the rule is per market, not a list."""
    assert wrong_currency(["AAPL"], "USD") == ({}, [])
    assert wrong_currency(["NPN.JO"], "ZAc") == ({}, [])
    assert wrong_currency(["AAPL"], "GBp") == ({"AAPL": "USD"}, [])


@pytest.fixture
def backfill(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """Run `_backfill` against a stubbed universe, recording what it fetches."""
    fetched: list[str] = []
    members = {"XLON": ["AZN.L"], "XJSE": ["NPN.JO"], "XNYS": ["AAPL"]}

    class _Session:
        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, *exc):  # type: ignore[no-untyped-def]
            return False

    monkeypatch.setattr("quantpulse.db.get_session", lambda *a, **k: _Session())
    monkeypatch.setattr(
        "quantpulse.data.universe.active_tickers",
        lambda session, code=None: list(members.get(code, [])),
    )

    def fake_fetch(tickers, start, end):  # type: ignore[no-untyped-def]
        fetched.extend(tickers)
        return []

    monkeypatch.setattr(ingest, "fetch_daily_bars", fake_fetch)
    monkeypatch.setattr(ingest, "upsert_prices", lambda session, bars: 0)
    return members, fetched


def test_a_backfill_refuses_before_fetching_when_a_listing_is_in_another_currency(
    backfill, caplog: pytest.LogCaptureFixture
) -> None:  # type: ignore[no-untyped-def]
    members, fetched = backfill
    members["XLON"].append("CPG.L")
    with caplog.at_level(logging.ERROR), pytest.raises(SystemExit) as exc:
        cli._backfill(None, None, "XLON")
    assert exc.value.code == 1
    assert fetched == [], "nothing may be stored for a market holding a mis-quoted listing"
    assert "CPG.L (USD, not GBp)" in caplog.text


def test_a_backfill_of_every_market_checks_each_against_its_own(backfill) -> None:  # type: ignore[no-untyped-def]
    _, fetched = backfill
    cli._backfill(None, None, None)
    assert sorted(fetched) == ["AAPL", "AZN.L", "NPN.JO"]


def test_a_currency_the_vendor_cannot_report_warns_but_does_not_block(
    backfill, caplog: pytest.LogCaptureFixture
) -> None:  # type: ignore[no-untyped-def]
    """A lookup that fails is the vendor's hiccup, not evidence of a wrong currency; blocking on it
    would stop every routine refill on a bad afternoon."""
    members, fetched = backfill
    members["XLON"].append("GONE.L")
    with caplog.at_level(logging.WARNING):
        cli._backfill(None, None, "XLON")
    assert "GONE.L" in fetched
    assert "quote currency unconfirmed for GONE.L" in caplog.text
