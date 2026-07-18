"""Registry round-trip against a throwaway SQLite MLflow backend (no server needed)."""

from pathlib import Path

import lightgbm as lgb
import numpy as np
import pytest

from quantpulse.ml import registry


@pytest.fixture(scope="module")
def tracking(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("mlflow")
    registry.configure(f"sqlite:///{path}/mlflow.db")
    return path


@pytest.fixture(scope="module")
def booster() -> lgb.Booster:
    rng = np.random.default_rng(1)
    x = rng.normal(size=(200, 3))
    y = x[:, 0] * 0.1 + rng.normal(0, 0.01, 200)
    return lgb.train(
        {"objective": "regression", "verbosity": -1},
        lgb.Dataset(x, label=y),
        num_boost_round=5,
    )


def test_log_promote_and_load_champion(tracking: Path, booster: lgb.Booster) -> None:
    assert registry.get_champion() is None
    assert registry.load_champion() is None

    version = registry.log_candidate(
        booster,
        params={"learning_rate": 0.05},
        metrics={"holdout_sharpe": 1.1, "holdout_ic": 0.04, "bad": float("nan")},
        feature_columns=["f1", "f2", "f3"],
        feature_version="v1",
    )
    registry.promote(version.version)

    champion = registry.get_champion()
    assert champion is not None and champion.version == version.version

    metrics = registry.champion_metrics()
    assert metrics is not None
    assert metrics["holdout_sharpe"] == pytest.approx(1.1)
    assert "bad" not in metrics  # NaNs dropped at logging time

    loaded = registry.load_champion()
    assert loaded is not None
    model, meta = loaded
    assert meta.version == version.version
    assert np.isfinite(model.predict(np.zeros((1, 3)))).all()


def test_second_version_supersedes_alias(tracking: Path, booster: lgb.Booster) -> None:
    v2 = registry.log_candidate(
        booster,
        params={},
        metrics={"holdout_sharpe": 2.0},
        feature_columns=["f1"],
        feature_version="v1",
    )
    registry.promote(v2.version)
    champion = registry.get_champion()
    assert champion is not None and champion.version == v2.version
