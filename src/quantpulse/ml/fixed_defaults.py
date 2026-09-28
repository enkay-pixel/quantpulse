"""Whether a fixed configuration can replace the tuner.

The tuning-budget work found that most of the tuner's trials are a fixed grid, that no rule
ordering on the folds finds the good ones, and — the reason for both — that refitting identical
parameters with only the seed changed reproduces a trial's holdout score poorly: most of the
variation the search tries to exploit is the fit's own randomness. That predicts a fixed
configuration should do about as well as a searched one. This tests the prediction instead of
acting on it.

The question is **non-inferiority**, not superiority. A fixed configuration costs one fit where a
tuned candidate costs sixty-one, and it is deterministic, so it does not have to win to be worth
adopting; it has to not lose by more than an amount that matters. That amount is the promotion
gate's own margin — the difference the gate itself treats as luck rather than improvement — and
the statistics come from a one-sided confidence bound, not from the margin. Using the margin as a
threshold of practical importance is a different thing from borrowing it as a noise floor, which
is what this project's measurement rules warn against.

Three properties carry the result:

  * The control *is* production. The tuned arm calls the tuner the weekly retrain calls, with its
    budget and sampler, rather than a reconstruction of it — and on the shared origins it has to
    reproduce the tuning-budget study's production arm exactly, which is checked rather than
    assumed.
  * The fixed configurations are chosen by rule, never by result. Ten thousand scored trials exist
    from the earlier rounds, and picking whichever parameters did well in them would be selecting on
    the holdout. So one arm is the pipeline's own defaults and the other is the centre of the space
    the tuner searches, and neither reads a single holdout score to be defined.
  * One fixed arm is pre-registered as the candidate for adoption. The second is a diagnostic for
    whether the particular fixed point matters. Choosing between them by which scored better would
    be the same selection on the holdout by a shorter route.
"""

import datetime as dt
import logging
import math
import time
from dataclasses import dataclass, replace
from typing import Any

import pandas as pd

from quantpulse.data.calendar import DEFAULT_EXCHANGE, get_exchange
from quantpulse.features.engineering import feature_columns_for
from quantpulse.ml.metrics import lag1_autocorrelation, newey_west_se
from quantpulse.ml.training import (
    DEFAULT_PARAMS,
    INTEGER_PARAMS,
    LEARNING_RATE_FLOOR,
    SEARCH_BOUNDS,
    TrainConfig,
)

logger = logging.getLogger(__name__)

#: Seeds averaged within an origin, as in the tuning-budget study — which is also what lets the
#: control arm be checked against that study's production arm cell by cell.
FIXED_SEEDS = (42, 7)

#: The control, and the pre-registered candidate for replacing it. The second fixed arm is
#: reported but is not eligible for adoption on this evidence.
CONTROL = "tuned"
CANDIDATE = "fixed_default"
ARMS = (CONTROL, CANDIDATE, "fixed_center")

#: One-sided 95%. Non-inferiority asks whether the worst plausible loss is acceptable, so only the
#: lower side of the interval matters.
ONE_SIDED_Z = 1.645


def fixed_default(ceiling: float) -> dict[str, Any]:
    """The pipeline's own defaults, with the learning rate held under the market's ceiling.

    The defaults set a rate above the JSE ceiling, and that ceiling exists because rates above it
    were measured to collapse candidates there. Respecting it is applying a decision already made
    on its own evidence, not choosing a value from this comparison's data.
    """
    return {**DEFAULT_PARAMS, "learning_rate": min(float(DEFAULT_PARAMS["learning_rate"]), ceiling)}


def search_center(ceiling: float) -> dict[str, Any]:
    """The centre of the space the tuner searches — what it would pick knowing nothing.

    Geometric midpoints where the search is log-scaled and arithmetic ones elsewhere, read from
    the same bounds the search reads, so the centre cannot drift from the space it is the centre
    of.
    """
    params: dict[str, Any] = {
        **DEFAULT_PARAMS,
        "learning_rate": math.sqrt(LEARNING_RATE_FLOOR * ceiling),
    }
    for name, (low, high, log) in SEARCH_BOUNDS.items():
        mid = math.sqrt(low * high) if log else (low + high) / 2
        params[name] = round(mid) if name in INTEGER_PARAMS else float(mid)
    return params


