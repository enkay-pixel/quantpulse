"""`raw_prices` in fill-only mode: what the catch-up sensor's retry of a partial session does.

The sensor tags the run; the asset has to honour the tag. Three things are pinned: only the
missing tickers are fetched, the write never overwrites a stored bar, and a vendor that still
has nothing is the expected answer rather than a failure — a failure here would raise a
pipeline alert on every retry of a bar that is merely late.

Everything outside the asset is stubbed, so this needs neither the database nor the vendor.
"""

import contextlib
import datetime as dt
from collections.abc import Iterator
from typing import Any

import pandas as pd
import pytest

import dagster as dg
from quantpulse.data import ingest
from quantpulse.data.ingest import BAR_COLUMNS, NoBarsReturned
from quantpulse.orchestration import assets, catchup

DAY = dt.date(2026, 10, 12)
KEY = dg.MultiPartitionKey({"date": str(DAY), "exchange": "XJSE"})


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    seen: dict[str, Any] = {}

    @contextlib.contextmanager
    def fake_session() -> Iterator[object]:
        yield object()

    def fake_fetch(tickers: list[str], start: dt.date, end: dt.date) -> pd.DataFrame:
        seen["fetched"] = list(tickers)
        return pd.DataFrame(
            [[t, DAY, 100.0, 101.0, 99.0, 100.5, 1000, "yfinance"] for t in tickers],
            columns=BAR_COLUMNS,
        )

    def fake_upsert(session: object, bars: pd.DataFrame, overwrite: bool = True) -> int:
        seen["overwrite"] = overwrite
        return len(bars)

    monkeypatch.setattr(assets, "is_trading_day", lambda day, exchange=None: True)
    monkeypatch.setattr(assets, "get_session", fake_session)
    monkeypatch.setattr(catchup, "missing_tickers", lambda day, exchange=None: ["AGL.JO", "NPN.JO"])
    monkeypatch.setattr(ingest, "fetch_daily_bars", fake_fetch)
    monkeypatch.setattr(ingest, "upsert_prices", fake_upsert)
    return seen


# The production asset's own body, rebuilt without its retry policy: that policy waits a
# minute between attempts, and a failure under test should report on the first one.
RAW_PRICES = dg.asset(name="raw_prices", partitions_def=assets.market_partitions)(
    assets.raw_prices.op.compute_fn.decorated_fn  # type: ignore[union-attr]
)


def test_the_rebuilt_asset_differs_from_production_only_by_its_retries() -> None:
    assert assets.raw_prices.op.retry_policy is not None
    assert RAW_PRICES.partitions_def == assets.raw_prices.partitions_def


def _materialize(tags: dict[str, str] | None = None) -> dg.ExecuteInProcessResult:
    return dg.materialize(
        [RAW_PRICES], partition_key=str(KEY), tags=tags or {}, raise_on_error=False
    )


def test_a_fill_fetches_only_what_is_missing_and_overwrites_nothing(
    calls: dict[str, Any],
) -> None:
    result = _materialize({catchup.FILL_ONLY_TAG: "true"})
    assert result.success
    assert calls["fetched"] == ["AGL.JO", "NPN.JO"], "a fill re-fetched tickers it already had"
    assert calls["overwrite"] is False, "a fill was allowed to rewrite stored bars"


def test_a_late_bar_is_not_a_failure(
    calls: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    def nothing_yet(tickers: list[str], start: dt.date, end: dt.date) -> pd.DataFrame:
        raise NoBarsReturned("none")

    monkeypatch.setattr(ingest, "fetch_daily_bars", nothing_yet)
    result = _materialize({catchup.FILL_ONLY_TAG: "true"})
    assert result.success, "a bar the vendor has not published yet raised a pipeline failure"
    assert "overwrite" not in calls, "nothing was fetched, so nothing should be written"


def test_a_vendor_that_is_down_still_fails_a_fill(
    calls: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only the vendor having nothing is expected. A failed request is an outage, and has to
    reach the run-failure alert like any other."""

    def down(tickers: list[str], start: dt.date, end: dt.date) -> pd.DataFrame:
        raise ingest.IngestionError("yfinance batch failed after retries")

    monkeypatch.setattr(ingest, "fetch_daily_bars", down)
    assert not _materialize({catchup.FILL_ONLY_TAG: "true"}).success


def test_an_untagged_run_is_the_scheduled_ingest_unchanged(
    calls: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    from quantpulse.data import universe

    monkeypatch.setattr(universe, "active_tickers", lambda session, exchange=None: ["A", "B", "C"])
    assert _materialize().success
    assert calls["fetched"] == ["A", "B", "C"]
    assert calls["overwrite"] is True
