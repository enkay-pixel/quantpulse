"""Simpler-model baselines: does the LightGBM layer earn its place?

The ML Test Score audit (docs/ml-test-score.md) scored *"a simpler model is not better"* at
zero, because nothing here had ever been compared against one. That is the first question a
reviewer asks of any ML system, and until it is answered the modelling is unjustified rather
than justified — the promotion gate only ever compared a challenger against the previous
champion, so a whole lineage of models could be beating each other while losing to a rule
that fits on one line.

Every competitor sits **the same exam**: the same holdout frame, cut the same way, scored by
`pipeline.score_holdout` at the market's own quantile width. That is the discipline incident
24 paid for — a model compared on a different window is not compared at all.

The comparison is deliberately unfair in one direction, and it has to be read that way: the
baselines are fitted on this run's training window, while the champion was fitted weeks ago
on a shorter panel and is merely *scored* here. The gate lives with the same asymmetry. It
means a baseline win is suggestive rather than damning, but a baseline **loss** is strong
evidence for the model, since the baseline had the fresher fit and still lost.
"""

import logging
from collections.abc import Callable

import numpy as np
import pandas as pd

from quantpulse.data.calendar import DEFAULT_EXCHANGE, get_exchange
from quantpulse.features.engineering import FEATURE_COLUMNS, LABEL_COLUMN
from quantpulse.ml import registry
from quantpulse.ml.training import TrainConfig, split_by_date

logger = logging.getLogger(__name__)

#: Ridge penalty for the linear baseline. Small — the point is to fit a *linear* model
#: properly, not to tune a competitor into the ground; a swept alpha would make it a
#: second tuned model rather than the simple control it is meant to be.
RIDGE_ALPHA = 1.0

Baseline = Callable[[pd.DataFrame, pd.DataFrame, list[str]], np.ndarray]


def _noise(train: pd.DataFrame, holdout: pd.DataFrame, cols: list[str]) -> np.ndarray:
    """Seeded random scores — the floor.

    Not a competitor but a ruler: it says what IC and Sharpe this backtest produces from a
    signal that certainly contains nothing. Any model whose holdout numbers sit inside this
    one's range has demonstrated nothing, however good they look in isolation.
    """
    return np.random.default_rng(0).normal(size=len(holdout))


def _momentum(train: pd.DataFrame, holdout: pd.DataFrame, cols: list[str]) -> np.ndarray:
    """Rank by 63-day momentum. Zero parameters, zero fitting, decades of literature.

    The single most likely thing to beat a small ML model on cross-sectional equity data,
    and the feature the panel is already known to be sensitive to: incident 24 measured raw
    63-day momentum IC at +0.039 over Mar-Dec 2025 and -0.004 since.
    """
    return holdout["mom_63_cs_rank"].to_numpy(dtype=float)


def _reversal(train: pd.DataFrame, holdout: pd.DataFrame, cols: list[str]) -> np.ndarray:
    """Short-term reversal: buy last month's losers. The other classic zero-parameter rule,
    and momentum's opposite — if both score alike, the backtest is measuring something other
    than either signal."""
    return -holdout["ret_21_cs_rank"].to_numpy(dtype=float)


