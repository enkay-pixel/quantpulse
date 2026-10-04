"""Guards on the shadow run.

A shadow rides inside the production retrain, so what matters is what it cannot do: fail the
retrain, register or promote anything, or be read as a candidate. Each test here pins one of
those, because each could be loosened without any test noticing and production would carry the
risk silently.
"""

import sys
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest

from quantpulse.data.calendar import get_exchange
from quantpulse.ml import shadow
from quantpulse.ml.fixed_defaults import fixed_default
from quantpulse.orchestration.assets import run_shadow

WINDOW = {
    "holdout_start": "2026-03-02",
    "holdout_end": "2026-08-26",
    "holdout_days": 126,
    "train_start": "2018-04-04",
    "train_end": "2026-01-30",
}


class _Log:
    def __init__(self) -> None:
        self.warnings: list[str] = []

    def warning(self, msg: str, *args: object) -> None:
        self.warnings.append(msg % args)


def test_a_failing_shadow_cannot_fail_the_retrain() -> None:
    """The shadow is a comparison riding along with the retrain. If its failure propagated, a
    bug in the experiment would take the production result down with it."""

    def explodes(*_: object, **__: object) -> dict[str, object]:
        raise RuntimeError("the shadow fit fell over")

    log = _Log()
    result = run_shadow("XJSE", log, record=explodes)
    assert result["status"] == "failed"
    assert "RuntimeError" in str(result["error"])
    assert log.warnings and "production is unaffected" in log.warnings[0]


class _Scalars:
    def __init__(self, row: object) -> None:
        self._row = row

    def first(self) -> object:
        return self._row


class _Session:
    """Just enough of a Session: hands back one production row and records what is added."""

    def __init__(self, production: object) -> None:
        self._production = production
        self.added: list[Any] = []

    def scalars(self, _query: object) -> _Scalars:
        return _Scalars(self._production)

    def add(self, row: Any) -> None:
        self.added.append(row)


def _patch_fit(monkeypatch: pytest.MonkeyPatch, seen: dict[str, Any], holdout_ic: float) -> None:
    """Stand in for the data and the fit, so no database or model is touched."""
    from quantpulse.ml import pipeline

    dates = pd.to_datetime(["2018-04-04", "2026-01-30", "2026-03-02", "2026-08-26"]).date
    frame = pd.DataFrame({"date": dates})
    monkeypatch.setattr(pipeline, "build_dataset", lambda *a, **k: frame)
    monkeypatch.setattr(
        shadow,
        "split_by_date",
        lambda f, *a, **k: (pd.DataFrame({"date": list(dates[:2])}), None),
    )

    def fake_fit(_frame: object, _cols: object, params: dict[str, Any], _cfg: object) -> Any:
        seen["params"] = params
        holdout = pd.DataFrame({"date": pd.to_datetime(["2026-03-02", "2026-08-26"]).date})
        holdout.attrs["days"] = WINDOW["holdout_days"]
        return None, holdout

    monkeypatch.setattr(shadow, "train_final_model", fake_fit)
    monkeypatch.setattr(
        pipeline,
        "score_holdout",
        lambda h, w: {"holdout_ic": holdout_ic, "holdout_sharpe": 1.0},
    )


def _production(window: dict[str, Any], ic: float = 0.0340) -> SimpleNamespace:
    return SimpleNamespace(id=77, model_version="15", metrics={**window, "holdout_ic": ic})


@pytest.mark.parametrize("market", ["XJSE", "XNYS"])
def test_shadow_fits_the_pre_registered_configuration_and_records_a_shadow(
    monkeypatch: pytest.MonkeyPatch, market: str
) -> None:
    """Both markets, because only one of them exercises the ceiling: XNYS's 0.2 leaves the
    defaults' 0.05 untouched, so a shadow that forgot the ceiling would pass there and quietly
    fit XJSE at a rate the ceiling exists to forbid."""
    seen: dict[str, Any] = {}
    _patch_fit(monkeypatch, seen, holdout_ic=0.0464)
    # The fake holdout has 2 dates, so pair against a production row that says the same.
    window = {**WINDOW, "holdout_days": 2, "train_end": "2026-01-30"}
    session = _Session(_production(window))
    result = shadow.record_shadow(object(), session, market)  # type: ignore[arg-type]

    # Exactly the configuration the study named, under this market's ceiling.
    assert seen["params"] == fixed_default(get_exchange(market).learning_rate_ceiling)
    assert seen["params"]["learning_rate"] <= get_exchange(market).learning_rate_ceiling
    assert len(session.added) == 1
    row = session.added[0]
    # A shadow, never a candidate: the readers that select run_type 'train' must pass over it,
    # and a decision would be read as a promotion by the readers that do not look at run_type.
    assert row.run_type == "shadow"
    assert row.decision is None
    assert row.model_version is None
    assert row.mlflow_run_id is None
    assert row.metrics["paired"] is True
    assert row.metrics["shadows_version"] == "15"
    assert row.metrics["delta_ic"] == pytest.approx(0.0464 - 0.0340)
    assert result["paired"] is True


def test_an_unpaired_shadow_says_so_and_reports_no_difference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the shadow and the candidate did not sit the same exam, a difference between their
    scores is not a result. The row must be recorded, flagged, and carry no delta that could be
    averaged in with the real ones."""
    seen: dict[str, Any] = {}
    _patch_fit(monkeypatch, seen, holdout_ic=0.0464)
    stale = {**WINDOW, "holdout_end": "2026-08-19"}  # last week's candidate, a different exam
    session = _Session(_production(stale))
    shadow.record_shadow(object(), session, "XNYS")  # type: ignore[arg-type]
    row = session.added[0]
    assert row.metrics["paired"] is False
    assert row.metrics["delta_ic"] is None
    assert row.decision is None


def test_the_shadow_never_touches_the_model_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Registering is what makes a model aliasable and deserializable as a champion. A shadow that
    registered would be one alias away from scoring the live book."""
    seen: dict[str, Any] = {}
    _patch_fit(monkeypatch, seen, holdout_ic=0.03)
    window = {**WINDOW, "holdout_days": 2}
    tripwire = SimpleNamespace()

    def forbidden(*_: object, **__: object) -> None:
        raise AssertionError("the shadow called the model registry")

    for name in ("log_candidate", "promote", "configure", "load_champion"):
        setattr(tripwire, name, forbidden)
    monkeypatch.setitem(sys.modules, "quantpulse.ml.registry", tripwire)
    shadow.record_shadow(object(), _Session(_production(window)), "XJSE")  # type: ignore[arg-type]
    assert "registry" not in shadow.__dict__, "shadow imports the registry"
