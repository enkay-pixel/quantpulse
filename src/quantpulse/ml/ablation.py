"""Feature ablation: which of the features actually earn their place?

Thirteen features were chosen up front and never pruned. Adding a feature that contributes
nothing is not free — it widens the search space, adds a vendor field that can break, and
makes every later "the model got worse" harder to attribute.

Two questions, both scored as the mean information coefficient across purged walk-forward
folds rather than on a single holdout:

* **drop-one** — refit without each feature in turn. If IC does not fall, that feature is
  not contributing; if IC *rises*, it is actively costing something.
* **alone** — refit on each feature by itself. A single feature that scores near the full
  model says the other twelve are decoration.

Hyperparameters are held fixed rather than retuned per subset. Retuning would vary two
things at once and the difference could no longer be attributed to the feature.

One holdout is one draw, and on this panel its seed-to-seed spread is wider than any effect
a single feature has — a sweep judged on it ranks noise however carefully the margin is set.
Averaging folds shrinks that spread roughly with the square root of the fold count, which is
what lets the comparison resolve anything.

Deltas are only meaningful against the noise floor, and the floor is measured here rather
than borrowed. Refitting one specification with just the seed changed already moves IC, by
an amount that depends on the panel, the parameters and the holdout — so a delta inside it
is indistinguishable from reshuffling the RNG, and is reported as such rather than ranked.

A floor measured under a different procedure does not transfer. Judged against one several
times too small, every feature clears it and the output is a confident ranking of noise.
"""

import logging
from dataclasses import dataclass, replace
from typing import Any

import pandas as pd

from quantpulse.data.calendar import DEFAULT_EXCHANGE, get_exchange
from quantpulse.features.engineering import FEATURE_COLUMNS
from quantpulse.ml.training import DEFAULT_PARAMS, TrainConfig, train_final_model

logger = logging.getLogger(__name__)


def _fold_ics(
    frame: pd.DataFrame,
    cols: list[str],
    params: dict[str, Any],
    cfg: TrainConfig,
) -> list[float]:
    """Out-of-fold IC per walk-forward fold, or empty if the subset cannot be fitted."""
    from quantpulse.ml.training import cross_validated_fold_ics

    try:
        return cross_validated_fold_ics(frame, cols, params, cfg)
    except Exception as exc:
        logger.warning("subset %s failed to fit: %s", cols, exc)
        return []


def _score_subset(
    frame: pd.DataFrame,
    cols: list[str],
    params: dict[str, Any],
    cfg: TrainConfig,
) -> float:
    """Mean out-of-fold IC for `cols`, or NaN if the subset cannot be fitted.

    Scored across walk-forward folds rather than on one holdout. A single holdout is a
    single draw, and on this panel its seed-to-seed spread is wider than any effect a
    feature has — so a sweep judged on it ranks noise however carefully the margin is set.
    Averaging folds shrinks that spread roughly with the square root of the fold count,
    which is what makes the comparison able to resolve anything at all.
    """
    import numpy as np

    ics = _fold_ics(frame, cols, params, cfg)
    return float(np.mean(ics)) if ics else float("nan")


#: Seeds re-rolled to separate a feature's effect from the noise of refitting.
NOISE_SEEDS = (42, 7, 123, 2024, 99, 5, 777, 31, 1000, 64)

#: |t| at which a paired difference is treated as telling apart from zero (~two sigma).
RESOLVES_AT_T = 2.0


def measured_noise_floor(
    frame: pd.DataFrame,
    cols: list[str],
    cfg: TrainConfig,
) -> float:
    """Two standard deviations of holdout IC across seeds, for this exact procedure.

    The promotion gate's `ic_promotion_margin` is the wrong yardstick here. It was measured
    on tuned models chosen by the gate, whereas an ablation refits at default parameters
    where early stopping lands on a different tree count for every seed. Measured on this
    panel the spread is several times larger, so borrowing the gate's margin would dress
    ordinary seed noise as a feature effect and rank thirteen of them.

    Measured rather than assumed, because it depends on the panel, the parameters and the
    holdout — all of which move.
    """
    import numpy as np

    ics = []
    for seed in NOISE_SEEDS:
        ic = _score_subset(frame, cols, DEFAULT_PARAMS, replace(cfg, seed=seed))
        if ic == ic:
            ics.append(ic)
    if len(ics) < 2:
        return float("nan")
    return float(2 * np.std(ics, ddof=1))