def _ridge(train: pd.DataFrame, holdout: pd.DataFrame, cols: list[str]) -> np.ndarray:
    """Closed-form ridge on the same 13 features — isolates what the *nonlinearity* buys.

    Same inputs as the champion, same rows, only the functional form differs, so a ridge
    that keeps up says gradient boosting is contributing nothing here beyond variance.
    Solved with numpy rather than scikit-learn: sklearn is only a transitive dependency and
    a normal-equations ridge is three lines, so the comparison adds no supply chain.
    """
    x = train[cols].to_numpy(dtype=float)
    y = train[LABEL_COLUMN].to_numpy(dtype=float)
    ok = np.isfinite(x).all(axis=1) & np.isfinite(y)
    x, y = x[ok], y[ok]
    # Filtering can empty the frame — a panel where every row carries one NaN feature does
    # it, and so does a target column that failed to compute. Left alone, the solve returns
    # coefficients from nothing and the baseline scores as "no signal", which is the most
    # misleading answer available here: it would read as evidence *for* the champion.
    if len(x) <= len(cols):
        raise ValueError(
            f"ridge baseline needs more usable rows than features; got {len(x)} for {len(cols)}"
        )
    # Standardise so one wide-scaled feature does not absorb the whole penalty.
    mean, sd = x.mean(axis=0), x.std(axis=0)
    sd[sd == 0] = 1.0
    xs = (x - mean) / sd
    xs = np.column_stack([xs, np.ones(len(xs))])  # intercept, left unpenalised below
    penalty = RIDGE_ALPHA * np.eye(xs.shape[1])
    penalty[-1, -1] = 0.0

    # NumPy 2.1 on this BLAS backend raises divide/overflow/invalid flags from `matmul`
    # itself on finite, well-conditioned input — measured: inputs finite, Gram finite,
    # condition number 2.4, coefficients finite, warnings raised anyway. Silencing the
    # flags alone would also hide a genuine blow-up, so the result is asserted instead:
    # an unreliable warning traded for a reliable check.
    with np.errstate(divide="ignore", over="ignore", invalid="ignore"):
        coef = np.linalg.solve(xs.T @ xs + penalty, xs.T @ y)
        xh = holdout[cols].to_numpy(dtype=float)
        xh = np.column_stack([(xh - mean) / sd, np.ones(len(xh))])
        preds = np.asarray(xh @ coef, dtype=float)
    if not np.isfinite(coef).all():
        raise ValueError("ridge baseline produced non-finite coefficients")
    return preds


#: Ordered so the report reads floor-first: what noise scores, then the rules, then the
#: linear fit, then the champion.
BASELINES: dict[str, Baseline] = {
    "noise": _noise,
    "momentum": _momentum,
    "reversal": _reversal,
    "ridge": _ridge,
}


def compare_baselines(
    engine: object,
    exchange: str = DEFAULT_EXCHANGE,
    cfg: TrainConfig | None = None,
    tracking_uri: str | None = None,
    holdout_fraction: float = 0.15,
) -> pd.DataFrame:
    """Score every baseline and the current champion on one shared holdout.

    Returns a frame of one row per competitor with the same four metrics the promotion gate
    reads. `holdout_fraction` mirrors `train_final_model`'s default so the exam is the one
    the gate would set.
    """
    from quantpulse.ml.pipeline import build_dataset, score_holdout

    cfg = cfg or TrainConfig()
    cols = list(FEATURE_COLUMNS)
    frame = build_dataset(engine, cfg, exchange)  # type: ignore[arg-type]
    train, holdout = split_by_date(frame, holdout_fraction, cfg.embargo_days)
    if train.empty or holdout.empty:
        raise ValueError(f"{exchange}: holdout split produced an empty frame")

    width = get_exchange(exchange).quantile_width
    rows = []
    for name, fn in BASELINES.items():
        scored = holdout.copy()
        scored["pred"] = fn(train, holdout, cols)
        rows.append({"model": name, **score_holdout(scored, width)})

    if tracking_uri:
        registry.configure(tracking_uri)
    champion = registry.load_champion(exchange=exchange)
    if champion is None:
        logger.warning("%s has no champion to compare against", exchange)
    else:
        booster, version = champion
        scored = holdout.copy()
        scored["pred"] = np.asarray(booster.predict(scored[cols]))
        rows.append({"model": f"champion (v{version.version})", **score_holdout(scored, width)})

    out = pd.DataFrame(rows)
    out.insert(0, "exchange", exchange)
    out.attrs["holdout_start"] = str(holdout["date"].min())
    out.attrs["holdout_end"] = str(holdout["date"].max())
    out.attrs["holdout_days"] = int(holdout["date"].nunique())
    return out
