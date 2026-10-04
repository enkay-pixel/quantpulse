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
import math
from dataclasses import dataclass, replace
from typing import Any

import optuna
import pandas as pd

from quantpulse.data.calendar import DEFAULT_EXCHANGE, get_exchange
from quantpulse.features.engineering import feature_columns_for
from quantpulse.ml.metrics import lag1_autocorrelation, newey_west_se
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

#: Added to a cell's seed to refit its trials a second time. The offset is large so a replicate
#: can never collide with another cell's own seed, which would make the two indistinguishable.
REPLICATE_SEED_OFFSET = 1000


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
class Transfer:
    """One rank correlation measured inside a cell and pooled across origins.

    A selection rule can only work if the quantity it orders on orders the holdout too, so this
    asks the question the arms answer indirectly: across the trials of a single study, does a
    better fold score go with a better holdout score? It uses all forty trials of a cell rather
    than the single fit a rule selects, which is where its power comes from.

    `against` names the positive control's partner. The learning rate is known to matter — high
    rates score the folds well and the holdout badly — so if the rate correlates with the holdout
    while the fold score does not, a null on the fold score is a real null rather than IC
    estimates too noisy to correlate with anything.
    """

    name: str
    study: str
    against: str
    trials: str
    mean_rho: float
    std_error: float
    n_origins: int
    n_positive: int
    note: str


#: Correlations measured per cell. The warm-up and informed splits are separated because the
#: informed trials are drawn toward the fold optimum, and whether that changes how well they
#: transfer is the whole question restated.
TRANSFERS: tuple[tuple[str, str, str, str, str], ...] = (
    ("cv_all", "tpe10", "cv_ic", "all", "do the folds order the holdout, over the long budget"),
    ("cv_warmup", "tpe10", "cv_ic", "warmup", "the same, over the blind draws only"),
    ("cv_informed", "tpe10", "cv_ic", "informed", "the same, over the trials that used the folds"),
    ("cv_random", "rand", "cv_ic", "all", "the same, with no learning anywhere in the trials"),
    ("lr_all", "tpe10", "learning_rate", "all", "positive control — a known real effect"),
    (
        "reliability",
        "tpe10",
        "replicate_ic",
        "all",
        "the same parameters refitted at another seed — is the holdout score reproducible at all",
    ),
)

