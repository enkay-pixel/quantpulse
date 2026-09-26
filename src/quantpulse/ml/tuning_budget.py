"""Whether the tuner's budget buys a better candidate, or only a longer search.

The search is smaller than its trial count suggests. A TPE sampler spends its first
`n_startup_trials` drawing independently, and only then starts using the objective — so at the
production budget most of the trials are a fixed grid that depends on the seed and the bounds
and not at all on the data. The same grid is therefore re-drawn at every retrain, and a
candidate that wins on one of those draws was not tuned in any useful sense.

That makes "give the tuner more trials" only one of the answers worth testing, and not the
first. The prior question is whether choosing the best cross-validated trial beats not
choosing at all, because if it does not then the budget is irrelevant and a larger one just
costs more. So the arms here are **selection rules scored on the same trials**, and two of them
cannot be using the objective at all.

Three properties of the design carry the result:

  * Rules select on cross-validated IC and are scored on the holdout. The holdout is read to
    evaluate a rule, never to choose within one, except for the oracle — which exists only to
    bound how much of any rule's apparent skill is the upward bias of a maximum over noisy
    evaluations, and is not a target any rule could reach.
  * Arms that share a sampler share its trials exactly. A TPE study run for the long budget has
    the production budget as its own opening, because the sampler is sequential and seeded, so
    the two arms are compared on identical fits rather than on separate runs of the same recipe.
    The same holds across samplers: a TPE sampler's warm-up draws are the independent sampler's
    draws at the same seed, so the learning and no-learning arms agree for the whole warm-up and
    diverge only once the objective starts being used. Every contrast here is therefore paired
    trial by trial, and the production arm is literally an independent search of warm-up length
    followed by a handful of informed trials.
  * Seeds are averaged within an origin before anything is pooled, and the error across origins
    allows neighbouring origins to be correlated. Successive panels here differ by a week
    against years of shared history, so treating each fit as an independent draw would report a
    sample many times larger than the period contains.
"""

import logging
from dataclasses import dataclass, replace
from typing import Any

import optuna
import pandas as pd

from quantpulse.data.calendar import DEFAULT_EXCHANGE, get_exchange
from quantpulse.features.engineering import feature_columns_for
from quantpulse.ml.metrics import newey_west_se
from quantpulse.ml.training import TrainConfig

logger = logging.getLogger(__name__)

#: Seeds averaged within each origin. Two rather than more because the origin is the unit of
#: generalisation: re-drawing the fit does not re-draw the market, so compute spent on extra
#: seeds quietens a cell without adding sample size, while compute spent on extra origins adds
#: both.
BUDGET_SEEDS = (42, 7)

#: The production budget, and the sampler's own default warm-up. Their difference is the number
#: of trials that actually see the objective.
PRODUCTION_TRIALS = 15
PRODUCTION_STARTUP = 10
#: A longer budget, and a shorter warm-up at the production budget. One buys more informed
#: trials by paying for them; the other buys them by drawing fewer blind ones.
LONG_TRIALS = 40
SHORT_STARTUP = 5


@dataclass(frozen=True)
class Rule:
    """One way of picking a single trial out of a recorded study.

    `sees` is the field the rule is allowed to order on, and is the whole point of the
    comparison: a rule that sees nothing is the control that says whether ordering on
    cross-validated IC carries any information at all.
    """

    name: str
    study: str
    n_trials: int
    sees: str  # "cv_ic" | "holdout_ic" | "nothing"
    note: str


RULES: tuple[Rule, ...] = (
    Rule("prod", "tpe10", PRODUCTION_TRIALS, "cv_ic", "what production does today"),
    Rule("tpe10_40", "tpe10", LONG_TRIALS, "cv_ic", "more trials, same warm-up"),
    Rule("tpe5_15", "tpe5", PRODUCTION_TRIALS, "cv_ic", "same trials, shorter warm-up"),
    Rule("rand_15", "rand", PRODUCTION_TRIALS, "cv_ic", "no learning, production budget"),
    Rule("rand_40", "rand", LONG_TRIALS, "cv_ic", "no learning, long budget"),
    Rule("arbitrary", "tpe10", PRODUCTION_TRIALS, "nothing", "no selection at all"),
    Rule("oracle_40", "tpe10", LONG_TRIALS, "holdout_ic", "bias bound, not a target"),
)

#: The control arm every other arm is differenced against.
CONTROL = "prod"


