"""Whether retraining buys skill, rather than whether a frozen model decays.

The staleness curve answers how long a model stays useful on its own. It cannot answer the
question the retrain cadence actually turns on, which is comparative: at a given moment, is a
model trained on everything available now better than the one trained some days earlier?
Scoring both on the *same* forward window holds the market fixed so that only the training
cut-off differs, which a decay curve measured at different times cannot do.

A model fitted at one origin is the stale model for every later window, so each origin is fit
once and scored forward. Model age therefore lands on exact multiples of the origin stride and
every lag is read off the same set of fits, at the cost of the staleness curve rather than a
multiple of it.

Two properties of the design constrain how the result may be read:

  * Seeds are averaged *within* a window before anything is pooled. Treating each (window,
    seed) fit as an independent draw multiplies the apparent sample by the seed count and
    divides the error bar by its square root, which turns a flat result into a sharp one.
  * Windows are not independent either. The model that is fresh for one window is the stale
    model for the next few, and a forward label straddles the window that follows it, so the
    reported standard error allows for serial correlation instead of assuming it away.

This measures retraining *unconditionally*. Production promotes a candidate only when it beats
the incumbent on a holdout, so a negative result here is not directly a statement about the
deployed model — it bounds how much the cadence can be worth before the gate is credited with
the difference.
"""

import logging
from dataclasses import dataclass, replace

import pandas as pd

from quantpulse.data.calendar import DEFAULT_EXCHANGE
from quantpulse.features.engineering import feature_columns_for
from quantpulse.ml.training import TrainConfig

logger = logging.getLogger(__name__)

#: Seeds averaged within each window. A single fit per origin would compare one draw against
#: another and read the seed noise on this panel as a cadence effect.
RETRAIN_SEEDS = (42, 7, 123)


@dataclass(frozen=True)
class LagRow:
    """Fresh-minus-stale IC on a shared forward window, for models this many days apart."""

    lag_days: int
    n_windows: int
    mean_delta: float
    std_error: float
    n_favour_fresh: int


def _newey_west(values: list[float], max_lag: int) -> float:
    """Standard error of the mean that allows neighbouring windows to be correlated.

    Weights fall linearly with distance so the estimate stays non-negative.
    """
    import numpy as np

    arr = np.asarray(values, dtype=float)
    n = len(arr)
    resid = arr - arr.mean()
    var = float(resid @ resid) / n
    for lag in range(1, min(max_lag, n - 1) + 1):
        cov = float(resid[lag:] @ resid[:-lag]) / n
        var += 2.0 * (1.0 - lag / (max_lag + 1)) * cov
    return float(np.sqrt(max(var, 0.0) / n))


def retrain_value(
    engine: object,
    exchange: str = DEFAULT_EXCHANGE,
    cfg: TrainConfig | None = None,
    seeds: tuple[int, ...] = RETRAIN_SEEDS,
    step_days: int = 21,
    max_lag: int = 3,
) -> pd.DataFrame:
    """Compare freshly fitted models against older ones on the same forward windows.

    Returns one row per lag, with the mean IC difference and a standard error that allows for
    correlation between neighbouring windows.
    """
    import numpy as np

    from quantpulse.ml.metrics import information_coefficient
    from quantpulse.ml.pipeline import build_dataset
    from quantpulse.ml.registry import predict_with
    from quantpulse.ml.staleness import _fit_frozen

    cfg = cfg or TrainConfig()
    cols = feature_columns_for(exchange)
    frame = build_dataset(engine, cfg, exchange)  # type: ignore[arg-type]
    dates = sorted(frame["date"].unique())

    # Every origin needs history to train on and `max_lag` later windows to be compared against.
    earliest = max(cfg.min_train_dates + cfg.embargo_days, len(dates) // 2)
    latest = len(dates) - step_days
    origins = list(range(earliest, latest, step_days))
    if len(origins) <= max_lag + 2:
        raise ValueError(
            f"panel has {len(dates)} dates, too few for {max_lag + 3} origins of {step_days}"
        )
    logger.info(
        "%s fitting at %d origins between %s and %s",
        exchange,
        len(origins),
        dates[origins[0]],
        dates[origins[-1]],
    )

    windows = {
        i: frame[frame["date"].isin(dates[o : o + step_days])] for i, o in enumerate(origins)
    }
    # ic[(fit_origin, window, seed)] — one model scored on its own window and later ones.
    ic: dict[tuple[int, int, int], float] = {}
    for i, origin in enumerate(origins):
        train = frame[frame["date"].isin(dates[: origin - cfg.embargo_days])]
        if train.empty:
            continue
        for seed in seeds:
            try:
                booster = _fit_frozen(train, cols, replace(cfg, seed=seed))
            except Exception as exc:
                logger.warning("%s origin %s failed to fit: %s", exchange, dates[origin], exc)
                continue
            for lag in range(max_lag + 1):
                window = windows.get(i + lag)
                if window is None or window.empty:
                    continue
                scored = window.copy()
                scored["pred"] = predict_with(booster, scored)
                value = information_coefficient(scored)
                if value == value:
                    ic[(i, i + lag, seed)] = value

    rows = []
    for lag in range(1, max_lag + 1):
        per_window = []
        for j in range(len(origins)):
            paired = [
                ic[(j, j, seed)] - ic[(j - lag, j, seed)]
                for seed in seeds
                if (j, j, seed) in ic and (j - lag, j, seed) in ic
            ]
            if paired:
                per_window.append(float(np.mean(paired)))
        if len(per_window) < 3:
            continue
        rows.append(
            LagRow(
                lag_days=lag * step_days,
                n_windows=len(per_window),
                mean_delta=float(np.mean(per_window)),
                std_error=_newey_west(per_window, max_lag=max_lag),
                n_favour_fresh=int(sum(1 for v in per_window if v > 0)),
            )
        )
    table = pd.DataFrame([r.__dict__ for r in rows])
    table.attrs["origins"] = len(origins)
    table.attrs["seeds"] = len(seeds)
    return table