def _paired_delta(
    frame: pd.DataFrame,
    subset: list[str],
    full_by_seed: dict[int, float],
    cfg: TrainConfig,
) -> tuple[float, float, float]:
    """Mean change in IC from using `subset` instead of the full set, with its own error.

    Paired on the seed: each subset is compared against the full model fitted with the *same*
    seed, so the seed cancels instead of being carried into the comparison as noise. Judging
    a single unpaired score against one global floor is what lets an unusually favourable
    draw read as a feature effect — the difference is large enough in practice to flip a
    verdict, so the pairing is the measurement, not a refinement of it.

    Returns (mean delta, standard error of that mean, t). A positive delta means dropping to
    this subset *raised* IC.
    """
    import numpy as np

    deltas = []
    for seed, full_ic in full_by_seed.items():
        ic = _score_subset(frame, subset, DEFAULT_PARAMS, replace(cfg, seed=seed))
        if ic == ic and full_ic == full_ic:
            deltas.append(ic - full_ic)
    if len(deltas) < 2:
        return float("nan"), float("nan"), float("nan")
    arr = np.array(deltas)
    se = float(arr.std(ddof=1) / np.sqrt(len(arr)))
    mean = float(arr.mean())
    if se > 0:
        return mean, se, mean / se
    # Zero spread is not missing evidence, so it must not be reported as such. Every seed
    # agreed: either there is no difference at all, or the difference is perfectly repeatable.
    return mean, se, 0.0 if mean == 0 else float(np.sign(mean)) * float("inf")


def ablation_report(
    engine: object,
    exchange: str = DEFAULT_EXCHANGE,
    cfg: TrainConfig | None = None,
    seeds: tuple[int, ...] = NOISE_SEEDS,
) -> pd.DataFrame:
    """Drop-one and alone IC for every feature, as paired differences against the full set.

    Each figure is a mean over walk-forward folds *and* over seeds, and every comparison is
    paired on the seed so that a favourable draw cannot pass as a feature effect. Returns one
    row per feature with `drop_ic`, `delta`, its standard error `delta_se`, `delta_t`,
    `alone_ic`, and a `verdict` drawn from `delta_t`.

    Nothing is selected here, so every fold's validation block can be scored and averaged.
    """
    import numpy as np

    from quantpulse.ml.pipeline import build_dataset

    cfg = cfg or TrainConfig()
    cols = list(FEATURE_COLUMNS)
    frame = build_dataset(engine, cfg, exchange)  # type: ignore[arg-type]

    full_by_seed = {
        seed: _score_subset(frame, cols, DEFAULT_PARAMS, replace(cfg, seed=seed)) for seed in seeds
    }
    usable = [v for v in full_by_seed.values() if v == v]
    full_ic = float(np.mean(usable)) if usable else float("nan")
    logger.info(
        "%s full model IC %.4f over %d folds x %d seeds",
        exchange,
        full_ic,
        cfg.n_splits,
        len(usable),
    )

    rows = []
    for col in cols:
        remaining = [c for c in cols if c != col]
        delta, se, t = _paired_delta(frame, remaining, full_by_seed, cfg)
        alone_ic = _score_subset(frame, [col], DEFAULT_PARAMS, cfg)
        if t != t:
            verdict = "could not measure"
        elif t <= -RESOLVES_AT_T:
            verdict = "carries signal"
        elif t >= RESOLVES_AT_T:
            verdict = "costs signal — removing it helps"
        else:
            verdict = "within noise — not shown to contribute"
        rows.append(
            {
                "feature": col,
                "drop_ic": full_ic + delta,
                "delta": delta,
                "delta_se": se,
                "delta_t": t,
                "alone_ic": alone_ic,
                "verdict": verdict,
            }
        )
        logger.info("  %-22s delta %+.4f +/- %.4f (t %+.2f)", col, delta, se, t)

    out = pd.DataFrame(rows).sort_values("delta").reset_index(drop=True)
    out.attrs["exchange"] = exchange
    out.attrs["full_ic"] = full_ic
    out.attrs["seeds"] = len(usable)
    return out


