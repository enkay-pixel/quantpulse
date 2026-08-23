"""The promotion gate must examine both models on the same holdout.

The incumbent's stored metrics were measured on a different panel (a backfill grew it)
and under different evaluation code (flat vs measured turnover). Comparing a fresh
candidate against those numbers promoted a model with no demonstrable edge. The gate now
re-scores the incumbent on the candidate's exact holdout — stored metrics are never
consulted at decision time.
"""

from types import SimpleNamespace

import lightgbm as lgb
import numpy as np
import pandas as pd
import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from quantpulse.db import ModelRun
from quantpulse.features.engineering import FEATURE_COLUMNS
from quantpulse.ml import pipeline, registry
from quantpulse.ml.training import DEFAULT_PARAMS, TrainConfig

pytestmark = pytest.mark.integration

CFG = TrainConfig(
    n_splits=3,
    embargo_days=5,
    min_train_dates=60,
    num_boost_round=40,
    early_stopping_rounds=8,
    optuna_trials=2,
)


def _panel() -> pd.DataFrame:
    """Synthetic panel with a learnable signal in the first two feature columns."""
    rng = np.random.default_rng(7)
    dates = pd.bdate_range("2023-01-02", periods=200).date
    rows = []
    for date in dates:
        for i in range(20):
            vals = rng.normal(size=len(FEATURE_COLUMNS))
            fwd = 0.03 * vals[0] - 0.015 * vals[1] + rng.normal(0, 0.01)
            row: dict[str, object] = {"ticker": f"T{i}", "date": date, "fwd_ret": fwd}
            row.update(zip(FEATURE_COLUMNS, vals, strict=True))
            rows.append(row)
    return pd.DataFrame(rows)


def test_incumbent_sits_the_same_exam_and_the_window_is_recorded(
    db_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    frame = _panel()
    # An incumbent with no signal: same features, shuffled targets.
    noise = frame.copy()
    noise["fwd_ret"] = np.random.default_rng(8).permutation(noise["fwd_ret"].to_numpy())
    champ = lgb.train(
        {**DEFAULT_PARAMS, "seed": 1},
        lgb.Dataset(noise[list(FEATURE_COLUMNS)], label=noise["fwd_ret"]),
        num_boost_round=20,
    )

    monkeypatch.setattr(pipeline, "build_dataset", lambda engine, cfg, exchange: frame)
    monkeypatch.setattr(pipeline, "tune_hyperparameters", lambda f, cols, cfg: dict(DEFAULT_PARAMS))
    monkeypatch.setattr(
        registry,
        "load_champion",
        # run_id is part of a real ModelVersion; the gate reads it to recover the panel
        # the incumbent was fitted to. None stands for a model logged before spans were
        # recorded, which is the case the gate has to warn about rather than assume away.
        lambda exchange=None: (champ, SimpleNamespace(version="1", run_id=None)),
    )
    monkeypatch.setattr(
        registry, "log_candidate", lambda *a, **k: SimpleNamespace(version="2", run_id="run-2")
    )
    promoted: dict[str, str] = {}
    monkeypatch.setattr(
        registry, "promote", lambda version, exchange=None: promoted.setdefault("v", str(version))
    )

    def _poisoned(exchange: str | None = None) -> dict[str, float]:
        raise AssertionError("gate consulted stored champion metrics")

    monkeypatch.setattr(registry, "champion_metrics", _poisoned)

    with Session(db_engine) as session:
        summary = pipeline.train_evaluate_promote(db_engine, session, cfg=CFG, exchange="XNYS")
        session.commit()

    # Real signal beats the no-signal incumbent on the same exam; stored metrics unused.
    assert summary["promoted"] is True
    assert promoted["v"] == "2"

    with Session(db_engine) as session:
        run = session.scalars(select(ModelRun).order_by(ModelRun.id.desc())).first()
    assert run is not None
    # The exam window is in the audit row, so a moved holdout is visible, not archaeology.
    assert run.metrics["holdout_days"] > 0
    assert run.metrics["holdout_start"] < run.metrics["holdout_end"]
