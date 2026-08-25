import datetime as dt
from contextlib import AbstractContextManager

import pandas as pd
import pytest
from sqlalchemy.orm import Session

from quantpulse.options import ingest
from quantpulse.options.ingest import (
    EmptyUniverseSnapshotError,
    OffHoursSnapshotError,
    _rows_for_ticker,
    dedupe_rows,
    snapshot_option_chains,
)


def chain_frame(strikes: list[float], itm_below: float) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "strike": strikes,
            "bid": [1.0] * len(strikes),
            "ask": [1.2] * len(strikes),
            "lastPrice": [1.1] * len(strikes),
            "volume": [10] * len(strikes),
            "openInterest": [100] * len(strikes),
            "impliedVolatility": [0.3] * len(strikes),
            "inTheMoney": [s < itm_below for s in strikes],
        }
    )


def test_rows_respect_moneyness_bound_and_compute_greeks() -> None:
    spot = 100.0
    strikes = [70, 85, 100, 115, 130, 150]  # ±20% keeps 85..115
    calls = chain_frame(strikes, itm_below=spot)
    puts = chain_frame(strikes, itm_below=spot)
    chains = [(dt.date(2026, 8, 21), calls, puts)]

    rows = _rows_for_ticker("AAPL", spot, chains, dt.date(2026, 7, 20), moneyness=0.2, rate=0.04)

    kept = {r["strike"] for r in rows}
    assert kept == {85.0, 100.0, 115.0}  # 70, 130, 150 filtered out
    assert len(rows) == 6  # 3 strikes x call+put

    call_atm = next(r for r in rows if r["option_type"] == "call" and r["strike"] == 100.0)
    put_atm = next(r for r in rows if r["option_type"] == "put" and r["strike"] == 100.0)
    assert 0 < call_atm["delta"] < 1
    assert -1 < put_atm["delta"] < 0
    assert call_atm["gamma"] > 0
    assert call_atm["theo_value"] > 0
    assert call_atm["open_interest"] == 100


def test_dedupe_keeps_the_more_liquid_contract() -> None:
    """Yahoo can list a standard and an adjusted contract at the same strike."""
    base = {
        "snapshot_date": dt.date(2026, 7, 20),
        "ticker": "AAPL",
        "expiry": dt.date(2026, 8, 21),
        "strike": 100.0,
        "option_type": "call",
    }
    rows = [
        {**base, "open_interest": 5, "last_price": 9.9},  # adjusted, illiquid
        {**base, "open_interest": 5000, "last_price": 4.2},  # standard
        {**base, "strike": 105.0, "open_interest": 1, "last_price": 2.0},  # distinct key
    ]
    deduped = dedupe_rows(rows)
    assert len(deduped) == 2
    kept = next(r for r in deduped if r["strike"] == 100.0)
    assert kept["open_interest"] == 5000
    assert kept["last_price"] == 4.2


def test_empty_when_no_strikes_in_band() -> None:
    calls = chain_frame([50, 200], itm_below=100)
    chains = [(dt.date(2026, 8, 21), calls, calls)]
    rows = _rows_for_ticker("X", 100.0, chains, dt.date(2026, 7, 20), moneyness=0.2, rate=0.04)
    assert rows == []


# --- The post-close gate ------------------------------------------------------------
#
# It lives in snapshot_option_chains() so that every caller inherits it. Enforced only in a
# caller, it would leave the CLI and a manual materialize free to capture pre-market chains
# and overwrite good post-close rows through the (snapshot_date, ticker, ...) upsert key.


class _EscapedTheGate(BaseException):
    """Deliberately NOT an Exception.

    snapshot_option_chains catches `Exception` per ticker and merely logs it, so a guard
    raising a normal error (AssertionError included) would be swallowed — the test would
    pass on its main assertion while quietly proving nothing. Inheriting BaseException
    means a run that gets past the gate propagates out and fails the test loudly.
    """