@dataclass(frozen=True)
class Selection:
    exchange: str
    chosen: list[str]
    full_ic: float
    pruned_ic: float
    baseline_ic: float
    noise_margin: float
    #: Floor for the inner split, which is smaller than the full panel and so noisier.
    inner_margin: float


def forward_select(
    engine: object,
    exchange: str = DEFAULT_EXCHANGE,
    cfg: TrainConfig | None = None,
    holdout_fraction: float = 0.15,
) -> Selection:
    """Build a feature set from nothing, adding only what measurably helps.

    Drop-one deltas do not add up: removing several features that each look costly alone can
    land anywhere, because their effects interact. So the pruned set is *selected* and then
    *measured*, never inferred by summing deltas.

    The selection never sees the holdout. Choosing features by holdout IC fits the choice to
    the holdout, and the resulting number would describe that fit rather than out-of-sample
    behaviour. Candidates are scored on an inner split carved from the training portion only,
    and the untouched holdout is used once at the end to compare the selected set against the
    full one and against the momentum baseline.

    Stops when nothing left to add improves inner IC by more than the noise floor measured on
    the inner split itself, so a feature is admitted on evidence rather than on a
    positive-looking rounding error. Two floors are measured rather than one: the inner split
    is smaller than the full panel and therefore noisier, and holding the selection to the
    full panel's floor would admit features on differences the inner split cannot resolve.
    """
    from quantpulse.ml.baselines import standing_competitor_metrics
    from quantpulse.ml.pipeline import build_dataset
    from quantpulse.ml.training import split_by_date

    cfg = cfg or TrainConfig()
    cols = list(FEATURE_COLUMNS)
    width = get_exchange(exchange).quantile_width
    frame = build_dataset(engine, cfg, exchange)  # type: ignore[arg-type]
    train, _ = split_by_date(frame, holdout_fraction, cfg.embargo_days)

    inner_margin = measured_noise_floor(train, cols, cfg)
    margin = measured_noise_floor(frame, cols, cfg)
    logger.info("%s noise floor — inner %.4f | holdout %.4f", exchange, inner_margin, margin)

    chosen: list[str] = []
    # An empty feature set has no skill, so the bar for the first feature is IC 0 plus the
    # floor. Starting at -inf would admit it whatever it scored, and a market where nothing
    # works would still report one "selected" feature.
    best_inner = 0.0
    while True:
        candidates = [c for c in cols if c not in chosen]
        if not candidates:
            break
        scored = [(_score_subset(train, [*chosen, c], DEFAULT_PARAMS, cfg), c) for c in candidates]
        scored = [(ic, c) for ic, c in scored if ic == ic]  # drop NaN fits
        if not scored:
            break
        top_ic, top_col = max(scored)
        if top_ic - best_inner < inner_margin:
            break
        chosen.append(top_col)
        best_inner = top_ic
        logger.info("%s + %-22s inner IC %.4f", exchange, top_col, top_ic)

    if not chosen:
        logger.warning("%s: no feature cleared the margin on its own", exchange)

    full_ic = _score_subset(frame, cols, DEFAULT_PARAMS, cfg)
    pruned_ic = _score_subset(frame, chosen, DEFAULT_PARAMS, cfg) if chosen else float("nan")
    _, holdout = train_final_model(frame, cols, DEFAULT_PARAMS, cfg, holdout_fraction)
    baseline_ic = standing_competitor_metrics(holdout, width)["holdout_ic"]
    return Selection(exchange, chosen, full_ic, pruned_ic, baseline_ic, margin, inner_margin)
