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


# --- scoring uses the model's own feature list ---------------------------------------------


def _tiny_booster(cols: list[str]) -> "lgb.Booster":  # type: ignore[name-defined]
    import lightgbm as lgb
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(0)
    x = pd.DataFrame(rng.normal(size=(200, len(cols))), columns=cols)
    y = x[cols[0]] * 2.0 + rng.normal(scale=0.1, size=200)
    return lgb.train(
        {"objective": "regression", "verbose": -1, "num_leaves": 4}, lgb.Dataset(x, y), 5
    )


def test_a_model_is_scored_on_the_columns_it_was_trained_on() -> None:
    """The regression this guards: scoring selected columns by a module-level constant, so a
    model trained on a different list was fed another model's matrix. It does not raise — it
    returns numbers — which is why it would survive a promotion gate unnoticed."""
    import numpy as np
    import pandas as pd

    from quantpulse.ml.registry import predict_with

    booster = _tiny_booster(["vol_21", "ret_5"])
    rng = np.random.default_rng(1)
    # A frame carrying every engineered column, in an unrelated order.
    from quantpulse.features.engineering import FEATURE_COLUMNS

    wide = pd.DataFrame(
        rng.normal(size=(20, len(FEATURE_COLUMNS))), columns=list(reversed(FEATURE_COLUMNS))
    )
    got = predict_with(booster, wide)
    want = booster.predict(wide[["vol_21", "ret_5"]])
    assert np.allclose(got, want)


def test_scoring_does_not_depend_on_the_global_feature_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Changing the engineered list must not change how an already-trained model scores."""
    import numpy as np
    import pandas as pd

    from quantpulse.features import engineering
    from quantpulse.ml.registry import predict_with

    booster = _tiny_booster(["vol_21", "ret_5"])
    rng = np.random.default_rng(2)
    wide = pd.DataFrame(
        rng.normal(size=(20, len(engineering.FEATURE_COLUMNS))),
        columns=list(engineering.FEATURE_COLUMNS),
    )
    before = predict_with(booster, wide)
    monkeypatch.setattr(engineering, "FEATURE_COLUMNS", ["ret_1", "mom_63"])
    assert np.allclose(predict_with(booster, wide), before)