@dataclass(frozen=True)
class RuleRow:
    """One rule's result, pooled across origins."""

    rule: str
    sees: str
    mean_holdout_ic: float
    mean_delta: float
    std_error: float
    n_origins: int
    n_favour: int
    mean_learning_rate: float
    note: str


def _study(name: str, seed: int) -> tuple[optuna.Study, int]:
    """Build one of the three recorded studies, with the trial count it needs.

    The long TPE study doubles as the production one: its first `PRODUCTION_TRIALS` trials are
    exactly what a study of that length would have produced, because the sampler is sequential
    and seeded. Running them separately would pay twice for the same fits and then compare the
    arms across two runs instead of within one.
    """
    if name == "tpe10":
        sampler: optuna.samplers.BaseSampler = optuna.samplers.TPESampler(
            seed=seed, n_startup_trials=PRODUCTION_STARTUP
        )
        return optuna.create_study(direction="maximize", sampler=sampler), LONG_TRIALS
    if name == "tpe5":
        sampler = optuna.samplers.TPESampler(seed=seed, n_startup_trials=SHORT_STARTUP)
        return optuna.create_study(direction="maximize", sampler=sampler), PRODUCTION_TRIALS
    if name == "rand":
        sampler = optuna.samplers.RandomSampler(seed=seed)
        return optuna.create_study(direction="maximize", sampler=sampler), LONG_TRIALS
    raise ValueError(f"unknown study {name}")


def _record_study(
    study_name: str,
    seed: int,
    panel: pd.DataFrame,
    train_frame: pd.DataFrame,
    feature_cols: list[str],
    cfg: TrainConfig,
    ceiling: float,
    splits: list[Any],
) -> list[dict[str, float]]:
    """Run one study, scoring every trial on the gate's holdout as well as on the folds.

    Production scores only the trial it selects. Scoring all of them is what lets a selection
    rule be judged after the fact without re-running the search, and costs one extra fit per
    trial against the folds' several.
    """
    from quantpulse.ml.metrics import information_coefficient
    from quantpulse.ml.training import (
        cross_validated_ic,
        suggest_params,
        train_final_model,
    )

    study, n_trials = _study(study_name, seed)
    rows: list[dict[str, float]] = []
    for _ in range(n_trials):
        trial = study.ask()
        params = suggest_params(trial, learning_rate_ceiling=ceiling)
        try:
            cv_ic = cross_validated_ic(train_frame, feature_cols, params, cfg, splits)
            _, holdout = train_final_model(panel, feature_cols, params, cfg)
            holdout_ic = information_coefficient(holdout)
        except Exception as exc:  # a single bad draw must not end the origin
            logger.warning("trial failed in %s: %s", study_name, exc)
            study.tell(trial, float("-inf"))
            continue
        study.tell(trial, cv_ic)
        rows.append(
            {
                "cv_ic": cv_ic,
                "holdout_ic": holdout_ic,
                "learning_rate": float(params["learning_rate"]),
            }
        )
    return rows


def _pick(rows: list[dict[str, float]], rule: Rule, arbitrary_index: int) -> dict[str, float]:
    """Apply one rule to a study's recorded trials."""
    window = rows[: rule.n_trials]
    if not window:
        raise ValueError(f"{rule.name}: no trials to pick from")
    if rule.sees == "nothing":
        # Positional, so it cannot be ordering on anything the data produced. This is the
        # control that tells a working selection rule apart from a budget that merely draws
        # more points and keeps the luckiest.
        return window[arbitrary_index % len(window)]
    return max(window, key=lambda r: r[rule.sees])


