"""A session missing some tickers is its own reason to re-ingest it — for a while, and only
until a model has been trained on it.

Coverage cannot see this gap: a session counts as ingested once the floor share of the universe
has arrived, and the scheduled ingest fetches only its own day, so the tickers that did not
arrive are never asked for again. The benchmark is the sharpest case — the marts inner-join it,
so its absence deletes the whole day from them — but any ticker missing a day also stretches its
returns and labels across the gap, because features shift by row.

Three bounds are load-bearing. The eligibility window, because the vendor may never publish a
bar and the retry must expire on its own. The training cut-off, because a session a retrain has
used must not change underneath the model, or the weekly refit that checks it stops
reproducing. And the fetch window, because a one-day request for yesterday made while today is
trading can come back with today's price under yesterday's date.
"""

import datetime as dt
from zoneinfo import ZoneInfo

import pytest

from quantpulse.data.calendar import session_in_progress
from quantpulse.orchestration import catchup
from quantpulse.orchestration.catchup import (
    TICKER_GAP_RETRY_SESSIONS,
    fetch_would_end_in_open_session,
    ticker_gaps_to_retry,
)

# Ten consecutive ingested sessions, newest last.
SESSIONS = [dt.date(2026, 8, 3) + dt.timedelta(days=i) for i in range(10)]
RECENT = SESSIONS[-TICKER_GAP_RETRY_SESSIONS:]
OLD = SESSIONS[:-TICKER_GAP_RETRY_SESSIONS]
NEVER_TRAINED = None
NEW_YORK = ZoneInfo("America/New_York")


def test_complete_sessions_ask_for_nothing() -> None:
    assert ticker_gaps_to_retry(SESSIONS, [], NEVER_TRAINED) == []


def test_a_recent_gap_is_requested() -> None:
    """The case this guards: the market ingested the session, some tickers did not arrive."""
    assert ticker_gaps_to_retry(SESSIONS, [RECENT[1]], NEVER_TRAINED) == [RECENT[1]]


def test_eligibility_expires_so_a_never_published_bar_stops_being_retried() -> None:
    """The bound that keeps this from retrying forever.

    A bar the vendor never publishes would otherwise re-ingest its session three times a day
    for the whole 30-day lookback. Past the window the gap is still *reported* by the post-close
    check — reporting forever is cheap, retrying forever is not.
    """
    assert ticker_gaps_to_retry(SESSIONS, [OLD[0]], NEVER_TRAINED) == []


def test_a_session_a_retrain_has_used_is_never_filled() -> None:
    """A model's training data must not change after it was fitted. The weekly shadow scorer
    refits every week's candidates and needs the refit to reproduce exactly; a gap filled after
    the retrain that saw it would make that week unrecoverable."""
    trained_on = RECENT[2]
    gaps = [RECENT[1], RECENT[2], RECENT[3]]
    assert ticker_gaps_to_retry(SESSIONS, gaps, trained_on) == [RECENT[3]]


def test_a_session_after_the_newest_retrain_is_still_filled() -> None:
    """The cut-off is strict: the retrain's own date is used, the next session is not."""
    assert ticker_gaps_to_retry(SESSIONS, [RECENT[4]], RECENT[3]) == [RECENT[4]]


def test_the_window_counts_sessions_not_calendar_days() -> None:
    """Weekends and holidays must not age a gap out early — five *sessions* of chances."""
    sparse = [dt.date(2026, 8, 3), dt.date(2026, 8, 17), dt.date(2026, 9, 7)]
    assert ticker_gaps_to_retry(sparse, sparse, NEVER_TRAINED) == sparse


def test_only_sessions_the_market_ingested_are_considered() -> None:
    """A day with no data at all belongs to missing_trading_days. Requesting it here too would
    spend the session's retry budget at double rate for one underlying cause."""
    ingested = SESSIONS[:-1]
    assert ticker_gaps_to_retry(ingested, [SESSIONS[-1]], NEVER_TRAINED) == []


def test_multiple_gaps_come_back_oldest_first() -> None:
    """Matches missing_trading_days' ordering, so the sensor's per-tick cap takes the oldest
    sessions — the ones closest to ageing out of eligibility."""
    gaps = [RECENT[2], RECENT[0]]
    assert ticker_gaps_to_retry(SESSIONS, gaps, NEVER_TRAINED) == [RECENT[0], RECENT[2]]


def test_never_more_than_the_window_however_long_the_drought() -> None:
    gaps = ticker_gaps_to_retry(SESSIONS, SESSIONS, NEVER_TRAINED)
    assert gaps == RECENT
    assert len(gaps) == TICKER_GAP_RETRY_SESSIONS


def test_duplicate_session_dates_do_not_shrink_the_window() -> None:
    """The query groups by date, but a caller passing raw rows must not silently get a narrower
    window than the constant promises."""
    assert ticker_gaps_to_retry(SESSIONS + SESSIONS, SESSIONS, NEVER_TRAINED) == RECENT


@pytest.mark.parametrize(
    ("now", "trading"),
    [
        (dt.datetime(2026, 10, 13, 10, 10, tzinfo=NEW_YORK), True),
        (dt.datetime(2026, 10, 13, 9, 29, tzinfo=NEW_YORK), False),
        (dt.datetime(2026, 10, 13, 16, 0, tzinfo=NEW_YORK), False),
        (dt.datetime(2026, 10, 10, 12, 0, tzinfo=NEW_YORK), False),  # a Saturday
        (dt.datetime(2026, 11, 27, 13, 30, tzinfo=NEW_YORK), False),  # after an early close
    ],
)
def test_a_session_is_in_progress_only_between_its_own_open_and_close(
    now: dt.datetime, trading: bool
) -> None:
    assert session_in_progress(now, "XNYS") is trading


def test_yesterday_is_not_fetched_while_today_trades(monkeypatch: pytest.MonkeyPatch) -> None:
    """The one window that can misdate a bar: yesterday's one-day request runs up to today,
    and today is still open."""
    monkeypatch.setattr(catchup, "session_in_progress", lambda now, exchange: True)
    now = dt.datetime(2026, 10, 13, 11, 0, tzinfo=NEW_YORK)
    assert fetch_would_end_in_open_session(dt.date(2026, 10, 12), now, "XNYS")
    assert not fetch_would_end_in_open_session(dt.date(2026, 10, 9), now, "XNYS"), (
        "an older session's window ends on a day long closed"
    )
    assert not fetch_would_end_in_open_session(dt.date(2026, 10, 13), now, "XNYS"), (
        "today's own window ends tomorrow"
    )


def test_yesterday_is_fetched_once_today_has_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(catchup, "session_in_progress", lambda now, exchange: False)
    now = dt.datetime(2026, 10, 13, 17, 0, tzinfo=NEW_YORK)
    assert not fetch_would_end_in_open_session(dt.date(2026, 10, 12), now, "XNYS")


def test_the_guard_reads_the_date_in_exchange_time() -> None:
    """01:00 UTC on a Tuesday is still Monday evening in New York, when Monday's window ends on
    a Tuesday that has not opened yet — so nothing is blocked, on the market's own clock."""
    now = dt.datetime(2026, 10, 13, 1, 0, tzinfo=dt.UTC)  # Mon 21:00 New York
    assert not fetch_would_end_in_open_session(dt.date(2026, 10, 12), now, "XNYS")
