"""The pipeline loads only native LightGBM boosters from the registry.

MLflow's LightGBM loader picks its loader from the model's own metadata and unpickles anything that
is not a booster, and the registry is writable by whatever reaches MLflow's API. Found in the
2026-10-22 security review: with MLflow's cross-origin checks disabled, a web page in this machine's
browser could have registered a pickled model and moved @champion to it. The pipeline must refuse
that model before reading it, whatever wrote the registry.
"""

from pathlib import Path

import lightgbm as lgb
import numpy as np
import pytest
import yaml

from quantpulse.ml import registry
from quantpulse.ml.registry import BOOSTER_CLASS, UntrustedModelFormat, load_booster


def _model_dir(tmp_path: Path, model_class: str | None, data: str | None = "model.lgb") -> Path:
    rng = np.random.default_rng(0)
    X, y = rng.random((60, 3)), rng.random(60)
    lgb.train({"verbosity": -1, "num_leaves": 4}, lgb.Dataset(X, y), num_boost_round=3).save_model(
        str(tmp_path / "model.lgb")
    )
    flavor = {"data": data, "lgb_version": lgb.__version__}
    if model_class is not None:
        flavor["model_class"] = model_class
    (tmp_path / "MLmodel").write_text(yaml.safe_dump({"flavors": {"lightgbm": flavor}}))
    return tmp_path


@pytest.fixture
def served(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """Point the registry download at a local directory instead of an MLflow server."""

    def serve(directory: Path) -> None:
        monkeypatch.setattr(
            registry.mlflow.artifacts, "download_artifacts", lambda artifact_uri: str(directory)
        )

    return serve


def test_a_native_booster_loads(tmp_path: Path, served) -> None:  # type: ignore[no-untyped-def]
    served(_model_dir(tmp_path, BOOSTER_CLASS))
    booster = load_booster("models:/quantpulse-lgbm-xnys/1")
    assert isinstance(booster, lgb.Booster) and booster.num_trees() == 3


def test_a_pickled_model_is_refused_before_it_is_read(tmp_path: Path, served) -> None:  # type: ignore[no-untyped-def]
    """What MLflow would unpickle: the metadata names a scikit-learn class."""
    d = _model_dir(tmp_path, "lightgbm.sklearn.LGBMRegressor", data="model.pkl")
    (d / "model.pkl").write_bytes(b"not reached")
    served(d)
    with pytest.raises(UntrustedModelFormat, match="refusing to load"):
        load_booster("models:/quantpulse-lgbm-xnys@champion")


def test_a_model_without_its_class_or_data_is_refused(tmp_path: Path, served) -> None:  # type: ignore[no-untyped-def]
    served(_model_dir(tmp_path, None))
    with pytest.raises(UntrustedModelFormat):
        load_booster("models:/x/1")


def test_a_data_path_outside_the_models_own_files_is_refused(tmp_path: Path, served) -> None:  # type: ignore[no-untyped-def]
    inner = tmp_path / "model"
    inner.mkdir()
    served(_model_dir(inner, BOOSTER_CLASS, data="../elsewhere.lgb"))
    with pytest.raises(UntrustedModelFormat, match="outside its own files"):
        load_booster("models:/x/1")
