"""How fast a model goes stale, measured rather than assumed.

Retraining weekly is a guess. It is defensible only if skill decays on roughly that
timescale, and nothing here has ever checked. This freezes a model at a point in time and
scores it on successive windows *after* its training data ends, so decay is read off a curve
instead of chosen.

The curve answers one question: how long a model stays useful. A flat curve says the cadence
is too fast and the retrains are spending Optuna budgets to replace nothing; a curve that
falls inside one step says it is too slow and the book runs on a stale model between runs.
"""

import logging
from dataclasses import dataclass, replace

import pandas as pd

from quantpulse.data.calendar import DEFAULT_EXCHANGE, get_exchange
from quantpulse.features.engineering import feature_columns_for
from quantpulse.ml.training import DEFAULT_PARAMS, TrainConfig

logger = logging.getLogger(__name__)

#: Seeds averaged at each age. One fit per age would confuse decay with the seed noise
#: already measured on this panel, which is larger than the effect being looked for.
STALENESS_SEEDS = (42, 7, 123, 2024, 99)


@dataclass(frozen=True)
class AgeBucket:
    """IC of a frozen model, for predictions made this many trading days after training."""

    age_start: int
    age_end: int
    n_days: int
    ic: float
    ic_std_error: float


def staleness_curve(
    engine: object,
    exchange: str = DEFAULT_EXCHANGE,
    cfg: TrainConfig | None = None,
    step_days: int = 21,
    n_steps: int = 4,
    n_origins: int = 5,
    seeds: tuple[int, ...] = STALENESS_SEEDS,
) -> pd.DataFrame:
    """IC by model age, pooled across several freeze points.

    `step_days` counts trading dates and defaults to the forecast horizon, so each bucket is
    one horizon wide. Buckets are consecutive and disjoint.

    The freeze point is repeated. One freeze point gives each age bucket a single window of
    `step_days` dates, and a 21-day IC swings far more with *which* three weeks it covers
    than with anything about the model — a first version of this reported ICs between -0.34
    and +0.20 with no monotonic shape, and quoted a seed-to-seed error that made the swings
    look significant. Rolling the origin gives every age several independent windows, and the
    spread across them is the error that belongs on the point.

    Returns one row per bucket with IC pooled over (origin, seed) and its standard error.
    """
    import numpy as np

    from quantpulse.ml.metrics import information_coefficient
    from quantpulse.ml.pipeline import build_dataset
    from quantpulse.ml.registry import predict_with

    cfg = cfg or TrainConfig()
    cols = feature_columns_for(exchange)
    frame = build_dataset(engine, cfg, exchange)  # type: ignore[arg-type]
    dates = sorted(frame["date"].unique())

    span = step_days * n_steps
    # Every origin needs a full `span` of dates after it, and enough history before it to
    # train on. Origins are spaced so the last one still has its whole span.
    earliest = max(cfg.min_train_dates + cfg.embargo_days, len(dates) // 2)
    latest = len(dates) - span
    if latest <= earliest:
        raise ValueError(
            f"panel has {len(dates)} dates, needs more than {earliest + span} "
            f"for {n_origins} origins of {span} dates"
        )
    stride = max(1, (latest - earliest) // max(1, n_origins - 1))
    origins = [earliest + i * stride for i in range(n_origins) if earliest + i * stride <= latest]
    logger.info(
        "%s freezing at %d origins between %s and %s",
        exchange,
        len(origins),
        dates[origins[0]],
        dates[origins[-1]],
    )

    # ic_by_age[bucket] collects one value per (origin, seed).
    ic_by_age: dict[int, list[float]] = {step: [] for step in range(n_steps)}
    for origin in origins:
        train_dates = dates[: origin - cfg.embargo_days]
        train = frame[frame["date"].isin(train_dates)]
        if train.empty:
            continue
        boosters = []
        for seed in seeds:
            try:
                booster = _fit_frozen(train, cols, replace(cfg, seed=seed))
            except Exception as exc:
                logger.warning("%s origin %s failed to fit: %s", exchange, dates[origin], exc)
                continue
            boosters.append(booster)
        for step in range(n_steps):
            block = dates[origin + step * step_days : origin + (step + 1) * step_days]
            if len(block) < step_days:
                break
            window = frame[frame["date"].isin(block)]
            for booster in boosters:
                scored = window.copy()
                scored["pred"] = predict_with(booster, scored)
                ic = information_coefficient(scored)
                if ic == ic:
                    ic_by_age[step].append(ic)

    rows = []
    for step in range(n_steps):
        values = ic_by_age[step]
        if len(values) < 2:
            continue
        arr = np.array(values)
        rows.append(
            {
                "age_start": step * step_days,
                "age_end": (step + 1) * step_days - 1,
                "n_windows": len(values),
                "ic": float(arr.mean()),
                "ic_std_error": float(arr.std(ddof=1) / np.sqrt(len(arr))),
            }
        )
        logger.info(
            "  age %3d-%3d days  IC %+.4f +/- %.4f  (%d window-fits)",
            rows[-1]["age_start"],
            rows[-1]["age_end"],
            rows[-1]["ic"],
            rows[-1]["ic_std_error"],
            rows[-1]["n_windows"],
        )

    out = pd.DataFrame(rows)
    out.attrs["exchange"] = exchange
    out.attrs["quantile_width"] = get_exchange(exchange).quantile_width
    out.attrs["seeds"] = len(seeds)
    out.attrs["origins"] = len(origins)
    return out


def _fit_frozen(train: pd.DataFrame, cols: list[str], cfg: TrainConfig) -> object:
    """Fit on `train` alone, early-stopping on an inner tail carved from it.

    The forward windows are what the curve measures, so nothing from them may reach the fit
    — not as training rows and not as the early-stopping signal.
    """
    from quantpulse.ml.training import _fit_one, split_by_date

    inner_train, inner_val = split_by_date(train, 0.15, cfg.embargo_days)
    if inner_train.empty or inner_val.empty:
        raise ValueError("inner validation split produced an empty frame")
    return _fit_one(inner_train, inner_val, cols, DEFAULT_PARAMS, cfg)
