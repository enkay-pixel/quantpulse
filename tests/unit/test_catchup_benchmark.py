"""A missing benchmark bar is its own reason to re-ingest a session — for a while.

Coverage cannot see this gap: the benchmark is one ticker, so losing it costs 1/29 of a JSE
session and `missing_trading_days` correctly calls that day complete. But `fct_alpha_beta`
and `fct_portfolio_vs_benchmark` inner-join the benchmark, so its absence deletes the whole
day from them. When a benchmark bar goes missing nothing retries it, and the gap surfaces
only by hand-comparing day counts between the two marts.

The eligibility window is the load-bearing part. Coverage-triggered retries are
self-limiting — a re-ingest that works fixes the coverage that asked for it. This trigger is
not, because the vendor may never publish the bar, so it has to expire on its own.
"""

import datetime as dt

from quantpulse.orchestration.catchup import (
    BENCHMARK_RETRY_SESSIONS,
    benchmark_gaps_to_retry,
)

# Ten consecutive ingested sessions, newest last.
SESSIONS = [dt.date(2026, 8, 3) + dt.timedelta(days=i) for i in range(10)]
RECENT = SESSIONS[-BENCHMARK_RETRY_SESSIONS:]
OLD = SESSIONS[:-BENCHMARK_RETRY_SESSIONS]


def test_complete_benchmark_asks_for_nothing() -> None:
    assert benchmark_gaps_to_retry(SESSIONS, SESSIONS) == []


def test_a_recent_missing_bar_is_requested() -> None:
    """The case this guards: the market ingested the session, the benchmark did not arrive."""
    gap = RECENT[1]
    have = [d for d in SESSIONS if d != gap]
    assert benchmark_gaps_to_retry(SESSIONS, have) == [gap]


def test_eligibility_expires_so_a_never_published_bar_stops_being_retried() -> None:
    """The bound that keeps this from retrying forever.

    A bar the vendor never publishes would otherwise re-ingest its session three times a
    day for the whole 30-day lookback. Past the window the gap is still *reported* by the
    benchmark_freshness asset check — reporting forever is cheap, retrying forever is not.
    """
    stale = OLD[0]
    have = [d for d in SESSIONS if d != stale]
    assert benchmark_gaps_to_retry(SESSIONS, have) == []


def test_the_window_counts_sessions_not_calendar_days() -> None:
    """Weekends and holidays must not age a gap out early — five *sessions* of chances."""
    sparse = [dt.date(2026, 8, 3), dt.date(2026, 8, 17), dt.date(2026, 9, 7)]
    assert benchmark_gaps_to_retry(sparse, []) == sparse


def test_only_sessions_the_market_ingested_are_considered() -> None:
    """A day with no data at all belongs to missing_trading_days. Requesting it here too
    would spend the session's retry budget at double rate for one underlying cause."""
    ingested = [d for d in SESSIONS if d != SESSIONS[-1]]
    gaps = benchmark_gaps_to_retry(ingested, ingested)
    assert SESSIONS[-1] not in gaps
    assert gaps == []


def test_multiple_gaps_come_back_oldest_first() -> None:
    """Matches missing_trading_days' ordering, so the sensor's per-tick cap takes the
    oldest sessions — the ones closest to ageing out of eligibility."""
    have = [d for d in SESSIONS if d not in (RECENT[0], RECENT[2])]
    assert benchmark_gaps_to_retry(SESSIONS, have) == [RECENT[0], RECENT[2]]


def test_a_benchmark_with_no_bars_at_all_requests_only_the_window() -> None:
    """Never more than the window, however long the drought."""
    gaps = benchmark_gaps_to_retry(SESSIONS, [])
    assert gaps == RECENT
    assert len(gaps) == BENCHMARK_RETRY_SESSIONS


def test_duplicate_session_dates_do_not_shrink_the_window() -> None:
    """The query groups by date, but a caller passing raw rows must not silently get a
    narrower window than the constant promises."""
    assert benchmark_gaps_to_retry(SESSIONS + SESSIONS, []) == RECENT
