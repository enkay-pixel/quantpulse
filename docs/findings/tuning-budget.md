# Does the tuner's budget buy anything? (2026-09-26)

**Status: pre-registered, not yet measured.** This section was written and committed before the
run started, so that the decision rule could not be chosen after seeing the numbers. Results
follow underneath once they exist.

## Why this is being measured

The weekly retrain runs Optuna for 15 trials. Optuna's TPE sampler draws its first
`n_startup_trials` — 10 by default, and the default is what is in use — without reference to the
objective. So **five of the fifteen trials are the search; the other ten are a fixed grid**
determined by the seed and the bounds, and since the seed never changes, the same ten points are
re-drawn at every retrain on every market.

Replaying that grid against every candidate the project has produced:

| | |
|---|---|
| candidates that are an exact match to one of the ten warm-up draws | **13 of 27** |
| XJSE v1 → v8 | all warm-up draw #2, `lr 0.00112` — nine consecutive retrains, same point |
| XJSE v12, v13 (the two under the learning-rate ceiling) | warm-up draw #2 again |
| XNYS v7, v11, v14 | warm-up draw #1 |

The match is on all five parameters to nine decimal places, so it is identity rather than
coincidence. Two consequences motivate the measurement:

- **The live JSE champion (v3) was never tuned.** Its parameters are the second draw of a seeded
  sampler. Ten subsequent retrains have been rejected against it, several of them re-drawing the
  same point, so the gate has largely been comparing a model with itself.
- The per-market learning-rate ceiling works partly by *rescaling this fixed grid* into the band
  that historically held up, not by constraining a search. The measurement in
  [learning-rate-ceiling.md](learning-rate-ceiling.md) stands; the mechanism given there does not.

## The question, and why it is not "more trials"

The obvious move is a bigger budget. The prior question is whether choosing the best
cross-validated trial beats not choosing at all — because if it does not, the budget is
irrelevant and a larger one only costs more. This project has already found one selection rule
that looked valuable and was measuring the bias of a maximum rather than any skill of its own
(the early-stopping round count), so the control matters more than the treatment here.

## Arms

All arms are **selection rules applied to the same recorded trials**, and every trial is scored
on the gate's holdout as well as on the folds. Rules order on cross-validated IC only.

| arm | trials | sees | what it asks |
|---|---|---|---|
| `prod` | TPE, 15, warm-up 10 | CV IC | the control — what production does today |
| `tpe10_40` | TPE, 40, warm-up 10 | CV IC | buy informed trials by paying for them |
| `tpe5_15` | TPE, 15, warm-up 5 | CV IC | buy informed trials by drawing fewer blind ones |
| `rand_15` | independent, 15 | CV IC | no learning, production budget |
| `rand_40` | independent, 40 | CV IC | no learning, long budget |
| `arbitrary` | TPE, 15, warm-up 10 | nothing | positional pick — no selection at all |
| `oracle_40` | TPE, 40, warm-up 10 | **holdout IC** | bias bound only, never a target |

The arms are paired trial by trial, not merely seed by seed: a sampler's draws are a single
seeded stream, so the long TPE study's opening *is* the production study, and a TPE sampler's
warm-up draws are the independent sampler's draws at the same seed. The learning and no-learning
arms therefore agree for the whole warm-up and diverge only where the objective starts being
used, which is exactly the contrast of interest.

## Design

- One origin every 21 trading days — the label horizon, rather than the weekly retrain cadence,
  because a weekly stride tiles the period with holdouts that are nearly the same window.
- Each origin re-runs the production procedure on the panel truncated at that date: tuning sees
  only the pre-holdout part, and the holdout is carved off the end exactly as the gate does it.
- Seeds averaged **within** an origin before anything is pooled. The origin is the unit of
  generalisation; re-drawing the fit does not re-draw the market.
- Standard error across origins via Newey-West, `max_lag = 3`: successive holdouts overlap
  heavily and a forward label straddles the origin that follows it.
- Markets analysed separately. The learning-rate work already showed they need opposite answers.

## Decision rule, fixed in advance

**Gate first.** If `rand_40` is not worse than `tpe10_40`, or `rand_15` is not worse than
`prod`, then the informed portion of the search carries no information at this budget and **no
trial-count change is adopted**, whatever the other arms show. If `arbitrary` matches `prod`,
the same conclusion follows more strongly, and the finding is about the sampler and the seed
rather than about the budget.

**Otherwise**, an arm replaces production only if all four hold on that market:

1. mean paired difference against `prod` is positive;
2. |t| = |mean / Newey-West SE| ≥ 2;
3. the sign repeats in more than 60% of origins;
4. the mean difference exceeds the control's own seed spread measured on the same origins — the
   floor for this procedure, measured here rather than borrowed from the promotion margin.

`oracle_40` is reported only to bound how much of any arm's apparent skill is the upward bias of
a maximum over noisy evaluations.

A mean that is stable while the error is still wide is reported as **not resolved at this sample
size, with what it would take** — never as no effect.

## Results

Not yet measured.