def _exploding_session() -> AbstractContextManager[Session]:
    """A session factory that fails the test if the gate ever lets it be called."""
    raise _EscapedTheGate("opened a session despite the off-hours gate")


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Any vendor call past the gate fails the test, rather than quietly going to yfinance."""

    def boom(ticker: str, n_expiries: int) -> object:
        raise _EscapedTheGate(f"fetched {ticker} despite the off-hours gate")

    monkeypatch.setattr(ingest, "_fetch_ticker_chain", boom)


def test_the_gate_is_the_real_post_close_predicate() -> None:
    """Pin what the tests below monkeypatch to the shared, exchange-aware implementation.

    Without this, the gate could be rewired to some local always-true stub and every
    other test here would still pass.
    """
    from quantpulse.data import calendar

    assert ingest.is_post_close is calendar.is_post_close


def test_snapshot_refuses_before_the_close(
    monkeypatch: pytest.MonkeyPatch, no_network: None
) -> None:
    """The case that actually occurred: `quantpulse options-snapshot` run by hand at 08:00."""
    monkeypatch.setattr(ingest, "is_post_close", lambda: False)

    with pytest.raises(OffHoursSnapshotError, match="before the close"):
        snapshot_option_chains(_exploding_session, ["AAPL"])


def test_refusal_ignores_an_explicit_snapshot_date(
    monkeypatch: pytest.MonkeyPatch, no_network: None
) -> None:
    """Marks come from the vendor NOW, so the wall clock decides — not the stamped date.

    Passing yesterday's date does not make this morning's IV trustworthy.
    """
    monkeypatch.setattr(ingest, "is_post_close", lambda: False)

    with pytest.raises(OffHoursSnapshotError):
        snapshot_option_chains(_exploding_session, ["AAPL"], dt.date(2026, 7, 22))


def test_refusal_happens_before_any_ticker_is_fetched(
    monkeypatch: pytest.MonkeyPatch, no_network: None
) -> None:
    """A partial off-hours run is the damaging case — it must not reach the feed at all."""
    monkeypatch.setattr(ingest, "is_post_close", lambda: False)

    with pytest.raises(OffHoursSnapshotError):
        snapshot_option_chains(_exploding_session, ["AAPL", "MSFT", "NVDA"])


def test_post_close_is_allowed_through(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ingest, "is_post_close", lambda: True)

    assert snapshot_option_chains(_exploding_session, []) == 0  # no tickers, no session


def test_force_bypasses_the_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    """The deliberate escape hatch: off-hours testing against a throwaway snapshot_date."""
    monkeypatch.setattr(ingest, "is_post_close", lambda: False)

    assert snapshot_option_chains(_exploding_session, [], force=True) == 0


# ------------------------------------------------------------------- empty universe


def test_whole_universe_returning_nothing_is_an_outage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The loss this exists for: every ticker empty, exit code 0.

    Whatever the cause — the recorded one was a local internet outage — each ticker takes
    the `continue` path, the run writes nothing and returns cleanly. Repair runs then report
    SUCCESS having captured zero rows. Option marks cannot be captured after the session, so
    a quiet 0 costs the day.
    """
    monkeypatch.setattr(ingest, "is_post_close", lambda: True)
    monkeypatch.setattr(ingest, "_fetch_ticker_chain", lambda t, n: (None, []))

    with pytest.raises(EmptyUniverseSnapshotError, match="cannot be captured later"):
        snapshot_option_chains(_exploding_session, ["AAPL", "MSFT", "NVDA"])


def test_outage_is_raised_when_every_fetch_throws(monkeypatch: pytest.MonkeyPatch) -> None:
    """The other shape: the fetch raises rather than returning empty."""
    monkeypatch.setattr(ingest, "is_post_close", lambda: True)

    def boom(ticker: str, n_expiries: int) -> object:
        raise RuntimeError("429 Too Many Requests")

    monkeypatch.setattr(ingest, "_fetch_ticker_chain", boom)

    with pytest.raises(EmptyUniverseSnapshotError):
        snapshot_option_chains(_exploding_session, ["AAPL", "MSFT"])


def test_one_ticker_without_a_chain_is_not_an_outage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A symbol with no listed options is ordinary and must not fail the run.

    This is the line: some tickers empty is normal, all of them is not.
    """
    monkeypatch.setattr(ingest, "is_post_close", lambda: True)
    monkeypatch.setattr(
        ingest,
        "_fetch_ticker_chain",
        lambda t, n: (
            (None, [])
            if t == "NOOPT"
            else (
                100.0,
                [(dt.date(2026, 9, 18), chain_frame([100.0], 100.0), chain_frame([100.0], 100.0))],
            )
        ),
    )
    monkeypatch.setattr(ingest, "upsert_quotes", lambda session, rows: len(rows))

    class _Sess:
        def __enter__(self) -> object:
            return self

        def __exit__(self, *a: object) -> None:
            return None

    assert snapshot_option_chains(lambda: _Sess(), ["NOOPT", "AAPL"]) > 0


def test_empty_universe_is_still_a_no_op(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nothing asked for is not an outage — the guard must not fire on an empty list."""
    monkeypatch.setattr(ingest, "is_post_close", lambda: True)

    assert snapshot_option_chains(_exploding_session, []) == 0
