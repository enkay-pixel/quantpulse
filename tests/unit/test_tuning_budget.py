"""Guards on the tuning-budget comparison.

The arms differ only in what a selection rule is allowed to look at, so the two things worth
pinning are that a rule really is restricted to its own field, and that the samplers agree for
the whole warm-up. The second is what makes every contrast paired trial by trial rather than two
separate runs of the same recipe, and it is a property of the sampler library rather than of this
code — so an upgrade could remove it without anything here failing.
"""

import math

import optuna
import pytest

from quantpulse.ml.metrics import lag1_autocorrelation
from quantpulse.ml.training import suggest_params
from quantpulse.ml.tuning_budget import (
    CONTROL,
    LONG_TRIALS,
    PRODUCTION_STARTUP,
    PRODUCTION_TRIALS,
    RULES,
    SHORT_STARTUP,
    Rule,
    _pick,
    _study,
)

#: The keys the tuner actually searches. `suggest_params` also carries the fixed defaults, some
#: of which are strings, so a comparison of draws has to name the searched ones.
SEARCHED = ("learning_rate", "num_leaves", "min_data_in_leaf", "feature_fraction", "lambda_l2")


def _trials() -> list[dict[str, float]]:
    """Trials whose cross-validated and holdout orderings disagree, so a rule reading the wrong
    field cannot accidentally pick the right trial."""
    return [
        {"cv_ic": 0.01, "holdout_ic": 0.09, "learning_rate": 0.001},
        {"cv_ic": 0.05, "holdout_ic": 0.02, "learning_rate": 0.002},
        {"cv_ic": 0.03, "holdout_ic": 0.04, "learning_rate": 0.003},
        {"cv_ic": 0.09, "holdout_ic": 0.01, "learning_rate": 0.004},
    ]


def test_pick_orders_on_the_field_the_rule_is_allowed_to_see() -> None:
    rows = _trials()
    on_cv = Rule("cv", "tpe10", 4, "cv_ic", "")
    on_holdout = Rule("oracle", "tpe10", 4, "holdout_ic", "")
    assert _pick(rows, on_cv, arbitrary_index=0)["cv_ic"] == 0.09
    assert _pick(rows, on_holdout, arbitrary_index=0)["holdout_ic"] == 0.09
    # The two disagree, which is the whole reason the oracle is reported separately.
    assert _pick(rows, on_cv, arbitrary_index=0) is not _pick(rows, on_holdout, arbitrary_index=0)


def test_a_rule_that_sees_nothing_ignores_both_metrics() -> None:
    """The signal-free control must not improve when the metrics do.

    A positional pick is the only kind that cannot be selecting on the data, so if reordering
    the trials changed what it returned it would be quietly using them.
    """
    rows = _trials()
    blind = Rule("arbitrary", "tpe10", 4, "nothing", "")
    picked = _pick(rows, blind, arbitrary_index=2)
    assert picked is rows[2]
    worsened = [dict(r, cv_ic=-r["cv_ic"], holdout_ic=-r["holdout_ic"]) for r in rows]
    assert _pick(worsened, blind, arbitrary_index=2)["learning_rate"] == rows[2]["learning_rate"]


def test_pick_is_confined_to_its_own_budget() -> None:
    """An arm must not see trials a shorter budget would never have run."""
    rows = _trials()
    short = Rule("short", "tpe10", 2, "cv_ic", "")
    assert _pick(rows, short, arbitrary_index=0)["cv_ic"] == 0.05
    with pytest.raises(ValueError):
        _pick([], short, arbitrary_index=0)


def test_the_long_tpe_study_opens_with_the_production_one() -> None:
    """Sharing the opening is what pairs the budget arms instead of comparing two runs."""
    study, n_trials = _study("tpe10", seed=42)
    assert n_trials == LONG_TRIALS
    assert study.sampler._n_startup_trials == PRODUCTION_STARTUP  # type: ignore[attr-defined]
    short_study, short_trials = _study("tpe5", seed=42)
    assert short_trials == PRODUCTION_TRIALS
    assert short_study.sampler._n_startup_trials == SHORT_STARTUP  # type: ignore[attr-defined]


def test_warm_up_draws_match_an_independent_sampler_at_the_same_seed() -> None:
    """The claim that every contrast is paired trial by trial rests on this.

    A TPE sampler's warm-up is an independent draw, and at a shared seed it is the *same*
    independent draw, so the learning and no-learning arms agree until the objective starts
    being used. Nothing in this repository enforces that — it is sampler behaviour — so it is
    asserted here rather than assumed in a docstring.
    """
    optuna.logging.set_verbosity(optuna.logging.CRITICAL)

    def draws(sampler: optuna.samplers.BaseSampler, n: int) -> list[tuple[float, ...]]:
        study = optuna.create_study(direction="maximize", sampler=sampler)
        out = []
        for _ in range(n):
            trial = study.ask()
            params = suggest_params(trial, learning_rate_ceiling=0.02)
            study.tell(trial, 0.0)
            # Only the searched keys: the rest are fixed defaults, some of them strings.
            out.append(tuple(round(float(params[k]), 12) for k in SEARCHED))
        return out

    tpe = draws(optuna.samplers.TPESampler(seed=42, n_startup_trials=PRODUCTION_STARTUP), 12)
    rand = draws(optuna.samplers.RandomSampler(seed=42), 12)
    assert tpe[:PRODUCTION_STARTUP] == rand[:PRODUCTION_STARTUP]
    # And they must diverge once TPE starts using the objective, or the "learning" arm is not
    # learning and the comparison has no treatment in it at all.
    assert tpe[PRODUCTION_STARTUP:] != rand[PRODUCTION_STARTUP:]


def test_the_control_is_one_of_the_rules_and_is_scored_on_the_folds() -> None:
    by_name = {r.name: r for r in RULES}
    assert CONTROL in by_name
    assert by_name[CONTROL].sees == "cv_ic"
    assert by_name[CONTROL].n_trials == PRODUCTION_TRIALS
    # Exactly one arm may read the holdout, and it must be the declared bias bound.
    reads_holdout = [r.name for r in RULES if r.sees == "holdout_ic"]
    assert reads_holdout == ["oracle_40"]
    # At least one arm must be unable to use the data, or there is no floor for the rest.
    assert any(r.sees == "nothing" for r in RULES)


def test_autocorrelation_separates_a_drifting_series_from_an_alternating_one() -> None:
    assert lag1_autocorrelation([0.0, 1.0, 2.0, 3.0, 4.0, 5.0]) > 0.4
    assert lag1_autocorrelation([0.0, 1.0, 0.0, 1.0, 0.0, 1.0]) < -0.5
    # Too short to estimate, and a flat series has no variance to divide by. Both must say "not
    # measured" rather than returning a number that reads as independence.
    assert math.isnan(lag1_autocorrelation([1.0, 2.0]))
    assert math.isnan(lag1_autocorrelation([1.0, 1.0, 1.0, 1.0]))
