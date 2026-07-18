"""MLflow tracking + model registry helpers. Champion selection uses registry aliases."""

import logging
from typing import Any

import lightgbm as lgb
import mlflow
from mlflow.entities.model_registry import ModelVersion
from mlflow.tracking import MlflowClient

logger = logging.getLogger(__name__)

MODEL_NAME = "quantpulse-lgbm"
CHAMPION_ALIAS = "champion"
EXPERIMENT_NAME = "quantpulse-training"


def configure(tracking_uri: str) -> None:
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(EXPERIMENT_NAME)


def log_candidate(
    booster: lgb.Booster,
    params: dict[str, Any],
    metrics: dict[str, float],
    feature_columns: list[str],
    feature_version: str,
) -> ModelVersion:
    """Log a training run and register the model; returns the new registry version."""
    with mlflow.start_run() as run:
        mlflow.log_params({k: v for k, v in params.items() if not k.startswith("_")})
        mlflow.log_metrics({k: v for k, v in metrics.items() if v == v})  # drop NaNs
        mlflow.set_tags(
            {"feature_version": feature_version, "feature_columns": ",".join(feature_columns)}
        )
        mlflow.lightgbm.log_model(booster, name="model", registered_model_name=MODEL_NAME)
        run_id = run.info.run_id
    client = MlflowClient()
    versions = client.search_model_versions(f"name = '{MODEL_NAME}' and run_id = '{run_id}'")
    if not versions:
        raise RuntimeError(f"Model version for run {run_id} not found after registration")
    return versions[0]


def get_champion(client: MlflowClient | None = None) -> ModelVersion | None:
    client = client or MlflowClient()
    try:
        return client.get_model_version_by_alias(MODEL_NAME, CHAMPION_ALIAS)
    except mlflow.exceptions.MlflowException:
        return None


def promote(version: str, client: MlflowClient | None = None) -> None:
    client = client or MlflowClient()
    client.set_registered_model_alias(MODEL_NAME, CHAMPION_ALIAS, version)
    logger.info("Model version %s promoted to @%s", version, CHAMPION_ALIAS)


def load_champion() -> tuple[lgb.Booster, ModelVersion] | None:
    """Load the champion booster, or None if no champion exists yet."""
    champion = get_champion()
    if champion is None:
        return None
    model = mlflow.lightgbm.load_model(f"models:/{MODEL_NAME}@{CHAMPION_ALIAS}")
    return model, champion


def champion_metrics(client: MlflowClient | None = None) -> dict[str, float] | None:
    """Metrics logged with the current champion's training run."""
    client = client or MlflowClient()
    champion = get_champion(client)
    if champion is None or not champion.run_id:
        return None
    run = client.get_run(champion.run_id)
    return dict(run.data.metrics)