def truncate_panel(frame: pd.DataFrame, as_of: str | None) -> pd.DataFrame:
    """Keep only the panel's dates on or before `as_of`, or the whole panel when it is None.

    The panel stores dates as `datetime.date`, and pandas refuses to compare those with a
    `Timestamp` — so the cutoff is parsed to the same type rather than to whatever pandas would
    choose. Getting this wrong fails loudly, which is the better outcome; a silent mismatch would
    truncate nothing and reproduce nothing while appearing to.
    """
    if as_of is None:
        return frame
    return frame[frame["date"] <= dt.date.fromisoformat(as_of)]


def non_inferiority(mean_delta: float, std_error: float, margin: float) -> tuple[float, bool]:
    """The one-sided lower bound on an arm's loss, and whether it is within the margin.

    An arm is non-inferior when even the worst loss the data is consistent with — the lower end of
    a one-sided 95% interval on arm minus control — is smaller than the margin. A point estimate
    near zero is not enough: a noisy arm can sit at zero with a bound far below the margin, and
    that is an unresolved comparison, not an acceptable one.
    """
    lower = mean_delta - ONE_SIDED_Z * std_error
    return lower, lower > -margin


@dataclass(frozen=True)
class ArmRow:
    """One arm against the tuned control, pooled across origins."""

    arm: str
    mean_holdout_ic: float
    #: Arm minus control. Positive means the arm did better.
    mean_delta: float
    std_error: float
    n_origins: int
    n_favour: int
    delta_autocorr: float
    #: The lowest loss the data is consistent with, one-sided 95%.
    lower_bound: float
    margin: float
    non_inferior: bool
    #: How much each candidate costs to produce, which is half of the case for switching.
    fits_per_candidate: int
    median_seconds: float


