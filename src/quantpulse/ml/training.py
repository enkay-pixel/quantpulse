"""LightGBM training with purged walk-forward CV and Optuna hyperparameter search."""

import logging
from dataclasses import dataclass, field
from typing import Any

import lightgbm as lgb
import numpy as np
import optuna
import pandas as pd

from quantpulse.ml.cv import DateSplit, purged_walk_forward_splits
from quantpulse.ml.metrics import information_coefficient

logger = logging.getLogger(__name__)

DEFAULT_PARAMS: dict[str, Any] = {
    "objective": "regression",
    "metric": "rmse",
    "learning_rate": 0.05,
    "num_leaves": 31,
    "min_data_in_leaf": 50,
    "feature_fraction": 0.9,
    "bagging_fraction": 0.9,
    "bagging_freq": 1,
    "lambda_l2": 1.0,
    "verbosity": -1,
}


@dataclass(frozen=True)
class TrainConfig:
    horizon_days: int = 21
    n_splits: int = 4
    embargo_days: int = 21  # >= horizon so overlapping labels can't leak
    min_train_dates: int = 126
    num_boost_round: int = 1500
    early_stopping_rounds: int = 50
    optuna_trials: int = 15
    seed: int = 42
    feature_columns: tuple[str, ...] = field(default_factory=tuple)


def _fit_one(
    train: pd.DataFrame,
    val: pd.DataFrame,
    feature_cols: list[str],
    params: dict[str, Any],
    cfg: TrainConfig,
) -> lgb.Booster:
    dtrain = lgb.Dataset(train[feature_cols], label=train["fwd_ret"])
    dval = lgb.Dataset(val[feature_cols], label=val["fwd_ret"], reference=dtrain)
    return lgb.train(
        {**params, "seed": cfg.seed},
        dtrain,
        num_boost_round=cfg.num_boost_round,
        valid_sets=[dval],
        callbacks=[lgb.early_stopping(cfg.early_stopping_rounds, verbose=False)],
    )


def cross_validated_ic(
    frame: pd.DataFrame,
    feature_cols: list[str],
    params: dict[str, Any],
    cfg: TrainConfig,
    splits: list[DateSplit] | None = None,
) -> float:
    """Mean out-of-fold information coefficient across purged walk-forward folds."""
    splits = splits or purged_walk_forward_splits(
        frame["date"].unique().tolist(), cfg.n_splits, cfg.embargo_days, cfg.min_train_dates
    )
    fold_ics: list[float] = []
    for split in splits:
        train = frame[frame["date"].isin(split.train_dates)]
        val = frame[frame["date"].isin(split.val_dates)].copy()
        if train.empty or val.empty:
            continue
        booster = _fit_one(train, val, feature_cols, params, cfg)
        val["pred"] = np.asarray(booster.predict(val[feature_cols]))
        ic = information_coefficient(val)
        if not np.isnan(ic):
            fold_ics.append(ic)
    if not fold_ics:
        raise ValueError("Cross-validation produced no scorable folds")
    return float(np.mean(fold_ics))


def tune_hyperparameters(
    frame: pd.DataFrame, feature_cols: list[str], cfg: TrainConfig
) -> dict[str, Any]:
    """Optuna search (budgeted) maximizing CV information coefficient."""
    splits = purged_walk_forward_splits(
        frame["date"].unique().tolist(), cfg.n_splits, cfg.embargo_days, cfg.min_train_dates
    )

    def objective(trial: optuna.Trial) -> float:
        params = {
            **DEFAULT_PARAMS,
            "learning_rate": trial.suggest_float("learning_rate", 1e-3, 0.2, log=True),
            "num_leaves": trial.suggest_int("num_leaves", 8, 96),
            "min_data_in_leaf": trial.suggest_int("min_data_in_leaf", 20, 200),
            "feature_fraction": trial.suggest_float("feature_fraction", 0.5, 1.0),
            "lambda_l2": trial.suggest_float("lambda_l2", 1e-3, 10.0, log=True),
        }
        return cross_validated_ic(frame, feature_cols, params, cfg, splits)

    sampler = optuna.samplers.TPESampler(seed=cfg.seed)
    study = optuna.create_study(direction="maximize", sampler=sampler)
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study.optimize(objective, n_trials=cfg.optuna_trials, show_progress_bar=False)
    logger.info("Optuna best CV IC=%.4f params=%s", study.best_value, study.best_params)
    return {**DEFAULT_PARAMS, **study.best_params}


def train_final_model(
    frame: pd.DataFrame,
    feature_cols: list[str],
    params: dict[str, Any],
    cfg: TrainConfig,
    holdout_fraction: float = 0.15,
) -> tuple[lgb.Booster, pd.DataFrame]:
    """Train on all but the last `holdout_fraction` of dates; return model + holdout preds.

    The holdout frame (with `pred` column) is the candidate's out-of-sample evidence,
    used by the promotion gate.
    """
    dates = sorted(frame["date"].unique())
    cut = dates[int(len(dates) * (1 - holdout_fraction))]
    embargo_start_idx = max(0, dates.index(cut) - cfg.embargo_days)
    train = frame[frame["date"] < dates[embargo_start_idx]]
    holdout = frame[frame["date"] >= cut].copy()
    if train.empty or holdout.empty:
        raise ValueError("Holdout split produced an empty frame")
    booster = _fit_one(train, holdout, feature_cols, params, cfg)
    holdout["pred"] = np.asarray(booster.predict(holdout[feature_cols]))
    return booster, holdout
