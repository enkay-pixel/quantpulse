"""`fetch_daily_bars`: the vendor-failure path, exercised without a network.

This is the only place the platform decides what to do when a data source fails, and it
has to fail in three different ways cleanly: yfinance down entirely, yfinance returning a
partial batch, and both sources missing a name. Everything downstream — features, the
model, the books — is built from whatever this returns, so a wrong answer here is not a
crash but a quietly incomplete history.

Both sources are stubbed. A test that reaches the real vendors would be measuring Yahoo's
uptime rather than this function, and would fail on a plane.
"""

import datetime as dt

import httpx
import pandas as pd
import pytest

from quantpulse.data import ingest
from quantpulse.data.ingest import BAR_COLUMNS, IngestionError, fetch_daily_bars

START, END = dt.date(2026, 1, 2), dt.date(2026, 1, 9)
DAYS = [d.date() for d in pd.bdate_range(START, END)]


def _bars(tickers: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        [[t, d, 100.0, 101.0, 99.0, 100.5, 1000, "yfinance"] for t in tickers for d in DAYS],
        columns=BAR_COLUMNS,
    )


def _stub_yfinance(monkeypatch: pytest.MonkeyPatch, returns: list[str] | None, fail: bool = False):
    def fake_download(tickers, start, end):  # type: ignore[no-untyped-def]
        if fail:
            raise RuntimeError("yfinance is down")
        return {"raw": returns}

    monkeypatch.setattr(ingest, "_download_yfinance", fake_download)
    monkeypatch.setattr(ingest, "normalize_yfinance", lambda raw, tickers: _bars(raw["raw"] or []))


def test_stooq_fills_in_what_yfinance_missed(monkeypatch: pytest.MonkeyPatch) -> None:
    """A partial batch is the common case, not an outage — one ticker silently absent
    from a fifty-name download."""
    _stub_yfinance(monkeypatch, returns=["AAA"])
    monkeypatch.setattr(ingest, "fetch_stooq", lambda t, s, e: _bars([t]).assign(source="stooq"))

    bars = fetch_daily_bars(["AAA", "BBB"], START, END)
    assert set(bars["ticker"].unique()) == {"AAA", "BBB"}
    assert set(bars.loc[bars["ticker"] == "BBB", "source"]) == {"stooq"}


def test_a_total_yfinance_failure_falls_through_to_stooq(monkeypatch: pytest.MonkeyPatch) -> None:
    """The batch raising must not lose the whole session — every name goes to the
    fallback rather than the run aborting."""
    _stub_yfinance(monkeypatch, returns=None, fail=True)
    monkeypatch.setattr(ingest, "fetch_stooq", lambda t, s, e: _bars([t]).assign(source="stooq"))

    bars = fetch_daily_bars(["AAA", "BBB"], START, END)
    assert set(bars["ticker"].unique()) == {"AAA", "BBB"}


def test_a_stooq_error_drops_only_that_ticker(monkeypatch: pytest.MonkeyPatch) -> None:
    """One unreachable name must not cost the other forty-nine their session."""
    _stub_yfinance(monkeypatch, returns=["AAA"])

    def flaky(ticker, start, end):  # type: ignore[no-untyped-def]
        raise httpx.ConnectError("stooq unreachable")

    monkeypatch.setattr(ingest, "fetch_stooq", flaky)

    bars = fetch_daily_bars(["AAA", "BBB"], START, END)
    assert set(bars["ticker"].unique()) == {"AAA"}


def test_no_data_from_any_source_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """The one case that must be loud. Returning an empty frame would let the caller
    upsert nothing and report success, and the missing day would only surface later as a
    hole in the book."""
    _stub_yfinance(monkeypatch, returns=[])
    monkeypatch.setattr(ingest, "fetch_stooq", lambda t, s, e: pd.DataFrame(columns=BAR_COLUMNS))

    with pytest.raises(IngestionError, match="No usable bars"):
        fetch_daily_bars(["AAA", "BBB"], START, END)


def test_the_result_is_cleaned(monkeypatch: pytest.MonkeyPatch) -> None:
    """`clean_bars` runs last, so a vendor row with a non-positive close cannot reach the
    database — it would produce an infinite return on the following day."""
    bad = _bars(["AAA"])
    bad.loc[bad.index[0], "close"] = 0.0
    monkeypatch.setattr(ingest, "_download_yfinance", lambda t, s, e: None)
    monkeypatch.setattr(ingest, "normalize_yfinance", lambda raw, tickers: bad)
    monkeypatch.setattr(ingest, "fetch_stooq", lambda t, s, e: pd.DataFrame(columns=BAR_COLUMNS))

    bars = fetch_daily_bars(["AAA"], START, END)
    assert (bars["close"] > 0).all()