#: The row whose correlation bounds every other row's. A measure cannot correlate with anything
#: more strongly than it correlates with itself.
RELIABILITY = "reliability"


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
    #: Lag-1 autocorrelation of this arm's per-origin differences. Reported rather than assumed:
    #: it is what says whether the error width allows for enough neighbours.
    delta_autocorr: float
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

    Each trial is also refitted at a second seed with its parameters held fixed, which measures
    how reproducible the holdout score is at all. Only the final fit is repeated — the folds do
    not need re-running, because the parameters are not being re-chosen — so the replicate costs
    one fit against the six already being paid, not a second run.
    """
    from quantpulse.ml.metrics import information_coefficient
    from quantpulse.ml.training import (
        cross_validated_ic,
        suggest_params,
        train_final_model,
    )

    replicate_cfg = replace(cfg, seed=cfg.seed + REPLICATE_SEED_OFFSET)
    study, n_trials = _study(study_name, seed)
    rows: list[dict[str, float]] = []
    for _ in range(n_trials):
        trial = study.ask()
        params = suggest_params(trial, learning_rate_ceiling=ceiling)
        try:
            cv_ic = cross_validated_ic(train_frame, feature_cols, params, cfg, splits)
            _, holdout = train_final_model(panel, feature_cols, params, cfg)
            holdout_ic = information_coefficient(holdout)
            _, replicate = train_final_model(panel, feature_cols, params, replicate_cfg)
            replicate_ic = information_coefficient(replicate)
        except Exception as exc:  # a single bad draw must not end the origin
            logger.warning("trial failed in %s: %s", study_name, exc)
            study.tell(trial, float("-inf"))
            continue
        study.tell(trial, cv_ic)
        rows.append(
            {
                "cv_ic": cv_ic,
                "holdout_ic": holdout_ic,
                "replicate_ic": replicate_ic,
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


def rolling_origins(n_dates: int, cfg: TrainConfig, step_days: int, n_origins: int) -> list[int]:
    """The origin indices every rolling comparison in this package runs on.

    Shared so that two studies asking different questions of the same retrains run on literally
    the same retrains. A result that one study's arm reproduces another's exactly is the strongest
    check available here, and it is only possible when neither study computes its own origins.

    An origin is an index into the sorted dates; the panel at that origin is every date before it.
    The most recent `n_origins` are kept, since those are the retrains closest to production.
    """
    earliest = max(cfg.min_train_dates + cfg.embargo_days, n_dates // 3)
    if n_dates - earliest < step_days * 4:
        raise ValueError(f"panel has {n_dates} dates, too few for origins of {step_days}")
    return list(range(earliest, n_dates, step_days))[-n_origins:]


def tuning_budget(
    engine: object,
    exchange: str = DEFAULT_EXCHANGE,
    cfg: TrainConfig | None = None,
    seeds: tuple[int, ...] = BUDGET_SEEDS,
    step_days: int = 21,
    max_lag: int = 3,
    n_origins: int = 24,
    as_of: str | None = None,
) -> pd.DataFrame:
    """Score selection rules against what production does, across rolling origins.

    `as_of` truncates the panel as `fixed_defaults` does, for the same reason: the origin grid is
    laid from the end of the data, so without it a rerun after any ingest lands on different
    origins and cannot regenerate an earlier run.

    Each origin re-runs the production procedure on the panel truncated at that date, so every
    cell is a retrain that could have happened that week rather than a variation on one window.

    Returns one row per rule. `mean_delta` is the paired holdout-IC difference against the
    production rule, averaged over seeds inside an origin and then over origins.
    """
    from quantpulse.ml.cv import purged_walk_forward_splits
    from quantpulse.ml.fixed_defaults import truncate_panel
    from quantpulse.ml.pipeline import build_dataset
    from quantpulse.ml.training import HOLDOUT_FRACTION, split_by_date

    cfg = cfg or TrainConfig()
    ceiling = get_exchange(exchange).learning_rate_ceiling
    feature_cols = feature_columns_for(exchange)
    frame = truncate_panel(build_dataset(engine, cfg, exchange), as_of)  # type: ignore[arg-type]
    dates = sorted(frame["date"].unique())

    # Origins are spaced by the label horizon rather than by the retrain cadence: a weekly
    # stride would tile the period with holdouts that are nearly the same window, which adds
    # rows without adding evidence.
    origins = rolling_origins(len(dates), cfg, step_days, n_origins)
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
    # Every trial from every study, so the run can be re-interrogated without being repeated.
    trials: list[dict[str, Any]] = []
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
            # Keep every trial, not only the ones a rule selected. The arms compare one fit per
            # cell, which is the weakest thing the run produces; the trials themselves say
            # whether the folds order them in a way that transfers at all, which is the question
            # the arms can only answer indirectly and at far lower power.
            for study_name, rows in studies.items():
                for index, row in enumerate(rows):
                    trials.append(
                        {"study": study_name, "origin": i, "seed": seed, "trial": index, **row}
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
                delta_autocorr=lag1_autocorrelation(deltas),
                mean_learning_rate=sum(lrs[i] for i in shared if i in lrs)
                / max(len([i for i in shared if i in lrs]), 1),
                note=rule.note,
            )
        )

    # --- does the fold score order the holdout at all? ---
    from scipy import stats

    trial_frame = pd.DataFrame(trials)

    def cell_rho(study: str, against: str, subset: str, i: int, seed: int) -> float | None:
        cell = trial_frame[
            (trial_frame["study"] == study)
            & (trial_frame["origin"] == i)
            & (trial_frame["seed"] == seed)
        ]
        if subset == "warmup":
            cell = cell[cell["trial"] < PRODUCTION_STARTUP]
        elif subset == "informed":
            cell = cell[cell["trial"] >= PRODUCTION_STARTUP]
        if len(cell) < 5:
            return None
        rho = stats.spearmanr(cell[against], cell["holdout_ic"]).statistic
        # Degenerate when every trial ties on one side, which is not a correlation of zero.
        return None if rho != rho else float(rho)

    transfers: list[Transfer] = []
    for name, study, against, subset, note in TRANSFERS:
        per: dict[int, float] = {}
        for i in range(len(origins)):
            vals = [r for s in seeds if (r := cell_rho(study, against, subset, i, s)) is not None]
            if vals:
                per[i] = sum(vals) / len(vals)
        if len(per) < 3:
            continue
        series = [per[i] for i in sorted(per)]
        transfers.append(
            Transfer(
                name=name,
                study=study,
                against=against,
                trials=subset,
                mean_rho=sum(series) / len(series),
                std_error=newey_west_se(series, max_lag=max_lag),
                n_origins=len(series),
                n_positive=int(sum(1 for v in series if v > 0)),
                note=note,
            )
        )

    # A correlation with the holdout is capped by how well the holdout correlates with itself, so
    # an observed rho understates the truth by roughly the square root of that reliability.
    # Dividing by it gives a LOWER bound on the real correlation — lower, because the other side
    # of the pair has its own unmeasured unreliability which would only push the truth higher. If
    # even the bound is near zero, the null is not an artefact of a noisy outcome. Aggregated
    # first and corrected second: per-cell reliabilities near zero make the division explode.
    by_name = {t.name: t for t in transfers}
    reliability = by_name[RELIABILITY].mean_rho if RELIABILITY in by_name else float("nan")
    bounds: dict[str, float] = {}
    if reliability == reliability and reliability > 0:
        for t in transfers:
            if t.name != RELIABILITY and t.against == "cv_ic":
                bounds[t.name] = t.mean_rho / math.sqrt(reliability)

    table = pd.DataFrame([r.__dict__ for r in results])
    table.attrs["origins"] = len(origins)
    table.attrs["seeds"] = len(seeds)
    table.attrs["first_origin"] = str(dates[origins[0] - 1])
    table.attrs["last_origin"] = str(dates[origins[-1] - 1])
    # The per-origin series, kept because the summary cannot be re-interrogated later: whether
    # the error width was right, and whether the seeds carried any independent information, are
    # both questions about these columns rather than about the means taken from them. A run that
    # keeps only the summary has to be repeated in full to answer either.
    table.attrs["per_origin"] = pd.DataFrame(
        {
            "origin": [str(dates[origins[i] - 1]) for i in range(len(origins))],
            **{
                rule.name: [per_origin(rule.name, "holdout_ic").get(i) for i in range(len(origins))]
                for rule in RULES
            },
        }
    )
    # How correlated neighbouring origins actually are, rather than a lag width assumed to cover
    # it. Reported for the control's own series and for each arm's differences, because pairing
    # removes the shared market movement and the two can differ a lot.
    table.attrs["control_autocorr"] = lag1_autocorrelation([control[i] for i in sorted(control)])
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
    # Whether averaging over seeds bought anything. If the spread of the origin means is close
    # to the spread of every individual fit, the seeds carried no information the origins did
    # not already have, and a sample counted in fits would have been inflated by the seed count.
    import numpy as np

    all_fits = [
        picked[(CONTROL, i, s)]["holdout_ic"]
        for i in range(len(origins))
        for s in seeds
        if (CONTROL, i, s) in picked
    ]
    # Both guarded on having something to take a spread of. A sample standard deviation of one
    # value is not a small number, it is undefined, and numpy says so by warning and returning a
    # nan that then reads as a measured result.
    origin_means = [control[i] for i in sorted(control)]
    table.attrs["control_origin_sd"] = (
        float(np.std(origin_means, ddof=1)) if len(origin_means) > 1 else float("nan")
    )
    table.attrs["control_fit_sd"] = (
        float(np.std(all_fits, ddof=1)) if len(all_fits) > 1 else float("nan")
    )
    transfer_frame = pd.DataFrame([t.__dict__ for t in transfers])
    if bounds:
        transfer_frame["disattenuated"] = transfer_frame["name"].map(bounds)
    table.attrs["transfer"] = transfer_frame
    table.attrs["reliability"] = reliability
    # The raw trials, so a later question does not need the run repeated. This is the whole
    # measurement; everything else on this table is a summary of it.
    table.attrs["trials"] = trial_frame
    return table
