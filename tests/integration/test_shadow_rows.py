"""The shadow's guarantees, held by the schema the migrations build.

Unit tests pin the code that writes shadow rows. These pin the table and the readers, because the
readers that identify champions by `decision = 'promoted'` alone do not look at run_type at all —
so whether a shadow can ever be mistaken for a promotion is a property of the table, and has to be
tested against the table the migrations actually produce.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from quantpulse.api.app import create_app
from quantpulse.api.deps import engine_dep, session_dep
from quantpulse.db import ModelRun

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("decision", ["promoted", "rejected"])
def test_the_table_refuses_a_shadow_with_any_decision(db_engine: Engine, decision: str) -> None:
    with Session(db_engine) as session:
        session.add(ModelRun(run_type="shadow", exchange="XNYS", metrics={}, decision=decision))
        with pytest.raises(IntegrityError, match="shadow_never_decides"):
            session.commit()


def test_the_table_accepts_a_shadow_without_one(db_engine: Engine) -> None:
    with Session(db_engine) as session:
        session.add(ModelRun(run_type="shadow", exchange="XNYS", metrics={"holdout_ic": 0.05}))
        session.commit()
        stored = session.scalars(select(ModelRun).where(ModelRun.run_type == "shadow")).one()
        assert stored.decision is None


@pytest.fixture
def client(db_engine: Engine) -> Iterator[TestClient]:
    with Session(db_engine) as session:
        session.add_all(
            [
                ModelRun(
                    run_type="train",
                    exchange="XNYS",
                    model_version="15",
                    metrics={"holdout_ic": 0.034},
                    decision="rejected",
                ),
                ModelRun(run_type="shadow", exchange="XNYS", metrics={"holdout_ic": 0.046}),
            ]
        )
        session.commit()
    app = create_app()

    def _session_override() -> Iterator[Session]:
        with Session(db_engine) as s:
            yield s

    app.dependency_overrides[engine_dep] = lambda: db_engine
    app.dependency_overrides[session_dep] = _session_override
    yield TestClient(app)


def test_model_history_shows_production_and_not_the_shadow(client: TestClient) -> None:
    """The dashboard's history is what ran or could have run. A shadow listed there would read as
    a decision nobody made."""
    rows = client.get("/models/history?exchange=XNYS").json()
    assert [r["run_type"] for r in rows] == ["train"]
