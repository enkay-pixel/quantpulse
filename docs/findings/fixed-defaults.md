# Can a fixed configuration replace the tuner? (pre-registered 2026-09-28)

**Status: pre-registered, not yet measured.** This page reached `main` before the run started,
following the rule in [How to measure things here](../measurement.md#fix-the-decision-rule-before-the-run-where-the-merge-cannot-erase-it)
that a pre-registration committed to a feature branch is erased by the squash merge.

## Why this is being measured

[The tuning-budget work](tuning-budget.md) found that the tuner's search does no better than random,
that the folds do not order the holdout, and — the reason for both — that refitting identical
parameters with only the seed changed reproduces a trial's holdout score poorly: reliability 0.13
on XJSE and 0.33 on XNYS, so most of the variation the search tries to exploit is the fit's own
randomness.

That **predicts** a fixed configuration should do about as well as a searched one. The prediction
is stated here so that the test can falsify it; nothing is changed on the strength of it.

## The question is non-inferiority

A fixed configuration costs **1** fit per candidate. A tuned one costs **61** — fifteen trials
across four folds, then the chosen parameters fitted once more. A fixed configuration is also
deterministic, which removes the week-to-week parameter churn that the learning-rate collapses
came from. So it does not have to *win* to be worth adopting. It has to not *lose* by an amount that
matters.

That amount is the promotion gate's own margin, `Exchange.ic_promotion_margin`: **0.008 on XJSE,
0.006 on XNYS**, the difference the gate itself treats as luck rather than improvement. It is used
here as a threshold of **practical importance**, not as a noise floor — the statistics come from a
one-sided confidence bound. Borrowing a margin *as a significance test* is what the measurement rules
warn against; asking whether a loss is smaller than the gate would ever act on is a different use,
and the one that matches the decision.

## Arms

| arm | parameters | role |
|---|---|---|
| `tuned` | production's own tuner — `tune_hyperparameters`, 15 trials, default warm-up | **control** |
| `fixed_default` | `DEFAULT_PARAMS`, learning rate held under the market's ceiling | **the candidate** |
| `fixed_center` | the centre of the space the tuner searches | diagnostic only |

The exact configurations, derived by rule before any holdout was read:

| | learning rate | leaves | min data in leaf | feature fraction | L2 |
|---|---|---|---|---|---|
| XJSE `fixed_default` | 0.02 | 31 | 50 | 0.9 | 1.0 |
| XJSE `fixed_center` | 0.00447 | 52 | 110 | 0.75 | 0.1 |
| XNYS `fixed_default` | 0.05 | 31 | 50 | 0.9 | 1.0 |
| XNYS `fixed_center` | 0.01414 | 52 | 110 | 0.75 | 0.1 |

The centre is a geometric midpoint wherever the search is log-scaled (learning rate, L2) and an
arithmetic one elsewhere, read from the same bounds the search reads.

**Neither fixed arm is chosen by result.** Over ten thousand scored trials exist from the earlier
rounds, and picking whichever parameters did well in them would be selecting on the holdout. And
**only `fixed_default` is eligible for adoption**: choosing between the two fixed arms by which
scored better would be the same selection by a shorter route. `fixed_center` answers only whether
the particular fixed point matters.

## Design

- **The control is production**, not a reconstruction: the tuned arm calls the tuner the weekly
  retrain calls. On the shared origins it should reproduce the tuning-budget study's production arm
  **exactly**, cell by cell, and that is checked rather than assumed. A match would also confirm,
  after the fact, that the earlier rounds' production arm was faithful to production.
- The same origins as the tuning-budget work — XJSE 20, XNYS 36 — through the shared
  `rolling_origins`, and the same two seeds.
- Paired on origin and seed, seeds averaged within an origin, Newey-West across origins at
  `max_lag = 3`.
- **The floor for a paired difference is measured correctly this time**: how far the
  arm-minus-control difference moves when only the seed changes, inside an origin. The
  tuning-budget study's second round compared paired differences against the unpaired spread of a
  single arm, which double-counts the seed that pairing exists to cancel.

## Decision rule, fixed in advance

**0. Comparability first.** If the tuned arm does not reproduce the tuning-budget production arm cell
by cell, the run is not comparable to the earlier rounds and is reported that way. The comparison
*within* the run still stands, because both of its arms were fitted on identical panels.

Then, **per market**:

1. **If `fixed_default`'s one-sided 95% lower bound on (fixed − tuned) is above −margin**, it is
   non-inferior, and replacing the tuner on that market is **supported on this evidence, subject to
   a live check**. Nothing is changed in production from this run alone.
2. **Otherwise**, tuning is earning its cost on that market, and it stays.
3. **A point estimate near zero with a wide bound is not a pass.** It is an unresolved comparison, and
   is reported as one rather than as equivalence.

`fixed_center` feeds no decision. If it and `fixed_default` differ by more than the paired seed
spread, the report says the choice of fixed point matters — which would weaken any case for
"the defaults" as a single thing.

## Disclosures

- **XJSE's `fixed_default` sits exactly at the ceiling, 0.02**, and that ceiling was itself set on
  holdout IC by [the learning-rate experiment](learning-rate-ceiling.md), over panels that overlap
  these. So that arm is not wholly blind. The tuned arm searches under the same ceiling, so the
  dependence is shared by both arms and does not bias the comparison between them.
- The cost figure of 61 fits corrects one given in conversation while this was being designed,
  which said 75. That was the tuning-budget *experiment's* cost per trial, which also scored every
  trial on the holdout; production never does.
- Only holdout IC is compared. The gate's drawdown floor and Sharpe veto are not, so a
  non-inferiority result here is about the metric the gate decides on, not every check it runs.

## Results

Not yet measured.
