"""Feature ablation: which of the features actually earn their place?

Thirteen features were chosen up front and never pruned. Adding a feature that contributes
nothing is not free — it widens the search space, adds a vendor field that can break, and
makes every later "the model got worse" harder to attribute.

Two questions, answered on the same holdout the promotion gate uses and scored by the same
`pipeline.score_holdout`:

* **drop-one** — refit without each feature in turn. If IC does not fall, that feature is
  not contributing; if IC *rises*, it is actively costing something.
* **alone** — refit on each feature by itself. A single feature that scores near the full
  model says the other twelve are decoration.

Hyperparameters are held fixed rather than retuned per subset. Retuning would vary two
things at once and the difference could no longer be attributed to the feature.

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


def _score_subset(
    frame: pd.DataFrame,
    cols: list[str],
    params: dict[str, Any],
    cfg: TrainConfig,
    width: float,
    holdout_fraction: float,
) -> float:
    """Fit on `cols` and return holdout IC, or NaN if the subset cannot be fitted."""
    from quantpulse.ml.pipeline import score_holdout

    try:
        _, holdout = train_final_model(frame, cols, params, cfg, holdout_fraction)
    except Exception as exc:
        logger.warning("subset %s failed to fit: %s", cols, exc)
        return float("nan")
    return score_holdout(holdout, width)["holdout_ic"]


#: Seeds used to measure how much holdout IC moves when nothing but the RNG changes.
NOISE_SEEDS = (42, 7, 123, 2024, 99)


def measured_noise_floor(
    frame: pd.DataFrame,
    cols: list[str],
    cfg: TrainConfig,
    width: float,
    holdout_fraction: float,
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
        ic = _score_subset(
            frame, cols, DEFAULT_PARAMS, replace(cfg, seed=seed), width, holdout_fraction
        )
        if ic == ic:
            ics.append(ic)
    if len(ics) < 2:
        return float("nan")
    return float(2 * np.std(ics, ddof=1))


def ablation_report(
    engine: object,
    exchange: str = DEFAULT_EXCHANGE,
    cfg: TrainConfig | None = None,
    holdout_fraction: float = 0.15,
) -> pd.DataFrame:
    """Drop-one and alone IC for every feature, against the full model on one holdout.

    Returns a frame with one row per feature carrying `drop_ic` (IC without it),
    `delta` (drop_ic minus full_ic, so negative means removing it hurt), `alone_ic`, and
    `verdict`. `frame.attrs` holds the full-model IC and the market's noise margin.
    """
    from quantpulse.ml.pipeline import build_dataset

    cfg = cfg or TrainConfig()
    cols = list(FEATURE_COLUMNS)
    width = get_exchange(exchange).quantile_width
    frame = build_dataset(engine, cfg, exchange)  # type: ignore[arg-type]

    margin = measured_noise_floor(frame, cols, cfg, width, holdout_fraction)
    full_ic = _score_subset(frame, cols, DEFAULT_PARAMS, cfg, width, holdout_fraction)
    logger.info(
        "%s full model holdout IC %.4f (measured noise floor %.4f)", exchange, full_ic, margin
    )

    rows = []
    for col in cols:
        remaining = [c for c in cols if c != col]
        drop_ic = _score_subset(frame, remaining, DEFAULT_PARAMS, cfg, width, holdout_fraction)
        alone_ic = _score_subset(frame, [col], DEFAULT_PARAMS, cfg, width, holdout_fraction)
        delta = drop_ic - full_ic
        if delta != delta:  # NaN
            verdict = "could not fit"
        elif delta <= -margin:
            verdict = "carries signal"
        elif delta >= margin:
            verdict = "costs signal — removing it helps"
        else:
            verdict = "within noise — not shown to contribute"
        rows.append(
            {
                "feature": col,
                "drop_ic": drop_ic,
                "delta": delta,
                "alone_ic": alone_ic,
                "verdict": verdict,
            }
        )
        logger.info("  %-22s drop %.4f (%+.4f) alone %.4f", col, drop_ic, delta, alone_ic)

    out = pd.DataFrame(rows).sort_values("delta").reset_index(drop=True)
    out.attrs["exchange"] = exchange
    out.attrs["full_ic"] = full_ic
    out.attrs["noise_margin"] = margin
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

    inner_margin = measured_noise_floor(train, cols, cfg, width, holdout_fraction)
    margin = measured_noise_floor(frame, cols, cfg, width, holdout_fraction)
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
        scored = [
            (_score_subset(train, [*chosen, c], DEFAULT_PARAMS, cfg, width, holdout_fraction), c)
            for c in candidates
        ]
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

    full_ic = _score_subset(frame, cols, DEFAULT_PARAMS, cfg, width, holdout_fraction)
    pruned_ic = (
        _score_subset(frame, chosen, DEFAULT_PARAMS, cfg, width, holdout_fraction)
        if chosen
        else float("nan")
    )
    _, holdout = train_final_model(frame, cols, DEFAULT_PARAMS, cfg, holdout_fraction)
    baseline_ic = standing_competitor_metrics(holdout, width)["holdout_ic"]
    return Selection(exchange, chosen, full_ic, pruned_ic, baseline_ic, margin, inner_margin)
