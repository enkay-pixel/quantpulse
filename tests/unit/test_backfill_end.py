"""A backfill never asks the vendor for a session that has not closed.

Found in M13's phase 3 (2026-10-27): `quantpulse backfill` ended on `last_trading_day()`, which is
today's session from midnight on, so a backfill run while Europe traded would have stored the live
prices as the day's closes. Stored bars are never rewritten (ADR 0006), so they would have stayed.
The end was given by hand that day. The day before is exposed as well while today trades: the
request runs to the end plus one day, and the live bar can come back under the window's last date
(data-dictionary.md), which is why the catch-up sensor does not fetch yesterday until today closes.

Every case runs on a frozen clock against the real exchange calendars. The universe and the vendor
are stubbed, and the refusal is checked to come before the database is opened at all.
"""

import datetime as dt
import logging
from zoneinfo import ZoneInfo

import pytest

from quantpulse import cli
from quantpulse.data import ingest
from quantpulse.data.calendar import EXCHANGES, is_trading_day, last_closed_session
from quantpulse.data.ingest import fetch_reaches_open_session, newest_safe_end

BERLIN = ZoneInfo("Europe/Berlin")
FRI, SAT, SUN, MON, TUE, WED = (dt.date(2026, 10, d) for d in (23, 24, 25, 26, 27, 28))


def berlin(day: dt.date, hour: int, minute: int = 0) -> dt.datetime:
    return dt.datetime(day.year, day.month, day.day, hour, minute, tzinfo=BERLIN)


# Xetra trades 09:00-17:30; `is_post_close` counts it closed from 18:00.
TRADING = berlin(TUE, 14)
PREMARKET = berlin(TUE, 8)
CLOSED = berlin(TUE, 18)
# When phase 3 ran: Johannesburg, London and the four European markets trading, New York not open.
PHASE_3 = dt.datetime(2026, 10, 27, 13, 0, tzinfo=dt.UTC)
EVENING = dt.datetime(2026, 10, 27, 20, 0, tzinfo=dt.UTC)  # every market closed, New York at 16:00


@pytest.mark.parametrize(
    ("now", "closed"),
    [
        (TRADING, MON),
        (PREMARKET, MON),
        (berlin(TUE, 17, 45), MON),  # trading has ended, but the close has not settled
        (CLOSED, TUE),
        (berlin(SAT, 12), FRI),
        (berlin(MON, 8), FRI),
        (dt.datetime(2026, 10, 27, 13, 0, tzinfo=dt.UTC), MON),  # 14:00 in Frankfurt
    ],
)
def test_the_newest_closed_session_waits_for_the_close(now: dt.datetime, closed: dt.date) -> None:
    assert last_closed_session(now, "XETR") == closed


@pytest.mark.parametrize(
    ("now", "end"),
    [
        (TRADING, FRI),  # Monday's request runs to Tuesday, which is trading
        (berlin(MON, 14), FRI),  # Friday's runs to Saturday
        (PREMARKET, MON),  # nothing trades yet, as the catch-up sensor's guard has it
        (CLOSED, TUE),
        (berlin(SAT, 12), FRI),
    ],
)
def test_the_default_end_is_the_newest_session_safe_to_fetch(
    now: dt.datetime, end: dt.date
) -> None:
    assert newest_safe_end(now, "XETR") == end


@pytest.mark.parametrize(
    ("now", "end", "reaches"),
    [
        (TRADING, WED, True),
        (TRADING, TUE, True),
        (TRADING, MON, True),  # the request runs to Tuesday
        (TRADING, SUN, False),
        (TRADING, FRI, False),
        (PREMARKET, TUE, True),  # today's session has not traded yet
        (PREMARKET, MON, False),
        (CLOSED, TUE, False),
        (berlin(MON, 14), SUN, True),  # runs to Monday, which is trading
        (berlin(MON, 14), SAT, False),
    ],
)
def test_an_end_is_refused_when_its_fetch_reaches_a_session_not_closed(
    now: dt.datetime, end: dt.date, reaches: bool
) -> None:
    assert fetch_reaches_open_session(end, now, "XETR") is reaches


