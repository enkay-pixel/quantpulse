import datetime as dt

import pandas as pd
import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from quantpulse.data.ingest import BAR_COLUMNS, upsert_prices
from quantpulse.data.universe import UniverseEntry, active_tickers, sync_universe
from quantpulse.db import Price, UniverseMember

pytestmark = pytest.mark.integration

ENTRIES = [UniverseEntry("AAPL", "stock"), UniverseEntry("SPY", "etf")]


def bars_frame(close: float = 101.0) -> pd.DataFrame:
    rows = [
        ["AAPL", dt.date(2024, 7, 1), 100.0, 102.0, 99.0, close, 1_000_000, "yfinance"],
        ["AAPL", dt.date(2024, 7, 2), 101.0, 103.0, 100.0, close + 1, 1_100_000, "yfinance"],
        ["SPY", dt.date(2024, 7, 1), 500.0, 502.0, 499.0, 501.0, 5_000_000, "yfinance"],
    ]
    return pd.DataFrame(rows, columns=BAR_COLUMNS)


def test_universe_sync_add_update_deactivate(db_engine: Engine) -> None:
    with Session(db_engine) as session:
        counts = sync_universe(session, ENTRIES)
        session.commit()
        assert counts == {"added": 2, "updated": 0, "deactivated": 0}
        assert active_tickers(session) == ["AAPL", "SPY"]

        counts = sync_universe(session, [ENTRIES[0]])  # SPY leaves the universe
        session.commit()
        assert counts == {"added": 0, "updated": 0, "deactivated": 1}
        assert active_tickers(session) == ["AAPL"]

        counts = sync_universe(session, ENTRIES)  # SPY returns
        session.commit()
        assert counts["updated"] == 1
        assert active_tickers(session) == ["AAPL", "SPY"]


def test_upsert_prices_is_idempotent_and_updates(db_engine: Engine) -> None:
    with Session(db_engine) as session:
        sync_universe(session, ENTRIES)
        session.commit()

        assert upsert_prices(session, bars_frame()) == 3
        session.commit()
        assert session.scalar(select(func.count()).select_from(Price)) == 3

        # Same keys, new close: row count stays, value updates.
        assert upsert_prices(session, bars_frame(close=150.0)) == 3
        session.commit()
        assert session.scalar(select(func.count()).select_from(Price)) == 3
        updated = session.get(Price, ("AAPL", dt.date(2024, 7, 1)))
        assert updated is not None and updated.close == 150.0


def test_constraints_reject_unknown_ticker(db_engine: Engine) -> None:
    from sqlalchemy.exc import IntegrityError

    bad = pd.DataFrame(
        [["ZZZZ", dt.date(2024, 7, 1), 1.0, 1.0, 1.0, 1.0, 0, "yfinance"]],
        columns=BAR_COLUMNS,
    )
    with Session(db_engine) as session, pytest.raises(IntegrityError):
        upsert_prices(session, bad)
        session.commit()


def test_check_constraint_rejects_nonpositive_price(db_engine: Engine) -> None:
    from sqlalchemy.exc import IntegrityError

    with Session(db_engine) as session:
        sync_universe(session, ENTRIES)
        session.commit()
        session.add(
            Price(
                ticker="AAPL",
                date=dt.date(2024, 8, 1),
                open=0.0,
                high=1.0,
                low=0.5,
                close=1.0,
                volume=10,
                source="yfinance",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_universe_table_has_metadata_columns(db_engine: Engine) -> None:
    with Session(db_engine) as session:
        member = session.get(UniverseMember, "AAPL")
        if member is None:
            sync_universe(session, ENTRIES)
            session.commit()
            member = session.get(UniverseMember, "AAPL")
        assert member is not None
        assert member.added_at is not None


def test_categorical_check_constraints_reject_bad_values(db_engine) -> None:  # type: ignore[no-untyped-def]
    """The domain columns constrain their vocabulary at the DB level, like asset_type and
    option_type. Guards against a regression that drops the CHECK or a code path that
    writes a value outside the set."""
    import datetime as dt

    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    from quantpulse.data.universe import UniverseEntry, sync_universe
    from quantpulse.db import ModelRun, Price

    with Session(db_engine) as s:
        sync_universe(s, [UniverseEntry("AAA", "stock")])
        s.commit()

    cases = [
        ModelRun(run_type="bogus", exchange="XNYS", metrics={}),  # bad run_type
        ModelRun(run_type="train", exchange="XNYS", decision="maybe", metrics={}),  # bad decision
        Price(  # bad source
            ticker="AAA",
            date=dt.date(2020, 1, 2),
            open=1,
            high=1,
            low=1,
            close=1,
            volume=1,
            source="bloomberg",
        ),
    ]
    for bad in cases:
        with Session(db_engine) as s, pytest.raises(IntegrityError):
            s.add(bad)
            s.commit()

    # ...and the allowed values pass, including the demotion audit value.
    with Session(db_engine) as s:
        s.add(ModelRun(run_type="demotion", exchange="XJSE", decision="rejected", metrics={}))
        s.commit()
        assert s.scalar(text("select count(*) from model_runs where run_type='demotion'")) == 1
