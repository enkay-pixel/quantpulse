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


def _paired_stats(deltas: list[float]) -> tuple[float, float, float]:
    """Mean of paired differences, its standard error, and t. NaN when there is too little."""
    import numpy as np

    usable = [d for d in deltas if d == d]
    if len(usable) < 2:
        return float("nan"), float("nan"), float("nan")
    arr = np.array(usable)
    se = float(arr.std(ddof=1) / np.sqrt(len(arr)))
    mean = float(arr.mean())
    if se > 0:
        return mean, se, mean / se
    # Zero spread is not missing evidence, so it must not be reported as such. Every seed
    # agreed: either there is no difference at all, or the difference is perfectly repeatable.
    return mean, se, 0.0 if mean == 0 else float(np.sign(mean)) * float("inf")


def _scores_by_seed(
    frame: pd.DataFrame, cols: list[str], cfg: TrainConfig, seeds: tuple[int, ...]
) -> dict[int, float]:
    """Fold-mean IC for `cols` under each seed, keyed by seed so comparisons can pair on it."""
    return {s: _score_subset(frame, cols, DEFAULT_PARAMS, replace(cfg, seed=s)) for s in seeds}


def _holdout_scores_by_seed(
    frame: pd.DataFrame,
    cols: list[str],
    cfg: TrainConfig,
    holdout_fraction: float,
    width: float,
    seeds: tuple[int, ...],
) -> dict[int, float]:
    """Holdout IC for `cols` under each seed, for the one measurement selection never saw."""
    from quantpulse.ml.pipeline import score_holdout

    out: dict[int, float] = {}
    for seed in seeds:
        try:
            _, holdout = train_final_model(
                frame, cols, DEFAULT_PARAMS, replace(cfg, seed=seed), holdout_fraction
            )
        except Exception as exc:
            logger.warning("subset %s failed to fit on seed %s: %s", cols, seed, exc)
            out[seed] = float("nan")
            continue
        out[seed] = score_holdout(holdout, width)["holdout_ic"]
    return out


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

    deltas = []
    for seed, full_ic in full_by_seed.items():
        ic = _score_subset(frame, subset, DEFAULT_PARAMS, replace(cfg, seed=seed))
        if ic == ic and full_ic == full_ic:
            deltas.append(ic - full_ic)
    return _paired_stats(deltas)


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
    #: Holdout IC of the full and selected sets, averaged over seeds.
    full_ic: float
    pruned_ic: float
    #: Paired difference (pruned minus full) on the holdout, with its own error and t.
    delta: float
    delta_se: float
    delta_t: float
    baseline_ic: float
    seeds: int


def forward_select(
    engine: object,
    exchange: str = DEFAULT_EXCHANGE,
    cfg: TrainConfig | None = None,
    holdout_fraction: float = 0.15,
    seeds: tuple[int, ...] = NOISE_SEEDS,
) -> Selection:
    """Build a feature set from nothing, adding only what measurably helps.

    Drop-one deltas do not add up: removing several features that each look costly alone can
    land anywhere, because their effects interact. So the pruned set is *selected* and then
    *measured*, never inferred by summing deltas.

    Every comparison is paired on the seed. A candidate is scored against the set chosen so
    far under the *same* seed, so the seed cancels rather than being carried into the
    difference, and the decision to add rests on whether the improvement repeats rather than
    on whether one draw looked large. Judging single scores against a global floor admits a
    feature whenever a seed happens to favour it, which is the same failure the drop-one
    sweep produced before it was paired.

    The first candidate is compared against no model at all, whose skill is zero by
    definition — so a market where nothing works selects nothing rather than whichever
    feature drew best.

    The selection never sees the holdout. Choosing features by holdout IC fits the choice to
    the holdout, and the resulting number would describe that fit rather than out-of-sample
    behaviour. Candidates are scored by walk-forward folds within the training portion only,
    and the untouched holdout is used once at the end — also paired across seeds — to compare
    the selected set against the full one and against the momentum baseline.
    """
    from quantpulse.ml.baselines import standing_competitor_metrics
    from quantpulse.ml.pipeline import build_dataset
    from quantpulse.ml.training import split_by_date

    cfg = cfg or TrainConfig()
    cols = list(FEATURE_COLUMNS)
    width = get_exchange(exchange).quantile_width
    frame = build_dataset(engine, cfg, exchange)  # type: ignore[arg-type]
    train, _ = split_by_date(frame, holdout_fraction, cfg.embargo_days)

    chosen: list[str] = []
    # An empty feature set has no skill, so the first candidate is measured against zero.
    reference = dict.fromkeys(seeds, 0.0)
    while True:
        candidates = [c for c in cols if c not in chosen]
        if not candidates:
            break
        best: tuple[float, float, float, str] | None = None
        for col in candidates:
            delta, se, t = _paired_delta(train, [*chosen, col], reference, cfg)
            if t == t and t >= RESOLVES_AT_T and (best is None or delta > best[0]):
                best = (delta, se, t, col)
        if best is None:
            break
        delta, se, t, col = best
        chosen.append(col)
        reference = _scores_by_seed(train, chosen, cfg, seeds)
        logger.info("%s + %-22s delta %+.4f +/- %.4f (t %+.2f)", exchange, col, delta, se, t)

    if not chosen:
        logger.warning(
            "%s: no feature improved on an empty model by more than its own noise", exchange
        )

    full_by_seed = _holdout_scores_by_seed(frame, cols, cfg, holdout_fraction, width, seeds)
    usable_full = [v for v in full_by_seed.values() if v == v]
    full_ic = float(sum(usable_full) / len(usable_full)) if usable_full else float("nan")

    if chosen:
        pruned_by_seed = _holdout_scores_by_seed(frame, chosen, cfg, holdout_fraction, width, seeds)
        usable_pruned = [v for v in pruned_by_seed.values() if v == v]
        pruned_ic = (
            float(sum(usable_pruned) / len(usable_pruned)) if usable_pruned else float("nan")
        )
        delta, delta_se, delta_t = _paired_stats(
            [pruned_by_seed[s] - full_by_seed[s] for s in seeds]
        )
    else:
        pruned_ic = delta = delta_se = delta_t = float("nan")

    _, holdout = train_final_model(frame, cols, DEFAULT_PARAMS, cfg, holdout_fraction)
    baseline_ic = standing_competitor_metrics(holdout, width)["holdout_ic"]
    return Selection(
        exchange, chosen, full_ic, pruned_ic, delta, delta_se, delta_t, baseline_ic, len(seeds)
    )
