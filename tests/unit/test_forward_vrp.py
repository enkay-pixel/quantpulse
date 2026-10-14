"""Guards on the forward variance risk premium, on synthetic rows whose answers are known.

What has to be pinned is that the measure is the pre-registered one: the window ends where the
last realization window closed, the headline is the mean of daily means rather than of
ticker-days, the error allows for overlapping windows, a units error stops the run instead of
being read, and each verdict needs its own side of the bound.
"""

import datetime as dt
from typing import Any

import pandas as pd
import pytest

from quantpulse.options import forward_vrp as fv
from quantpulse.options.forward_vrp import last_snapshot, read, summarize, units_ok

SESSIONS = [dt.date(2026, 7, 1) + dt.timedelta(days=i) for i in range(60)]


def test_the_window_ends_where_the_last_realization_window_closed() -> None:
    """A snapshot at session t needs sessions t+1..t+21; with data ending at session 50 the last
    such snapshot is session 29."""
    assert last_snapshot(SESSIONS, SESSIONS[50]) == SESSIONS[29]
    with pytest.raises(ValueError, match="not a trading session"):
        last_snapshot(SESSIONS, dt.date(2025, 1, 1))


@pytest.mark.parametrize(("vol", "ok"), [(0.30, True), (0.02, False), (19.0, False)])
def test_a_units_error_is_caught_on_either_side(vol: float, ok: bool) -> None:
    """A daily standard deviation reads about 0.02 for a stock; one annualized twice reads in
    the tens. Both are errors, not results."""
    assert units_ok(vol) is ok


def _rows(days: dict[dt.date, list[float]], vol: float = 0.30) -> pd.DataFrame:
    out = []
    for day, premiums in days.items():
        for i, p in enumerate(premiums):
            out.append(
                {
                    "ticker": f"T{i}",
                    "snapshot_date": day,
                    "atm_iv": vol + p,
                    "atm_days": 30,
                    "forward_realized_vol_21d": vol,
                    "trailing_realized_vol_21d": vol + 0.01,
                    "forward_premium": p,
                    "trailing_premium": p - 0.01,
                }
            )
    return pd.DataFrame(out)


def test_the_headline_weighs_days_not_ticker_days() -> None:
    """Fifty tickers on one day share the market's volatility, so a day with more of them must
    not count for more. One day of ten tickers at +0.1 and one of one ticker at -0.1 average to
    zero by day, and to +0.08 by ticker-day."""
    rows = _rows({SESSIONS[0]: [0.1] * 10, SESSIONS[1]: [-0.1]})
    out = summarize(rows)
    assert out["headline"]["mean"] == pytest.approx(0.0)
    assert out["ticker_day_mean"] == pytest.approx(0.1 * 10 / 11 - 0.1 / 11)


def test_a_units_error_stops_the_reading() -> None:
    out = summarize(_rows({SESSIONS[0]: [0.1], SESSIONS[1]: [0.1]}, vol=0.02))
    assert out["units_ok"] is False
    assert "headline" not in out, "a premium was read from series in different units"


def test_which_forecast_came_closer_is_measured_against_what_arrived() -> None:
    rows = _rows({SESSIONS[0]: [0.05, -0.05]})
    out = summarize(rows)
    assert out["mae_implied"] == pytest.approx(0.05)
    assert out["mae_trailing"] == pytest.approx(0.01)


def _series(values: list[float]) -> pd.Series:
    return pd.Series(values, index=SESSIONS[: len(values)], dtype=float)


def test_each_verdict_needs_its_own_side_of_the_bound(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fv, "newey_west_se", lambda v, max_lag: 0.01)
    assert read(_series([0.05] * 30))["state"] == "priced_above"
    assert read(_series([-0.05] * 30))["state"] == "priced_below"
    close = read(_series([0.01] * 30))
    assert close["state"] == "not_resolved"
    assert close["days_needed"] == pytest.approx(30 * (1.645 * 0.01 / 0.01) ** 2)


def test_a_bound_exactly_on_zero_does_not_resolve() -> None:
    flat = read(_series([0.0] * 30))
    assert flat["lower_bound"] == 0.0 and flat["upper_bound"] == 0.0
    assert flat["state"] == "not_resolved" and flat["days_needed"] is None


def test_the_error_allows_for_overlapping_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def spy(values: list[float], max_lag: int) -> float:
        seen["lag"] = max_lag
        return 0.01

    monkeypatch.setattr(fv, "newey_west_se", spy)
    read(_series([0.0] * 30))
    assert seen["lag"] == 20, "each 21-session window overlaps the next twenty"


def test_one_day_reads_nothing() -> None:
    assert read(_series([0.1]))["state"] == "too_few_days"
