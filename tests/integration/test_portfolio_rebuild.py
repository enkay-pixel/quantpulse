"""`score_history` and `rebuild_portfolio`: how the replay evidence base gets built.

Between them they write every prediction and every book snapshot the dashboard shows for
the pre-live period — 2,000+ days per market. Neither had a test. The failure modes are
quiet ones: scoring a market with another market's champion, or collapsing the three books
into one so the daily-vs-horizon comparison silently compares a book with itself.
"""

import datetime as dt
from types import SimpleNamespace

import lightgbm as lgb
import numpy as np
import pandas as pd
import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from quantpulse.data.ingest import BAR_COLUMNS, upsert_prices
from quantpulse.data.universe import UniverseEntry, sync_universe
from quantpulse.features.engineering import FEATURE_COLUMNS, FEATURE_VERSION
from quantpulse.features.store import store_features
from quantpulse.ml import registry
from quantpulse.ml.portfolio import books_for, rebuild_portfolio, score_history
from quantpulse.ml.training import DEFAULT_PARAMS

pytestmark = pytest.mark.integration

DATES = [d.date() for d in pd.bdate_range("2024-01-01", periods=70)]
US = [f"US{i}" for i in range(6)]
ZA = [f"ZA{i}.JO" for i in range(6)]


def _features(tickers: list[str]) -> pd.DataFrame:
    rng = np.random.default_rng(12)
    return pd.DataFrame(
        [
            {
                "ticker": t,
                "date": d,
                **dict(zip(FEATURE_COLUMNS, rng.normal(size=len(FEATURE_COLUMNS)), strict=True)),
            }
            for d in DATES
            for t in tickers
        ]
    )


@pytest.fixture
def seeded(db_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> Engine:
    with Session(db_engine) as session:
        sync_universe(
            session,
            [UniverseEntry(t, "stock") for t in US]
            + [UniverseEntry(t, "stock", exchange="XJSE") for t in ZA],
        )
        session.commit()
    rng = np.random.default_rng(5)
    with Session(db_engine) as session:
        rows = []
        for i, day in enumerate(DATES):
            for t in US + ZA:
                close = 100.0 * (1 + 0.002 * i) + rng.normal(0, 0.5)
                rows.append([t, day, close, close * 1.01, close * 0.99, close, 1000, "yfinance"])
        upsert_prices(session, pd.DataFrame(rows, columns=BAR_COLUMNS))
        store_features(session, _features(US + ZA), FEATURE_VERSION)
        session.commit()

    frame = _features(US)
    booster = lgb.train(
        {**DEFAULT_PARAMS, "seed": 1},
        lgb.Dataset(frame[list(FEATURE_COLUMNS)], label=rng.normal(size=len(frame))),
        num_boost_round=5,
    )
    monkeypatch.setattr(
        registry, "load_champion", lambda exchange=None: (booster, SimpleNamespace(version="9"))
    )
    return db_engine


def _predicted_tickers(engine: Engine) -> set[str]:
    with engine.connect() as conn:
        return {r.ticker for r in conn.execute(text("SELECT DISTINCT ticker FROM predictions"))}


def test_score_history_touches_only_its_own_market(seeded: Engine) -> None:
    """One champion per market. Replaying the JSE with NYSE's model would write thousands
    of predictions from a model that never saw a JSE name, and the dashboard would show
    them as that market's signal trail."""
    with Session(seeded) as session:
        written = score_history(seeded, session, exchange="XJSE")
        session.commit()

    assert written > 0
    assert _predicted_tickers(seeded) <= set(ZA)


def test_score_history_is_idempotent(seeded: Engine) -> None:
    """It is the bootstrap path and gets re-run; a second pass must update, not duplicate."""
    with Session(seeded) as session:
        first = score_history(seeded, session, exchange="XNYS")
        session.commit()
    with Session(seeded) as session:
        score_history(seeded, session, exchange="XNYS")
        session.commit()

    with seeded.connect() as conn:
        total = conn.execute(text("SELECT count(*) FROM predictions")).scalar_one()
    assert total == first


def test_score_history_without_a_champion_writes_nothing(
    seeded: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(registry, "load_champion", lambda exchange=None: None)
    with Session(seeded) as session:
        assert score_history(seeded, session, exchange="XNYS") == 0
        session.commit()
    assert _predicted_tickers(seeded) == set()


def test_rebuild_writes_every_book_separately(seeded: Engine) -> None:
    """The three books are the project's one controlled experiment; they must land as
    three distinct variants or the comparison compares a book with itself."""
    with Session(seeded) as session:
        score_history(seeded, session, exchange="XNYS")
        session.commit()
    with Session(seeded) as session:
        written = rebuild_portfolio(seeded, session, exchange="XNYS")
        session.commit()

    assert written > 0
    with seeded.connect() as conn:
        rows = conn.execute(
            text("SELECT variant, count(*) AS n FROM portfolio_snapshots GROUP BY variant")
        ).all()
    got = {r.variant: r.n for r in rows}
    assert set(got) == {b.variant for b in books_for("XNYS")}
    assert len({*got.values()}) == 1, "each book should cover the same trading days"


def test_rebuild_is_idempotent(seeded: Engine) -> None:
    """Runs nightly over the whole trail; a second pass must upsert onto the same
    (date, exchange, variant) rows rather than accumulate."""
    with Session(seeded) as session:
        score_history(seeded, session, exchange="XNYS")
        session.commit()
    with Session(seeded) as session:
        first = rebuild_portfolio(seeded, session, exchange="XNYS")
        session.commit()
    with Session(seeded) as session:
        rebuild_portfolio(seeded, session, exchange="XNYS")
        session.commit()

    with seeded.connect() as conn:
        total = conn.execute(text("SELECT count(*) FROM portfolio_snapshots")).scalar_one()
    assert total == first


def test_rebuild_stamps_the_market_on_every_row(seeded: Engine) -> None:
    """`portfolio_snapshots` has no ticker to join through, so the exchange written here
    is the only thing that says which market a book belongs to."""
    with Session(seeded) as session:
        score_history(seeded, session, exchange="XJSE")
        session.commit()
    with Session(seeded) as session:
        rebuild_portfolio(seeded, session, exchange="XJSE")
        session.commit()

    with seeded.connect() as conn:
        exchanges = {
            r.exchange
            for r in conn.execute(text("SELECT DISTINCT exchange FROM portfolio_snapshots"))
        }
    assert exchanges == {"XJSE"}


def test_rebuild_without_predictions_is_a_noop(seeded: Engine) -> None:
    """Prices but no predictions is the state right after a fresh backfill. It must write
    nothing rather than build a book out of an empty signal."""
    with Session(seeded) as session:
        assert rebuild_portfolio(seeded, session, exchange="XNYS") == 0
        session.commit()


def test_a_books_positions_are_recoverable_from_its_snapshot(seeded: Engine) -> None:
    """The positions JSON is what the dashboard's holdings table reads; an empty or
    missing one turns the panel into a blank table with no error."""
    with Session(seeded) as session:
        score_history(seeded, session, exchange="XNYS")
        session.commit()
    with Session(seeded) as session:
        rebuild_portfolio(seeded, session, exchange="XNYS")
        session.commit()

    with seeded.connect() as conn:
        row = conn.execute(
            text(
                "SELECT positions, date FROM portfolio_snapshots "
                "WHERE variant = 'daily' ORDER BY date DESC LIMIT 1"
            )
        ).one()
    assert row.positions, "a snapshot with no positions cannot be displayed or audited"
    assert all(isinstance(w, float) for w in row.positions.values())
    assert isinstance(row.date, dt.date)
