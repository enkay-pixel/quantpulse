"""One market's paper books must not stop the others', or the marts that read them.

On 2026-11-07 Frankfurt's rebuild passed Postgres's parameter limit. The asset looped over every
market with nothing between them, so the first failure ended the step: no market's books were
written, and dbt, which depends on the step, skipped every mart (incident 41). A failure still has
to be seen, and one that leaves nothing written still has to fail.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest

import dagster as dg
from quantpulse.data.calendar import EXCHANGES
from quantpulse.orchestration import assets


@contextmanager
def _session() -> Iterator[MagicMock]:
    yield MagicMock()


@pytest.fixture
def alerts(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, str]]:
    recorded: list[tuple[str, str, str]] = []
    monkeypatch.setattr(assets, "get_session", _session)
    monkeypatch.setattr(assets, "get_engine", MagicMock)
    monkeypatch.setattr(
        "quantpulse.monitoring.alerts.record_failure",
        lambda job, run, error: recorded.append((job, run, error)),
    )
    return recorded


def _rebuild_fails_for(monkeypatch: pytest.MonkeyPatch, failing: set[str]) -> list[str]:
    rebuilt: list[str] = []

    def rebuild(_engine: object, _session: object, exchange: str) -> int:
        if exchange in failing:
            raise RuntimeError(f"{exchange}: number of parameters must be between 0 and 65535")
        rebuilt.append(exchange)
        return 3

    monkeypatch.setattr("quantpulse.ml.portfolio.rebuild_portfolio", rebuild)
    return rebuilt


def _materialize() -> dg.ExecuteInProcessResult:
    return dg.materialize_to_memory(
        [assets.portfolio_equity], selection=["portfolio_equity"], raise_on_error=False
    )


def test_one_market_failing_leaves_the_others_written_and_the_step_finished(
    alerts: list[tuple[str, str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    first = sorted(EXCHANGES)[0]  # the one that failed first on 11-07, and stopped the rest
    rebuilt = _rebuild_fails_for(monkeypatch, {first})

    result = _materialize()

    assert result.success, "a failed step skips the marts for every market"
    assert rebuilt == sorted(set(EXCHANGES) - {first}), "every other market is still rebuilt"
    metadata = result.asset_materializations_for_node("portfolio_equity")[0].metadata
    assert metadata["failed_markets"].value == first
    assert len(alerts) == 1, "the failure is still raised, once"
    job, _run, error = alerts[0]
    assert job == "portfolio_equity"
    assert first in error and "65535" in error


def test_no_market_rebuilt_fails_the_step(
    alerts: list[tuple[str, str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    _rebuild_fails_for(monkeypatch, set(EXCHANGES))

    result = _materialize()

    assert not result.success, "with nothing written there is nothing for the marts to read"


def test_every_market_rebuilt_raises_no_alert(
    alerts: list[tuple[str, str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    rebuilt = _rebuild_fails_for(monkeypatch, set())

    result = _materialize()

    assert result.success
    assert rebuilt == sorted(EXCHANGES)
    metadata = result.asset_materializations_for_node("portfolio_equity")[0].metadata
    assert metadata["failed_markets"].value == "none"
    assert alerts == []
