"""LightGBM training with purged walk-forward CV and Optuna hyperparameter search."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import lightgbm as lgb
import numpy as np
import optuna
import pandas as pd

from quantpulse.features.engineering import LABEL_COLUMN
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


def _ic_eval(val: pd.DataFrame) -> Callable[[np.ndarray, Any], tuple[str, float, bool]]:
    """Early-stopping metric: the same information coefficient the promotion gate scores.

    Stopping on RMSE while deciding on IC picks the wrong number of rounds. RMSE over noisy
    21-day forward returns is dominated by variance the model cannot explain, so it flattens
    almost at once and stopping fires long before ranking stops improving — on the full panel
    that ended the fit after a single boosting round.

    Spearman is computed as Pearson on within-date ranks, aggregated with bincount rather than
    a groupby, because this runs on every boosting round and a per-date scipy loop over a
    decade of dates dominates the fit.
    """
    codes = pd.factorize(val["date"])[0]
    label_rank = pd.Series(val[LABEL_COLUMN].to_numpy()).groupby(codes).rank().to_numpy()
    counts = np.bincount(codes).astype(float)
    sum_y = np.bincount(codes, label_rank)
    sum_yy = np.bincount(codes, label_rank * label_rank)

    def _eval(preds: np.ndarray, _dataset: Any) -> tuple[str, float, bool]:
        pred_rank = pd.Series(preds).groupby(codes).rank().to_numpy()
        sum_x = np.bincount(codes, pred_rank)
        sum_xx = np.bincount(codes, pred_rank * pred_rank)
        sum_xy = np.bincount(codes, pred_rank * label_rank)
        numerator = counts * sum_xy - sum_x * sum_y
        denominator = np.sqrt(
            np.maximum(counts * sum_xx - sum_x * sum_x, 0.0)
            * np.maximum(counts * sum_yy - sum_y * sum_y, 0.0)
        )
        # A date with fewer than three names, or no spread in either ranking, carries no
        # rank information; `information_coefficient` skips those too.
        usable = (counts >= 3) & (denominator > 0)
        ic = float(np.mean(numerator[usable] / denominator[usable])) if usable.any() else 0.0
        return "ic", ic, True  # higher is better

    return _eval


def _fit_one(
    train: pd.DataFrame,
    val: pd.DataFrame,
    feature_cols: list[str],
    params: dict[str, Any],
    cfg: TrainConfig,
) -> lgb.Booster:
    dtrain = lgb.Dataset(train[feature_cols], label=train[LABEL_COLUMN])
    dval = lgb.Dataset(val[feature_cols], label=val[LABEL_COLUMN], reference=dtrain)
    return lgb.train(
        # "None" switches off the built-in metric so early stopping watches IC alone.
        {**params, "seed": cfg.seed, "metric": "None"},
        dtrain,
        num_boost_round=cfg.num_boost_round,
        valid_sets=[dval],
        feval=_ic_eval(val),
        callbacks=[lgb.early_stopping(cfg.early_stopping_rounds, verbose=False)],
    )


def cross_validated_fold_ics(
    frame: pd.DataFrame,
    feature_cols: list[str],
    params: dict[str, Any],
    cfg: TrainConfig,
    splits: list[DateSplit] | None = None,
) -> list[float]:
    """Out-of-fold information coefficient for each purged walk-forward fold.

    The per-fold values are kept rather than collapsed, because their spread is the only
    thing that says how well the mean is determined. A caller comparing two specifications
    needs that spread; one that only wants a single number can average them.
    """
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
    return fold_ics


def cross_validated_ic(
    frame: pd.DataFrame,
    feature_cols: list[str],
    params: dict[str, Any],
    cfg: TrainConfig,
    splits: list[DateSplit] | None = None,
) -> float:
    """Mean out-of-fold information coefficient across purged walk-forward folds."""
    return float(np.mean(cross_validated_fold_ics(frame, feature_cols, params, cfg, splits)))


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


def split_by_date(
    frame: pd.DataFrame, fraction: float, embargo_days: int
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split off the last `fraction` of dates, with an embargo gap before the cut so
    overlapping forward-return labels cannot straddle the boundary."""
    dates = sorted(frame["date"].unique())
    cut = dates[int(len(dates) * (1 - fraction))]
    embargo_start_idx = max(0, dates.index(cut) - embargo_days)
    return frame[frame["date"] < dates[embargo_start_idx]], frame[frame["date"] >= cut].copy()


def train_final_model(
    frame: pd.DataFrame,
    feature_cols: list[str],
    params: dict[str, Any],
    cfg: TrainConfig,
    holdout_fraction: float = 0.15,
) -> tuple[lgb.Booster, pd.DataFrame]:
    """Train on all but the last `holdout_fraction` of dates; return model + holdout preds.

    The holdout frame (with `pred` column) is the candidate's out-of-sample evidence,
    used by the promotion gate. Early stopping therefore must not see it: the boosting
    rounds are chosen on an *inner* validation tail carved from the training window.
    Otherwise the final fit grinds its rounds toward the exact frame the gate then scores,
    and the "out-of-sample" result is partly fitted.
    """
    train, holdout = split_by_date(frame, holdout_fraction, cfg.embargo_days)
    if train.empty or holdout.empty:
        raise ValueError("Holdout split produced an empty frame")
    inner_train, inner_val = split_by_date(train, holdout_fraction, cfg.embargo_days)
    if inner_train.empty or inner_val.empty:
        raise ValueError("Inner validation split produced an empty frame")
    booster = _fit_one(inner_train, inner_val, feature_cols, params, cfg)
    holdout["pred"] = np.asarray(booster.predict(holdout[feature_cols]))
    return booster, holdout
