"""A capture refused off-hours must not take the rest of the processing run with it.

dbt depends on `option_chains`, so a failure there skips the marts. Refusing is right, and no retry
can help; failing is what cost the marts a day on 2026-11-03. The refusal still has to be seen,
because a missed capture cannot be fetched again, and any other failure still has to fail.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest

import dagster as dg
from quantpulse.options.ingest import EmptyUniverseSnapshotError, OffHoursSnapshotError
from quantpulse.orchestration import assets


@contextmanager
def _session() -> Iterator[MagicMock]:
    yield MagicMock()


@pytest.fixture
def alerts(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, str]]:
    recorded: list[tuple[str, str, str]] = []
    monkeypatch.setattr(assets, "get_session", _session)
    monkeypatch.setattr("quantpulse.data.universe.options_tickers", lambda session: ["AAPL"])
    monkeypatch.setattr("quantpulse.options.book.held_contracts", lambda session: {})
    monkeypatch.setattr(
        "quantpulse.monitoring.alerts.record_failure",
        lambda job, run, error: recorded.append((job, run, error)),
    )
    return recorded


def _capture_raises(monkeypatch: pytest.MonkeyPatch, error: Exception) -> None:
    def capture(*_args: object, **_kwargs: object) -> int:
        raise error

    monkeypatch.setattr("quantpulse.options.ingest.snapshot_option_chains", capture)


def test_an_off_hours_refusal_finishes_the_step_and_raises_the_alert(
    alerts: list[tuple[str, str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    _capture_raises(monkeypatch, OffHoursSnapshotError("before the close"))
    result = dg.materialize_to_memory([assets.option_chains], selection=["option_chains"])
    assert result.success, "a failed step here skips dbt"
    assert "before the close" in str(
        result.asset_materializations_for_node("option_chains")[0].metadata["skipped"]
    )
    assert len(alerts) == 1, "a missed capture must still be seen"
    assert alerts[0][0] == "option_chains"
    assert "before the close" in alerts[0][2]


def test_a_real_capture_failure_still_fails_the_run(
    alerts: list[tuple[str, str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    _capture_raises(monkeypatch, EmptyUniverseSnapshotError("no chain for any ticker"))
    result = dg.materialize_to_memory(
        [assets.option_chains], selection=["option_chains"], raise_on_error=False
    )
    assert not result.success
    assert not alerts, "the failure sensor raises this one's alert"
