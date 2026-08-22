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

Deltas are only meaningful against the noise floor. Refitting one specification with just
the seed changed moves IC by a small but non-zero amount, and each market's
`ic_promotion_margin` is two standard deviations of that re-roll — so a delta inside the
margin is indistinguishable from reshuffling the RNG, and is reported as such rather than
ranked.
"""

import logging
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
    margin = get_exchange(exchange).ic_promotion_margin
    width = get_exchange(exchange).quantile_width
    frame = build_dataset(engine, cfg, exchange)  # type: ignore[arg-type]

    full_ic = _score_subset(frame, cols, DEFAULT_PARAMS, cfg, width, holdout_fraction)
    logger.info("%s full model holdout IC %.4f (noise margin %.4f)", exchange, full_ic, margin)

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
