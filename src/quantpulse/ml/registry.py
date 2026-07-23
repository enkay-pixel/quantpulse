"""MLflow tracking + model registry helpers. Champion selection uses registry aliases."""

import logging
from typing import Any

import lightgbm as lgb
import mlflow
from mlflow.entities.model_registry import ModelVersion
from mlflow.tracking import MlflowClient

from quantpulse.data.calendar import DEFAULT_EXCHANGE

logger = logging.getLogger(__name__)

MODEL_NAME = "quantpulse-lgbm"  # legacy single-market name; see model_name()
CHAMPION_ALIAS = "champion"
EXPERIMENT_NAME = "quantpulse-training"


def model_name(exchange: str = DEFAULT_EXCHANGE) -> str:
    """Registry name for a market's champion.

    One model per exchange: different sessions, currencies and dynamics, and pooling them
    would muddle attribution for no gain in data we are short of.
    """
    return f"{MODEL_NAME}-{exchange.lower()}"


def configure(tracking_uri: str) -> None:
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(EXPERIMENT_NAME)


def log_candidate(
    booster: lgb.Booster,
    params: dict[str, Any],
    metrics: dict[str, float],
    feature_columns: list[str],
    feature_version: str,
    exchange: str = DEFAULT_EXCHANGE,
) -> ModelVersion:
    """Log a training run and register the model; returns the new registry version."""
    name = model_name(exchange)
    with mlflow.start_run() as run:
        mlflow.log_params({k: v for k, v in params.items() if not k.startswith("_")})
        mlflow.log_metrics({k: v for k, v in metrics.items() if v == v})  # drop NaNs
        mlflow.set_tags(
            {
                "feature_version": feature_version,
                "feature_columns": ",".join(feature_columns),
                "exchange": exchange,
            }
        )
        mlflow.lightgbm.log_model(booster, name="model", registered_model_name=name)
        run_id = run.info.run_id
    client = MlflowClient()
    versions = client.search_model_versions(f"name = '{name}' and run_id = '{run_id}'")
    if not versions:
        raise RuntimeError(f"Model version for run {run_id} not found after registration")
    return versions[0]


def get_champion(
    client: MlflowClient | None = None, exchange: str = DEFAULT_EXCHANGE
) -> ModelVersion | None:
    client = client or MlflowClient()
    try:
        return client.get_model_version_by_alias(model_name(exchange), CHAMPION_ALIAS)
    except mlflow.exceptions.MlflowException:
        return None


def promote(
    version: str, client: MlflowClient | None = None, exchange: str = DEFAULT_EXCHANGE
) -> None:
    client = client or MlflowClient()
    client.set_registered_model_alias(model_name(exchange), CHAMPION_ALIAS, version)
    logger.info("%s model version %s promoted to @%s", exchange, version, CHAMPION_ALIAS)


def load_champion(exchange: str = DEFAULT_EXCHANGE) -> tuple[lgb.Booster, ModelVersion] | None:
    """Load this market's champion booster, or None if it has no champion yet."""
    champion = get_champion(exchange=exchange)
    if champion is None:
        return None
    model = mlflow.lightgbm.load_model(f"models:/{model_name(exchange)}@{CHAMPION_ALIAS}")
    return model, champion


def champion_metrics(
    client: MlflowClient | None = None, exchange: str = DEFAULT_EXCHANGE
) -> dict[str, float] | None:
    """Metrics logged with this market's champion training run."""
    client = client or MlflowClient()
    champion = get_champion(client, exchange)
    if champion is None or not champion.run_id:
        return None
    run = client.get_run(champion.run_id)
    return dict(run.data.metrics)
