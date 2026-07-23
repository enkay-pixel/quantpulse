"""Rows must be stamped with the exchange's date, never the container's UTC date.

Containers run UTC. Under EDT the 19:00 ET jobs land at 23:00 UTC and the two agree, so
this is invisible all summer. Under EST they land at 00:00 UTC and `date.today()` returns
*tomorrow* — silently shifting the options history by a day at the November DST change, in
the one dataset that cannot be rebuilt.
"""

import datetime as dt
from zoneinfo import ZoneInfo

import pytest

from quantpulse.data.calendar import NEW_YORK, market_today

UTC = dt.UTC
SCHEDULE_HOUR_ET = 19  # daily_process_schedule, which writes the option snapshot


class FrozenDatetime(dt.datetime):
    """Stands in for dt.datetime with `now()` pinned to a chosen instant."""

    frozen: dt.datetime

    @classmethod
    def now(cls, tz: dt.tzinfo | None = None) -> dt.datetime:  # type: ignore[override]
        return cls.frozen.astimezone(tz) if tz else cls.frozen


@pytest.fixture
def at_utc(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    def _freeze(moment: dt.datetime) -> None:
        FrozenDatetime.frozen = moment
        monkeypatch.setattr("quantpulse.data.calendar.dt.datetime", FrozenDatetime)

    return _freeze


@pytest.mark.parametrize(
    ("session", "tz_label"),
    [(dt.date(2026, 7, 23), "EDT"), (dt.date(2026, 11, 20), "EST")],
)
def test_evening_run_is_stamped_with_the_session_it_belongs_to(
    at_utc, session: dt.date, tz_label: str
) -> None:  # type: ignore[no-untyped-def]
    """The regression: 19:00 EST is 00:00 UTC the next day, so the naive UTC date is wrong.
    Both sides of the DST change must yield the session's own date."""
    run_time = dt.datetime(
        session.year, session.month, session.day, SCHEDULE_HOUR_ET, tzinfo=NEW_YORK
    )
    at_utc(run_time)
    assert market_today() == session, f"{tz_label} run mis-stamped"


def test_est_evening_is_the_case_utc_gets_wrong() -> None:
    """Documents *why* the helper exists, independent of the implementation."""
    est_run = dt.datetime(2026, 11, 20, SCHEDULE_HOUR_ET, tzinfo=NEW_YORK)
    assert est_run.astimezone(UTC).date() == dt.date(2026, 11, 21)  # naive UTC: tomorrow
    assert est_run.astimezone(NEW_YORK).date() == dt.date(2026, 11, 20)  # exchange: today


def test_midnight_utc_still_belongs_to_the_previous_session(at_utc) -> None:  # type: ignore[no-untyped-def]
    """A snapshot that runs past 20:00 EDT crosses UTC midnight mid-run — exactly what
    split one snapshot across two dates on 2026-07-22."""
    at_utc(dt.datetime(2026, 7, 24, 0, 30, tzinfo=UTC))  # 20:30 EDT on the 23rd
    assert market_today() == dt.date(2026, 7, 23)


def test_daytime_is_unaffected(at_utc) -> None:  # type: ignore[no-untyped-def]
    """Mid-session the two clocks agree; the fix must not perturb the common case."""
    at_utc(dt.datetime(2026, 7, 23, 14, 30, tzinfo=UTC))  # 10:30 EDT
    assert market_today() == dt.date(2026, 7, 23)


def test_new_york_is_the_exchange_zone_not_a_fixed_offset() -> None:
    """A fixed -05:00 would reintroduce the bug every summer."""
    assert ZoneInfo("America/New_York") == NEW_YORK
    july = dt.datetime(2026, 7, 23, 12, tzinfo=NEW_YORK).utcoffset()
    january = dt.datetime(2026, 1, 23, 12, tzinfo=NEW_YORK).utcoffset()
    assert july != january  # the zone actually shifts