def tuning_budget(
    engine: object,
    exchange: str = DEFAULT_EXCHANGE,
    cfg: TrainConfig | None = None,
    seeds: tuple[int, ...] = BUDGET_SEEDS,
    step_days: int = 21,
    max_lag: int = 3,
    n_origins: int = 24,
) -> pd.DataFrame:
    """Score selection rules against what production does, across rolling origins.

    Each origin re-runs the production procedure on the panel truncated at that date, so every
    cell is a retrain that could have happened that week rather than a variation on one window.

    Returns one row per rule. `mean_delta` is the paired holdout-IC difference against the
    production rule, averaged over seeds inside an origin and then over origins.
    """
    from quantpulse.ml.cv import purged_walk_forward_splits
    from quantpulse.ml.pipeline import build_dataset
    from quantpulse.ml.training import HOLDOUT_FRACTION, split_by_date

    cfg = cfg or TrainConfig()
    ceiling = get_exchange(exchange).learning_rate_ceiling
    feature_cols = feature_columns_for(exchange)
    frame = build_dataset(engine, cfg, exchange)  # type: ignore[arg-type]
    dates = sorted(frame["date"].unique())

    # Origins are spaced by the label horizon rather than by the retrain cadence: a weekly
    # stride would tile the period with holdouts that are nearly the same window, which adds
    # rows without adding evidence.
    latest = len(dates)
    earliest = max(cfg.min_train_dates + cfg.embargo_days, len(dates) // 3)
    span = latest - earliest
    if span < step_days * 4:
        raise ValueError(f"panel has {len(dates)} dates, too few for origins of {step_days}")
    origins = list(range(earliest, latest, step_days))[-n_origins:]
    logger.info(
        "%s: %d origins between %s and %s, %d seed(s), ceiling %.3g",
        exchange,
        len(origins),
        dates[origins[0] - 1],
        dates[origins[-1] - 1],
        len(seeds),
        ceiling,
    )

    # picked[(rule, origin_index, seed)] -> the selected trial's record
    picked: dict[tuple[str, int, int], dict[str, float]] = {}
    for i, origin in enumerate(origins):
        panel = frame[frame["date"].isin(dates[:origin])]
        train_frame, _ = split_by_date(panel, HOLDOUT_FRACTION, cfg.embargo_days)
        if train_frame.empty:
            continue
        splits = purged_walk_forward_splits(
            train_frame["date"].unique().tolist(),
            cfg.n_splits,
            cfg.embargo_days,
            cfg.min_train_dates,
        )
        for seed in seeds:
            cell_cfg = replace(cfg, seed=seed)
            studies: dict[str, list[dict[str, float]]] = {}
            for study_name in ("tpe10", "tpe5", "rand"):
                studies[study_name] = _record_study(
                    study_name,
                    seed,
                    panel,
                    train_frame,
                    feature_cols,
                    cell_cfg,
                    ceiling,
                    splits,
                )
            for rule in RULES:
                rows = studies[rule.study]
                if len(rows) < rule.n_trials:
                    continue
                try:
                    picked[(rule.name, i, seed)] = _pick(rows, rule, arbitrary_index=i * 7 + seed)
                except ValueError as exc:
                    logger.warning("%s at origin %s: %s", rule.name, dates[origin - 1], exc)
        logger.info("%s origin %d/%d done (%s)", exchange, i + 1, len(origins), dates[origin - 1])

    def per_origin(rule_name: str, field: str) -> dict[int, float]:
        """Average a field over seeds inside each origin."""
        out: dict[int, float] = {}
        for i in range(len(origins)):
            vals = [picked[(rule_name, i, s)][field] for s in seeds if (rule_name, i, s) in picked]
            if vals:
                out[i] = sum(vals) / len(vals)
        return out

    control = per_origin(CONTROL, "holdout_ic")
    results: list[RuleRow] = []
    for rule in RULES:
        arm = per_origin(rule.name, "holdout_ic")
        shared = sorted(set(arm) & set(control))
        if not shared:
            continue
        deltas = [arm[i] - control[i] for i in shared]
        lrs = per_origin(rule.name, "learning_rate")
        results.append(
            RuleRow(
                rule=rule.name,
                sees=rule.sees,
                mean_holdout_ic=sum(arm[i] for i in shared) / len(shared),
                mean_delta=sum(deltas) / len(deltas),
                std_error=newey_west_se(deltas, max_lag=max_lag),
                n_origins=len(shared),
                n_favour=int(sum(1 for d in deltas if d > 0)),
                mean_learning_rate=sum(lrs[i] for i in shared if i in lrs)
                / max(len([i for i in shared if i in lrs]), 1),
                note=rule.note,
            )
        )

    table = pd.DataFrame([r.__dict__ for r in results])
    table.attrs["origins"] = len(origins)
    table.attrs["seeds"] = len(seeds)
    table.attrs["first_origin"] = str(dates[origins[0] - 1])
    table.attrs["last_origin"] = str(dates[origins[-1] - 1])
    # The floor this comparison has to clear, measured under this procedure rather than
    # borrowed: how far the control's own holdout IC moves when only the seed changes.
    spreads = [
        max(vals) - min(vals)
        for i in range(len(origins))
        if len(
            vals := [
                picked[(CONTROL, i, s)]["holdout_ic"] for s in seeds if (CONTROL, i, s) in picked
            ]
        )
        > 1
    ]
    table.attrs["seed_spread"] = sum(spreads) / len(spreads) if spreads else float("nan")
    return table
