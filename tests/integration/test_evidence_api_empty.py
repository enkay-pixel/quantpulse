"""Evidence endpoints must degrade gracefully before the first dbt build."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from quantpulse.api.app import create_app
from quantpulse.api.deps import engine_dep, session_dep

pytestmark = pytest.mark.integration


@pytest.fixture
def bare_client(db_engine: Engine) -> Iterator[TestClient]:
    with db_engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS analytics CASCADE"))

    app = create_app()
    app.dependency_overrides[engine_dep] = lambda: db_engine

    def _session_override() -> Iterator[Session]:
        with Session(db_engine) as session:
            yield session

    app.dependency_overrides[session_dep] = _session_override
    yield TestClient(app)


def test_endpoints_survive_missing_analytics_schema(bare_client: TestClient) -> None:
    assert bare_client.get("/track-record").json() == {"live_since": None, "phases": []}
    assert bare_client.get("/signals/quintiles").json() == {"overall": [], "recent": []}
    assert bare_client.get("/portfolio/risk").json() == {"points": []}
    assert bare_client.get("/portfolio/positions").json() == {
        "date": None,
        "model_version": None,
        "rows": [],
    }
    assert bare_client.get("/models/history").json() == []
    assert bare_client.get("/portfolio/equity-curve").json()["points"] == []
