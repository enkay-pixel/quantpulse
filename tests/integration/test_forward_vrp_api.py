"""`/options/forward-vrp` against a real table in the throwaway database.

The endpoint's work is one aggregation — average each snapshot day over its tickers — so that is
what is pinned, on rows whose daily means are known. The mart is stood in for by a table of the
same shape, dropped afterwards; `dbt build` in other tests recreates the real one.
"""

import datetime as dt
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from quantpulse.api.app import create_app
from quantpulse.api.deps import engine_dep, session_dep

pytestmark = pytest.mark.integration

D1, D2 = dt.date(2026, 7, 20), dt.date(2026, 7, 21)


@pytest.fixture
def client(db_engine: Engine) -> Iterator[TestClient]:
    with db_engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS analytics"))
        conn.execute(text("DROP TABLE IF EXISTS analytics.fct_iv_vs_forward_realized"))
        conn.execute(
            text(
                "CREATE TABLE analytics.fct_iv_vs_forward_realized (ticker text, exchange text, "
                "snapshot_date date, atm_iv float, forward_realized_vol_21d float, "
                "forward_premium float)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO analytics.fct_iv_vs_forward_realized VALUES "
                "('A', 'XNYS', :d1, 0.30, 0.20, 0.10), ('B', 'XNYS', :d1, 0.40, 0.40, 0.00), "
                "('A', 'XNYS', :d2, 0.20, 0.25, -0.05), ('X', 'XJSE', :d1, 0.9, 0.1, 0.8)"
            ),
            {"d1": D1, "d2": D2},
        )
    app = create_app()
    app.dependency_overrides[engine_dep] = lambda: db_engine

    def _session() -> Iterator[Session]:
        with Session(db_engine) as session:
            yield session

    app.dependency_overrides[session_dep] = _session
    yield TestClient(app)
    with db_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS analytics.fct_iv_vs_forward_realized"))


def test_each_day_is_averaged_over_its_tickers_for_one_market(client: TestClient) -> None:
    days = client.get("/options/forward-vrp", params={"exchange": "XNYS"}).json()["days"]
    assert [d["snapshot_date"] for d in days] == [str(D1), str(D2)]
    first = days[0]
    assert first["tickers"] == 2
    assert first["implied"] == pytest.approx(0.35)
    assert first["realized"] == pytest.approx(0.30)
    assert first["premium"] == pytest.approx(0.05)
    assert days[1]["premium"] == pytest.approx(-0.05)


def test_a_missing_mart_is_an_empty_series_not_an_error(db_engine: Engine) -> None:
    with db_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS analytics.fct_iv_vs_forward_realized"))
    app = create_app()

    def _session() -> Iterator[Session]:
        with Session(db_engine) as session:
            yield session

    app.dependency_overrides[session_dep] = _session
    body = TestClient(app).get("/options/forward-vrp", params={"exchange": "XNYS"}).json()
    assert body == {"exchange": "XNYS", "days": []}