def fixed_defaults(
    engine: object,
    exchange: str = DEFAULT_EXCHANGE,
    cfg: TrainConfig | None = None,
    seeds: tuple[int, ...] = FIXED_SEEDS,
    step_days: int = 21,
    max_lag: int = 3,
    n_origins: int = 24,
    as_of: str | None = None,
) -> pd.DataFrame:
    """Score production's tuned candidate against fixed configurations across rolling origins.

    `as_of` truncates the panel to dates on or before it. Without it the study is not reproducible
    across days: the origin grid is laid from the end of the data, so each weekday's ingest adds a
    labelled date and moves every origin, and a rerun on Tuesday answers a different question from
    Monday's. Pinning it is what lets one run be checked against another.
    """
    from quantpulse.ml.metrics import information_coefficient
    from quantpulse.ml.pipeline import build_dataset
    from quantpulse.ml.training import (
        HOLDOUT_FRACTION,
        split_by_date,
        train_final_model,
        tune_hyperparameters,
    )
    from quantpulse.ml.tuning_budget import rolling_origins

    cfg = cfg or TrainConfig()
    market = get_exchange(exchange)
    ceiling = market.learning_rate_ceiling
    margin = market.ic_promotion_margin
    feature_cols = feature_columns_for(exchange)
    frame = build_dataset(engine, cfg, exchange)  # type: ignore[arg-type]
    frame = truncate_panel(frame, as_of)
    dates = sorted(frame["date"].unique())
    origins = rolling_origins(len(dates), cfg, step_days, n_origins)
    fixed = {CANDIDATE: fixed_default(ceiling), "fixed_center": search_center(ceiling)}
    logger.info(
        "%s: %d origins between %s and %s, %d seed(s), ceiling %.3g, margin %.4f",
        exchange,
        len(origins),
        dates[origins[0] - 1],
        dates[origins[-1] - 1],
        len(seeds),
        ceiling,
        margin,
    )

    cells: list[dict[str, Any]] = []
    for i, origin in enumerate(origins):
        panel = frame[frame["date"].isin(dates[:origin])]
        train_frame, _ = split_by_date(panel, HOLDOUT_FRACTION, cfg.embargo_days)
        if train_frame.empty:
            continue
        for seed in seeds:
            cell_cfg = replace(cfg, seed=seed)

            # The weekly retrain's own tuner, called the way the pipeline calls it.
            started = time.perf_counter()
            tuned_params = tune_hyperparameters(
                train_frame, feature_cols, cell_cfg, learning_rate_ceiling=ceiling
            )
            _, holdout = train_final_model(panel, feature_cols, tuned_params, cell_cfg)
            cells.append(
                {
                    "arm": CONTROL,
                    "origin": i,
                    "seed": seed,
                    "holdout_ic": information_coefficient(holdout),
                    "learning_rate": float(tuned_params["learning_rate"]),
                    "seconds": time.perf_counter() - started,
                }
            )
            for name, params in fixed.items():
                started = time.perf_counter()
                _, holdout = train_final_model(panel, feature_cols, params, cell_cfg)
                cells.append(
                    {
                        "arm": name,
                        "origin": i,
                        "seed": seed,
                        "holdout_ic": information_coefficient(holdout),
                        "learning_rate": float(params["learning_rate"]),
                        "seconds": time.perf_counter() - started,
                    }
                )
        logger.info("%s origin %d/%d done (%s)", exchange, i + 1, len(origins), dates[origin - 1])

    cell_frame = pd.DataFrame(cells)
    # Seeds averaged inside each origin before anything is pooled: the origin is the sample.
    by_origin = cell_frame.pivot_table(
        index="origin", columns="arm", values="holdout_ic", aggfunc="mean"
    )
    control = by_origin[CONTROL]
    # The tuner fits every fold for every trial and then fits the chosen parameters once more; a
    # fixed candidate is only that last fit. The tuning-budget study cost more per trial because it
    # also scored every trial on the holdout, which production never does.
    fits = {CONTROL: cfg.optuna_trials * cfg.n_splits + 1, **dict.fromkeys(fixed, 1)}

    rows: list[ArmRow] = []
    for arm in ARMS:
        if arm not in by_origin:
            continue
        paired = (by_origin[arm] - control).dropna()
        deltas = paired.tolist()
        if not deltas:
            continue
        mean_delta = sum(deltas) / len(deltas)
        se = newey_west_se(deltas, max_lag=max_lag) if arm != CONTROL else 0.0
        lower, within = non_inferiority(mean_delta, se, margin)
        rows.append(
            ArmRow(
                arm=arm,
                mean_holdout_ic=float(by_origin[arm].loc[paired.index].mean()),
                mean_delta=mean_delta,
                std_error=se,
                n_origins=len(deltas),
                n_favour=int(sum(1 for d in deltas if d > 0)),
                delta_autocorr=lag1_autocorrelation(deltas),
                lower_bound=lower,
                margin=margin,
                non_inferior=bool(arm != CONTROL and within),
                fits_per_candidate=fits[arm],
                median_seconds=float(cell_frame.loc[cell_frame["arm"] == arm, "seconds"].median()),
            )
        )

    table = pd.DataFrame([r.__dict__ for r in rows])
    table.attrs["origins"] = len(origins)
    table.attrs["seeds"] = len(seeds)
    table.attrs["first_origin"] = str(dates[origins[0] - 1])
    table.attrs["last_origin"] = str(dates[origins[-1] - 1])
    table.attrs["margin"] = margin
    table.attrs["as_of"] = as_of or "latest"
    table.attrs["panel_end"] = str(dates[-1])[:10]
    # The floor a *paired* difference has to clear: how far the arm-minus-control difference itself
    # moves when only the seed changes, inside one origin. The tuning-budget study compared paired
    # differences against the unpaired spread of a single arm, which double-counts the seed that
    # pairing exists to cancel; this is the quantity that should have been used there.
    by_seed = cell_frame.pivot_table(
        index=["origin", "seed"], columns="arm", values="holdout_ic"
    ).reset_index()
    spreads: dict[str, float] = {}
    for arm in fixed:
        by_seed["paired"] = by_seed[arm] - by_seed[CONTROL]
        diff = by_seed.pivot_table(index="origin", columns="seed", values="paired")
        ranges = (diff.max(axis=1) - diff.min(axis=1)).dropna()
        spreads[arm] = float(ranges.mean()) if len(ranges) else float("nan")
    table.attrs["paired_seed_spread"] = spreads
    table.attrs["cells"] = cell_frame
    return table
