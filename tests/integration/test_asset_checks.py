"""The asset checks, which had no tests at all.

Their pure helpers (`run_quality_checks`, `run_option_quality_checks`, `check_headroom`)
are well covered. What was bare is the wiring around them: which rows get fetched, what
denominator coverage is scored against, whether one market's failure fails the run, and
what happens when a market is not configured yet.

That wiring is where a guard fails quietly. A gate that returns `passed=True` because its
query found nothing is indistinguishable from a gate that looked and approved.
"""

import datetime as dt

import pandas as pd
import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from quantpulse.data.ingest import BAR_COLUMNS, upsert_prices
from quantpulse.data.universe import UniverseEntry, sync_universe
from quantpulse.db import OptionQuote
from quantpulse.orchestration import assets

pytestmark = pytest.mark.integration

TICKERS = [f"T{i}" for i in range(5)]


@pytest.fixture(autouse=True)
def wired(db_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(assets, "get_engine", lambda: db_engine)
    monkeypatch.setattr(assets, "get_session", lambda: Session(db_engine))


def _seed_prices(engine: Engine, days: list[dt.date], tickers: list[str], close: float) -> None:
    with Session(engine) as session:
        sync_universe(session, [UniverseEntry(t, "stock") for t in tickers])
        session.commit()
    with Session(engine) as session:
        rows = [
            [t, d, close, close * 1.01, close * 0.99, close, 1000, "yfinance"]
            for d in days
            for t in tickers
        ]
        upsert_prices(session, pd.DataFrame(rows, columns=BAR_COLUMNS))
        session.commit()


def test_price_quality_reports_per_market_and_skips_unconfigured(db_engine: Engine) -> None:
    """Only markets with tickers are judged. A market with no universe must be skipped,
    not scored as a market whose every check failed."""
    from quantpulse.data.calendar import trading_days

    end = dt.date(2026, 8, 7)
    days = trading_days(end - dt.timedelta(days=20), end, "XNYS")
    _seed_prices(db_engine, days, TICKERS, 100.0)

    result = assets.recent_prices_quality()
    labels = set(result.metadata or {})
    assert any(k.startswith("XNYS/") for k in labels), "the configured market must be judged"
    assert not any(k.startswith("XJSE/") for k in labels), "an empty market must be skipped"


def test_option_quality_passes_when_no_market_has_options(db_engine: Engine) -> None:
    """Not a free pass: with no options-bearing market there is nothing to judge, and the
    check says so in its metadata rather than reporting a silent success."""
    with Session(db_engine) as session:
        sync_universe(session, [UniverseEntry("NPN.JO", "stock", exchange="XJSE")])
        session.commit()

    result = assets.option_snapshot_quality()
    assert result.passed
    assert "no options-bearing market" in str((result.metadata or {}).get("note", ""))


def test_option_quality_fails_on_a_premarket_snapshot(db_engine: Engine) -> None:
    """The guard that matters: pre-market IV reads ~2% against ~33% post-close. A snapshot
    taken off-hours is junk that would otherwise be indistinguishable from real data once
    it is in the table."""
    with Session(db_engine) as session:
        sync_universe(session, [UniverseEntry(t, "stock") for t in TICKERS])
        session.commit()
    day = dt.date(2026, 8, 7)
    with Session(db_engine) as session:
        for t in TICKERS:
            session.add(
                OptionQuote(
                    snapshot_date=day,
                    ticker=t,
                    expiry=day + dt.timedelta(days=30),
                    strike=100.0,
                    option_type="call",
                    underlying_close=100.0,
                    implied_volatility=0.021,  # stale pre-market mark
                    in_the_money=False,
                    theo_value=1.0,
                    delta=0.5,
                    gamma=0.1,
                    theta=-0.1,
                    vega=0.2,
                    volume=5,
                    open_interest=50,
                )
            )
        session.commit()

    result = assets.option_snapshot_quality()
    assert not result.passed
    # Anchored to the cause: coverage is full here, so a bare "not passed" could have
    # been satisfied by the wrong check failing and the IV gate never being exercised.
    iv = (result.metadata or {}).get("implied_vol_plausible")
    assert iv is not None and iv.value["passed"] is False
    assert (result.metadata or {})["ticker_coverage"].value["passed"] is True


def test_option_quality_accepts_a_healthy_snapshot(db_engine: Engine) -> None:
    with Session(db_engine) as session:
        sync_universe(session, [UniverseEntry(t, "stock") for t in TICKERS])
        session.commit()
    day = dt.date(2026, 8, 7)
    with Session(db_engine) as session:
        for t in TICKERS:
            for strike in (90.0, 100.0, 110.0):
                session.add(
                    OptionQuote(
                        snapshot_date=day,
                        ticker=t,
                        expiry=day + dt.timedelta(days=30),
                        strike=strike,
                        option_type="call",
                        underlying_close=100.0,
                        implied_volatility=0.33,
                        in_the_money=strike < 100,
                        theo_value=2.0,
                        delta=0.5,
                        gamma=0.1,
                        theta=-0.1,
                        vega=0.2,
                        volume=10,
                        open_interest=100,
                    )
                )
        session.commit()

    assert assets.option_snapshot_quality().passed


def test_resource_headroom_passes_on_a_small_database(db_engine: Engine) -> None:
    """A near-empty database has years of runway; anything else means the check is
    measuring the wrong thing."""
    result = assets.resource_headroom()
    assert result.passed
    assert result.metadata


def test_drift_report_refuses_when_no_market_is_configured(db_engine: Engine) -> None:
    """Silence here would be the worst outcome: an empty universe reporting no drift
    reads exactly like a healthy pipeline."""
    with pytest.raises(ValueError, match="No configured market"):
        assets.drift_report()


def test_drift_report_measures_each_configured_market(db_engine: Engine) -> None:
    """The happy path of the per-market loop: one entry per market, not one pooled number.

    The metadata keys are the visible half of the fix — a single `share_drifted` in the
    Dagster UI is exactly what the pooled version showed, and looked perfectly fine.
    """
    import numpy as np

    from quantpulse.features.engineering import FEATURE_COLUMNS, FEATURE_VERSION
    from quantpulse.features.store import store_features

    dates = [d.date() for d in pd.bdate_range("2025-06-02", periods=80)]
    rng = np.random.default_rng(9)
    with Session(db_engine) as session:
        sync_universe(
            session,
            [UniverseEntry(f"US{i}", "stock") for i in range(4)]
            + [UniverseEntry(f"ZA{i}.JO", "stock", exchange="XJSE") for i in range(4)],
        )
        session.commit()
    rows = [
        {
            "ticker": t,
            "date": d,
            **dict(zip(FEATURE_COLUMNS, rng.normal(size=len(FEATURE_COLUMNS)), strict=True)),
        }
        for d in dates
        for t in [f"US{i}" for i in range(4)] + [f"ZA{i}.JO" for i in range(4)]
    ]
    with Session(db_engine) as session:
        store_features(session, pd.DataFrame(rows), FEATURE_VERSION)
        session.commit()

    result = assets.drift_report()
    keys = set(result.metadata or {})
    assert "XNYS/share_drifted" in keys
    assert "XJSE/share_drifted" in keys
