"""Drift is measured per market, because a mixture describes neither.

The check pooled both markets' features into one distribution. On live data that roughly
halved the measured signal and hid its size — the worst pooled feature read far calmer than
the worst single-market one. The markets also drift on different features, so the single
number averaged two unrelated things. The same mistake as pooling cross-sectional ranks,
repeated in a place nobody revisited after fixing it there.

Nothing caught it because `run_drift_check` and `store_drift_report` had no tests at all —
only the pure PSI helpers did. These cover the part that was broken.
"""

import datetime as dt

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from quantpulse.data.universe import UniverseEntry, sync_universe
from quantpulse.features.engineering import FEATURE_COLUMNS, FEATURE_VERSION
from quantpulse.features.store import store_features
from quantpulse.monitoring.drift import CURRENT_DAYS, run_drift_check

pytestmark = pytest.mark.integration

CALM, SHIFTED = "XNYS", "XJSE"
DATES = [d.date() for d in pd.bdate_range("2025-01-01", periods=120)]
RECENT = DATES[-CURRENT_DAYS:]


def _frame(tickers: list[str], shift_recent: bool) -> pd.DataFrame:
    """Feature rows; `shift_recent` moves the last CURRENT_DAYS to a different distribution."""
    rng = np.random.default_rng(4)
    rows = []
    for date in DATES:
        for ticker in tickers:
            offset = 8.0 if (shift_recent and date in RECENT) else 0.0
            values = rng.normal(loc=offset, size=len(FEATURE_COLUMNS))
            row: dict[str, object] = {"ticker": ticker, "date": date}
            row.update(dict(zip(FEATURE_COLUMNS, values, strict=True)))
            rows.append(row)
    return pd.DataFrame(rows)


@pytest.fixture
def two_markets(db_engine: Engine) -> Engine:
    """One market whose features shift hard in the recent window, one that does not."""
    with Session(db_engine) as session:
        sync_universe(
            session,
            [UniverseEntry(f"CALM{i}", "stock", exchange=CALM) for i in range(6)]
            + [UniverseEntry(f"SHFT{i}", "stock", exchange=SHIFTED) for i in range(6)],
        )
        session.commit()
    with Session(db_engine) as session:
        store_features(session, _frame([f"CALM{i}" for i in range(6)], False), FEATURE_VERSION)
        store_features(session, _frame([f"SHFT{i}" for i in range(6)], True), FEATURE_VERSION)
        session.commit()
    return db_engine


def test_a_drifting_market_is_not_diluted_by_a_calm_one(two_markets: Engine) -> None:
    """The bug, stated as an assertion: the two markets must report different numbers.

    Pooling cannot produce this — one distribution yields one answer, somewhere between
    the two, which is exactly how a real shift got reported as half its size.
    """
    with Session(two_markets) as session:
        shifted = run_drift_check(two_markets, session, exchange=SHIFTED)
        calm = run_drift_check(two_markets, session, exchange=CALM)
        session.commit()

    assert shifted.share_drifted > calm.share_drifted
    assert shifted.drifted, "a market whose features moved 8 sigma must register as drifted"
    assert not calm.drifted, "an unchanged market must not be dragged over the line"


def test_each_reading_is_stored_against_its_own_market(two_markets: Engine) -> None:
    with Session(two_markets) as session:
        run_drift_check(two_markets, session, exchange=SHIFTED)
        run_drift_check(two_markets, session, exchange=CALM)
        session.commit()

    with two_markets.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT exchange, value FROM drift_metrics "
                "WHERE metric_name = 'share_drifted' ORDER BY exchange"
            )
        ).all()
    stored = {r.exchange: r.value for r in rows}
    assert set(stored) == {CALM, SHIFTED}, "each market needs its own row, not one shared"
    assert stored[SHIFTED] > stored[CALM]


def test_a_market_with_no_features_is_an_error_not_a_silent_zero(db_engine: Engine) -> None:
    """Reporting 'no drift' for a market that was never measured is the worst answer:
    it is indistinguishable from a clean bill of health."""
    with Session(db_engine) as session, pytest.raises(ValueError, match="No stored features"):
        run_drift_check(db_engine, session, exchange=SHIFTED)


def test_the_window_is_the_markets_own_dates(two_markets: Engine) -> None:
    """`asof` must come from the market being measured, not from whichever market
    happens to have ingested most recently."""
    with Session(two_markets) as session:
        report = run_drift_check(two_markets, session, exchange=CALM)
        session.commit()
    assert report.asof == max(DATES)
    assert isinstance(report.asof, dt.date)
