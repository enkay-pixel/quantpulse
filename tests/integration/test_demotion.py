"""Rolling back a promotion, and the ordering that keeps the two records together.

Rolling back means changing two records that no transaction spans: MLflow's champion alias
and the Postgres audit trail. The tests that matter are the failure ones — what the database
looks like when the registry refuses decides whether this is safe.
"""

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from quantpulse.db import ModelRun
from quantpulse.ml import registry
from quantpulse.ml.promotion import audit_champion, demote_champion

pytestmark = pytest.mark.integration


class _FakeRegistry:
    """Stands in for MLflow: records alias moves, and can be told to refuse."""

    def __init__(self, champion: str | None, fail: bool = False) -> None:
        self.champion = champion
        self.fail = fail
        self.calls: list[str | None] = []

    def get_champion(self, exchange: str | None = None, **_: object) -> object | None:
        if self.champion is None:
            return None
        return type("MV", (), {"version": self.champion})()

    def promote(self, version: str, exchange: str | None = None, **_: object) -> None:
        if self.fail:
            raise RuntimeError("registry unavailable")
        self.calls.append(version)
        self.champion = version

    def clear_champion(self, exchange: str | None = None, **_: object) -> None:
        if self.fail:
            raise RuntimeError("registry unavailable")
        self.calls.append(None)
        self.champion = None


@pytest.fixture
def wired(db_engine: Engine, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    def _seed(promotions: list[str], champion: str | None, fail: bool = False) -> _FakeRegistry:
        with Session(db_engine) as session:
            session.query(ModelRun).delete()
            for version in promotions:
                session.add(
                    ModelRun(
                        run_type="train",
                        exchange="XJSE",
                        mlflow_run_id=f"run{version}",
                        model_version=version,
                        metrics={"holdout_ic": 0.05},
                        decision="promoted",
                    )
                )
            session.commit()
        fake = _FakeRegistry(champion, fail)
        monkeypatch.setattr(registry, "get_champion", fake.get_champion)
        monkeypatch.setattr(registry, "promote", fake.promote)
        monkeypatch.setattr(registry, "clear_champion", fake.clear_champion)
        return fake

    return _seed


def _rows(engine: Engine) -> list[ModelRun]:
    with Session(engine) as session:
        return list(session.scalars(select(ModelRun).where(ModelRun.run_type == "demotion")))


def test_demotion_writes_the_audit_row_and_moves_the_alias(db_engine: Engine, wired) -> None:  # type: ignore[no-untyped-def]
    fake = wired(["1", "2"], champion="2")
    with Session(db_engine) as session:
        result = demote_champion(session, "XJSE", reason="loses to momentum")

    assert result.demoted_version == "2"
    assert result.fell_back_to == "1", "must fall back to the promotion behind it"
    assert fake.calls == ["1"]
    (row,) = _rows(db_engine)
    assert row.model_version == "2"
    assert row.decision == "rejected"
    assert row.metrics["demotion_reason"] == "loses to momentum"


def test_the_fallback_is_resolved_after_the_new_row_exists(db_engine: Engine, wired) -> None:  # type: ignore[no-untyped-def]
    """`audit_champion` is "the newest promotion with no later demotion", so the row has to
    be visible before the fallback is chosen — otherwise it resolves to the version being
    demoted and the alias never moves."""
    wired(["1", "2"], champion="2")
    with Session(db_engine) as session:
        demote_champion(session, "XJSE", reason="x")
    with Session(db_engine) as session:
        assert audit_champion(session, "XJSE").model_version == "1"  # type: ignore[union-attr]


def test_demoting_the_only_promotion_leaves_no_champion(db_engine: Engine, wired) -> None:  # type: ignore[no-untyped-def]
    """No predictions at all beats predictions from a model judged
    unfit — only one of those is visible on the dashboard as a gap."""
    fake = wired(["1"], champion="1")
    with Session(db_engine) as session:
        result = demote_champion(session, "XJSE", reason="first champion was junk")
    assert result.fell_back_to is None
    assert fake.calls == [None] and fake.champion is None


def test_a_registry_failure_leaves_the_audit_trail_untouched(db_engine: Engine, wired) -> None:  # type: ignore[no-untyped-def]
    """The property the ordering exists for. If the alias cannot move, Postgres must not
    claim it did — a demotion row with the alias still pointing at the demoted model is
    worse than no demotion, because the dashboard would report a rollback that never
    happened while that model kept scoring."""
    wired(["1", "2"], champion="2", fail=True)
    with Session(db_engine) as session, pytest.raises(RuntimeError, match="registry unavailable"):
        demote_champion(session, "XJSE", reason="x")
    assert _rows(db_engine) == [], "audit row survived a failed registry write"


def test_a_dry_run_changes_nothing_but_reports_the_plan(db_engine: Engine, wired) -> None:  # type: ignore[no-untyped-def]
    fake = wired(["1", "2"], champion="2")
    with Session(db_engine) as session:
        result = demote_champion(session, "XJSE", reason="checking", dry_run=True)
    assert (result.demoted_version, result.fell_back_to) == ("2", "1")
    assert fake.calls == [] and fake.champion == "2"
    assert _rows(db_engine) == []


def test_demoting_a_version_that_was_never_promoted_is_refused(db_engine: Engine, wired) -> None:  # type: ignore[no-untyped-def]
    """A demotion withdraws *its own version's* promotion. Against a version that was never
    promoted it withdraws nothing, and leaves a row implying a rollback that never was."""
    wired(["1"], champion="1")
    with Session(db_engine) as session, pytest.raises(ValueError, match="no recorded promotion"):
        demote_champion(session, "XJSE", reason="x", version="7")


def test_demoting_with_no_champion_is_refused(db_engine: Engine, wired) -> None:  # type: ignore[no-untyped-def]
    wired([], champion=None)
    with Session(db_engine) as session, pytest.raises(ValueError, match="no champion to demote"):
        demote_champion(session, "XJSE", reason="x")
