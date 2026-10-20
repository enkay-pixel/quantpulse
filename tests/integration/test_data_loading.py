"""`load_price_bars` and `build_dataset`: the two reads everything downstream trusts.

Neither had a test. They are the point where "which market's data is this" is decided, and
getting that wrong does not raise — it produces a training frame that silently mixes two
markets, which is how the cross-sectional ranks came to compare Naspers with Apple
and how drift came to describe neither market.
"""

import datetime as dt

import pandas as pd
import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from quantpulse.data.ingest import BAR_COLUMNS, upsert_prices
from quantpulse.data.universe import UniverseEntry, sync_universe
from quantpulse.features.store import load_price_bars
from quantpulse.ml.pipeline import build_dataset
from quantpulse.ml.training import TrainConfig

pytestmark = pytest.mark.integration

DATES = [d.date() for d in pd.bdate_range("2024-01-01", periods=90)]
US = ["AAA", "BBB"]
ZA = ["XXX.JO", "YYY.JO"]


@pytest.fixture
def seeded(db_engine: Engine) -> Engine:
    with Session(db_engine) as session:
        sync_universe(
            session,
            [UniverseEntry(t, "stock") for t in US]
            + [UniverseEntry(t, "stock", exchange="XJSE") for t in ZA],
        )
        session.commit()
    with Session(db_engine) as session:
        rows = []
        for i, day in enumerate(DATES):
            for t in US + ZA:
                # A gently trending series, so forward returns are well defined.
                close = 100.0 + i * 0.5 + (7.0 if t in ZA else 0.0)
                rows.append([t, day, close, close * 1.01, close * 0.99, close, 1000, "yfinance"])
        upsert_prices(session, pd.DataFrame(rows, columns=BAR_COLUMNS))
        session.commit()
    return db_engine


def test_bars_carry_their_market(seeded: Engine) -> None:
    """The `exchange` column is not decoration: `compute_features` groups by it to rank
    within a market. A loader that dropped it would rank across markets and nothing would
    complain."""
    bars = load_price_bars(seeded)
    assert "exchange" in bars.columns
    assert set(bars["exchange"].unique()) == {"XNYS", "XJSE"}


def test_filtering_by_market_excludes_the_other(seeded: Engine) -> None:
    bars = load_price_bars(seeded, exchange="XJSE")
    assert set(bars["ticker"].unique()) == set(ZA)


def test_inactive_members_are_not_loaded(seeded: Engine) -> None:
    """Deactivating a ticker must stop it feeding the model, without deleting its history
    — the universe is the switch, and `prices` keeps the record."""
    from quantpulse.db import UniverseMember

    with Session(seeded) as session:
        session.query(UniverseMember).filter(UniverseMember.ticker == "AAA").update(
            {"active": False}
        )
        session.commit()
    assert "AAA" not in set(load_price_bars(seeded, exchange="XNYS")["ticker"].unique())


def test_date_bounds_are_inclusive(seeded: Engine) -> None:
    bars = load_price_bars(seeded, start=DATES[10], end=DATES[20])
    assert bars["date"].min() == DATES[10]
    assert bars["date"].max() == DATES[20]


def test_build_dataset_returns_only_the_requested_market(seeded: Engine) -> None:
    """The training frame is where a market mix-up becomes a model. Every ticker in it
    must belong to the market being trained."""
    frame = build_dataset(seeded, TrainConfig(horizon_days=5), exchange="XJSE")
    assert set(frame["ticker"].unique()) <= set(ZA)
    assert not frame.empty


def test_build_dataset_raises_for_a_market_with_no_bars(db_engine: Engine) -> None:
    """Loud, not empty: a silent empty frame would train on nothing and promote whatever
    came out."""
    with pytest.raises(ValueError, match="No price bars"):
        build_dataset(db_engine, TrainConfig(), exchange="XNYS")


def test_build_dataset_raises_when_history_is_shorter_than_the_horizon(
    db_engine: Engine,
) -> None:
    """Forward returns need `horizon` days ahead; without them every label is NaN and the
    frame empties out. That must be an error, not a zero-row training run."""
    with Session(db_engine) as session:
        sync_universe(session, [UniverseEntry("AAA", "stock")])
        session.commit()
    with Session(db_engine) as session:
        rows = [
            ["AAA", d, 100.0, 101.0, 99.0, 100.0, 1000, "yfinance"]
            for d in [dt.date(2024, 1, 2), dt.date(2024, 1, 3)]
        ]
        upsert_prices(session, pd.DataFrame(rows, columns=BAR_COLUMNS))
        session.commit()

    with pytest.raises(ValueError, match="Training frame is empty"):
        build_dataset(db_engine, TrainConfig(horizon_days=21), exchange="XNYS")


CUTOFF = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)


def _stored_after_cutoff(engine: Engine, first_late: dt.date) -> None:
    """Mark every row as stored before CUTOFF, except those from `first_late` on."""
    from sqlalchemy import text

    with engine.begin() as conn:
        conn.execute(
            text("UPDATE prices SET ingested_at = :t"), {"t": CUTOFF - dt.timedelta(days=1)}
        )
        conn.execute(
            text("UPDATE prices SET ingested_at = :t WHERE date >= :d"),
            {"t": CUTOFF + dt.timedelta(days=1), "d": first_late},
        )


def test_known_by_keeps_only_the_rows_stored_by_then(seeded: Engine) -> None:
    """A model fitted on a past day is refitted on the bars stored by then, not today's."""
    _stored_after_cutoff(seeded, DATES[-5])
    assert load_price_bars(seeded, exchange="XNYS", known_by=CUTOFF)["date"].max() == DATES[-6]
    assert load_price_bars(seeded, exchange="XNYS")["date"].max() == DATES[-1]


def test_a_missing_session_lets_later_bars_add_rows_before_the_cut(seeded: Engine) -> None:
    """Why the shadow scorer refits on `known_by` rather than on today's frame cut at the holdout
    end. Labels count rows, so a ticker missing a session labels its late rows from a bar one
    session further on. Here AAA misses one session, and its row 21 sessions before the last bar
    a past fit could see had no label then; today it has one, so a cut at that date keeps a row
    the fit never trained on. BBB, with no gap, is the same either way."""
    from sqlalchemy import text

    from quantpulse.ml.fixed_defaults import truncate_panel

    last_seen, row, gap = 87, 66, 75  # indexes into DATES; 87 - 21 = 66, and 75 lies between
    with seeded.begin() as conn:
        conn.execute(
            text("DELETE FROM prices WHERE ticker = 'AAA' AND date = :d"), {"d": DATES[gap]}
        )
    _stored_after_cutoff(seeded, DATES[last_seen + 1])
    cfg = TrainConfig(horizon_days=21)
    cut = str(DATES[row])
    then = truncate_panel(build_dataset(seeded, cfg, "XNYS", known_by=CUTOFF), cut)
    today = truncate_panel(build_dataset(seeded, cfg, "XNYS"), cut)

    def has(frame: pd.DataFrame, ticker: str) -> bool:
        return bool(((frame["ticker"] == ticker) & (frame["date"] == DATES[row])).any())

    assert has(today, "AAA") and not has(then, "AAA")
    assert has(today, "BBB") and has(then, "BBB")