def test_the_default_is_safe_and_newest_at_every_half_hour_in_every_market() -> None:
    """Across both clock changes, a weekend, Thanksgiving and New York's early close after it."""
    instants = [
        dt.datetime(2026, 10, 22, tzinfo=dt.UTC) + dt.timedelta(minutes=30 * i)
        for i in range(13 * 48)
    ] + [
        dt.datetime(2026, 11, 25, tzinfo=dt.UTC) + dt.timedelta(minutes=30 * i)
        for i in range(3 * 48)
    ]
    for code in EXCHANGES:
        for now in instants:
            end = newest_safe_end(now, code)
            assert is_trading_day(end, code), (code, now)
            assert not fetch_reaches_open_session(end, now, code), (code, now, end)
            closed = last_closed_session(now, code)
            later = [
                d
                for d in (end + dt.timedelta(days=n) for n in range(1, (closed - end).days + 1))
                if is_trading_day(d, code)
            ]
            assert all(fetch_reaches_open_session(d, now, code) for d in later), (code, now, end)


MEMBERS = {
    "XNYS": ["AAPL"],
    "XJSE": ["NPN.JO"],
    "XLON": ["AZN.L"],
    "XETR": ["SAP.DE"],
    "XPAR": ["MC.PA"],
    "XSWX": ["NESN.SW"],
    "XAMS": ["ASML.AS"],
}


class _Session:
    def __enter__(self):  # type: ignore[no-untyped-def]
        return self

    def __exit__(self, *exc):  # type: ignore[no-untyped-def]
        return False


@pytest.fixture
def fetched(monkeypatch: pytest.MonkeyPatch) -> dict[str, dt.date]:
    """Run `_backfill` against a stubbed universe and vendor, recording each ticker's end."""
    ends: dict[str, dt.date] = {}

    def fake_fetch(tickers, start, end):  # type: ignore[no-untyped-def]
        ends.update(dict.fromkeys(tickers, end))
        return []

    monkeypatch.setattr("quantpulse.db.get_session", lambda *a, **k: _Session())
    monkeypatch.setattr(
        "quantpulse.data.universe.active_tickers", lambda session, code=None: MEMBERS[code]
    )
    monkeypatch.setattr(ingest, "wrong_currency", lambda members, expected: ({}, []))
    monkeypatch.setattr(ingest, "fetch_daily_bars", fake_fetch)
    monkeypatch.setattr(ingest, "upsert_prices", lambda session, bars: 0)
    return ends


def test_the_default_end_follows_each_markets_own_close(fetched: dict[str, dt.date]) -> None:
    """The phase 3 run without `--end`: the markets trading stop at Friday, and New York, which
    has not opened, at Monday."""
    cli._backfill(None, None, None, now=PHASE_3)
    assert fetched == {
        t: (MON if code == "XNYS" else FRI) for code, members in MEMBERS.items() for t in members
    }


def test_one_market_s_default_end_is_its_own(fetched: dict[str, dt.date]) -> None:
    cli._backfill(None, None, "XETR", now=PHASE_3)
    assert fetched == {"SAP.DE": FRI}


def no_database(*a, **k):  # type: ignore[no-untyped-def]
    raise AssertionError("the refusal must come before the database is opened")


def test_an_end_reaching_an_open_session_is_refused_before_the_database_opens(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Phase 3's own `--end 2026-10-26`: its request ran to the 27th while Europe traded."""
    monkeypatch.setattr("quantpulse.db.get_session", no_database)
    with caplog.at_level(logging.ERROR), pytest.raises(SystemExit) as exc:
        cli._backfill(None, MON, None, now=PHASE_3)
    assert exc.value.code == 1
    for code in ("XAMS", "XETR", "XJSE", "XLON", "XPAR", "XSWX"):
        assert f"{code} (newest safe end {FRI})" in caplog.text
    assert "XNYS" not in caplog.text, "New York has not opened, so Monday is safe there"


def test_a_start_after_the_default_end_is_refused_rather_than_sent_to_the_vendor(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Today's bars asked for while today trades: the default end is now Friday, and a backwards
    window would only fail inside the vendor's retries."""
    monkeypatch.setattr("quantpulse.db.get_session", no_database)
    with caplog.at_level(logging.ERROR), pytest.raises(SystemExit) as exc:
        cli._backfill(TUE, None, "XETR", now=PHASE_3)
    assert exc.value.code == 1
    assert f"XETR ({FRI})" in caplog.text


def test_the_same_end_is_fetched_once_every_market_has_closed(
    fetched: dict[str, dt.date],
) -> None:
    cli._backfill(None, MON, None, now=EVENING)
    assert set(fetched.values()) == {MON}


def test_after_every_close_the_default_end_is_today(fetched: dict[str, dt.date]) -> None:
    cli._backfill(None, None, None, now=EVENING)
    assert set(fetched.values()) == {TUE}
