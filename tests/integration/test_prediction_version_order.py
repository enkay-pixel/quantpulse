"""When two model versions scored the same date, the *newest* one must win.

`stg_predictions` deduplicates to one score per (ticker, date) and everything downstream
inherits that choice — the paper book, the track record, the alpha decomposition. Picking
the wrong row does not fail anything; it just quietly attributes the evidence to a model
that had already been replaced.

`model_version` is varchar, because that is MLflow's own type, and the dedupe originally
sorted it as text. `'9' > '10'` is true in a string sort, so from version 10 onward the
"newest" version would have been an older model — and any single-digit version from 2 up
beats '10'. Retrains add a version per market per week, so this becomes reachable within
weeks of a market's first champion. Nothing had gone wrong yet because no date carried two
versions, which is exactly why it needed a test rather than a sighting.
"""

import datetime as dt
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine, make_url, text
from sqlalchemy.orm import Session

from quantpulse.data.universe import UniverseEntry, sync_universe
from quantpulse.db import Prediction

pytestmark = pytest.mark.integration

TRANSFORM_DIR = Path(__file__).parents[2] / "transform"
DAY = dt.date(2026, 8, 12)
#: The pair that a text sort gets backwards, and the one that motivated the cast.
OLDER, NEWER = "9", "10"


def _build_staging(db_url: str) -> None:
    from dbt.cli.main import dbtRunner

    url = make_url(db_url)
    env = {
        "DBT_HOST": url.host or "localhost",
        "DBT_PORT": str(url.port or 5432),
        "POSTGRES_USER": url.username or "quantpulse",
        "POSTGRES_PASSWORD": url.password or "quantpulse",
        "POSTGRES_DB": url.database or "market_test",
    }
    old = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    try:
        result = dbtRunner().invoke(
            [
                "build",
                "--select",
                "stg_predictions",
                "--project-dir",
                str(TRANSFORM_DIR),
                "--profiles-dir",
                str(TRANSFORM_DIR),
            ]
        )
        if not result.success:
            raise AssertionError(f"dbt build failed: {result.exception or result.result}")
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@pytest.fixture(scope="module")
def staged(test_db_url: str) -> Iterator[Engine]:
    """One ticker, one date, scored by both version 9 and version 10."""
    engine = create_engine(test_db_url)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE predictions, universe RESTART IDENTITY CASCADE"))
    with Session(engine) as session:
        sync_universe(session, [UniverseEntry("AAPL", "stock")])
        session.commit()  # predictions.ticker is FK-checked on insert
    with Session(engine) as session:
        session.add(Prediction(ticker="AAPL", date=DAY, model_version=OLDER, score=0.11))
        session.add(Prediction(ticker="AAPL", date=DAY, model_version=NEWER, score=0.99))
        session.commit()
    _build_staging(test_db_url)
    yield engine
    engine.dispose()


def _staged_row(engine: Engine) -> tuple[str, float]:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT model_version, score FROM analytics.stg_predictions WHERE date = :d"),
            {"d": DAY},
        ).one()
    return row.model_version, float(row.score)


def test_version_ten_beats_version_nine(staged: Engine) -> None:
    """The case a text sort gets backwards. Ordering by the string would keep '9'."""
    version, score = _staged_row(staged)
    assert version == NEWER, "a text sort put '9' above '10' and served a replaced model"
    assert score == pytest.approx(0.99)


def test_only_one_row_survives_per_ticker_and_date(staged: Engine) -> None:
    """The dedupe still has to dedupe — a cast that broke the row_number would show up
    here as both versions surviving into every downstream mart."""
    with staged.connect() as conn:
        rows = conn.execute(
            text("SELECT count(*) FROM analytics.stg_predictions WHERE date = :d"), {"d": DAY}
        ).scalar_one()
    assert rows == 1
