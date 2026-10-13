"""`fetch_daily_bars`: the vendor-failure path, exercised without a network.

This is the only place the platform decides what to do when the data source fails, and it has
to fail in three different ways cleanly: yfinance down entirely, yfinance returning a partial
batch, and yfinance returning nothing. Everything downstream — features, the model, the books —
is built from whatever this returns, so a wrong answer here is not a crash but a quietly
incomplete history.

yfinance is stubbed. A test that reaches the real vendor would be measuring Yahoo's uptime
rather than this function, and would fail on a plane.
"""

import datetime as dt
import logging

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


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nothing here may reach for a second source. A fallback that times out per ticker turns a
    vendor's partial day into an ingest that runs for minutes, and fills nothing."""

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("fetch_daily_bars made a network call outside yfinance")

    monkeypatch.setattr(httpx, "get", refuse)


def test_a_partial_batch_keeps_what_arrived_and_names_what_did_not(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A partial batch is the common case, not an outage — one ticker absent from a fifty-name
    download. The session keeps the rest, and the absent ticker is named, so the gap can be
    found and re-fetched once the vendor has the bar."""
    _stub_yfinance(monkeypatch, returns=["AAA"])

    with caplog.at_level(logging.WARNING, logger="quantpulse.data.ingest"):
        bars = fetch_daily_bars(["AAA", "BBB", "CCC"], START, END)

    assert set(bars["ticker"].unique()) == {"AAA"}
    assert set(bars["source"]) == {"yfinance"}
    assert "2 of 3 tickers" in caplog.text and "BBB, CCC" in caplog.text


def test_a_total_yfinance_failure_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """The batch raising must fail the run, so the run-failure alert fires and the catch-up
    sensor retries it — not return an empty session that looks like a quiet day."""
    _stub_yfinance(monkeypatch, returns=None, fail=True)

    with pytest.raises(IngestionError, match="yfinance batch failed"):
        fetch_daily_bars(["AAA", "BBB"], START, END)


def test_no_data_at_all_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """The one case that must be loud. Returning an empty frame would let the caller upsert
    nothing and report success, and the missing day would only surface later as a hole in the
    book."""
    _stub_yfinance(monkeypatch, returns=[])

    with pytest.raises(IngestionError, match="No usable bars"):
        fetch_daily_bars(["AAA", "BBB"], START, END)


def test_the_result_is_cleaned(monkeypatch: pytest.MonkeyPatch) -> None:
    """`clean_bars` runs last, so a vendor row with a non-positive close cannot reach the
    database — it would produce an infinite return on the following day."""
    bad = _bars(["AAA"])
    bad.loc[bad.index[0], "close"] = 0.0
    monkeypatch.setattr(ingest, "_download_yfinance", lambda t, s, e: None)
    monkeypatch.setattr(ingest, "normalize_yfinance", lambda raw, tickers: bad)

    bars = fetch_daily_bars(["AAA"], START, END)
    assert (bars["close"] > 0).all()
