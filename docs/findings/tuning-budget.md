# Does the tuner's budget buy anything? (2026-09-26)

Everything above the Results heading was written and **committed before the run started**, so the
decision rule could not be chosen after seeing the numbers. The commit that fixed it is separate
from the one that added the results.

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

Measured 2026-09-26. 20 origins per market, 2 seeds, 21-day stride, ~5.3 hours in a throwaway
container. XJSE origins end 2024-12-31 → 2026-08-05; XNYS 2025-01-22 → 2026-08-25.

Holdout IC of the selected parameters, and the paired difference against `prod`:

### XJSE — seed spread 0.0186

| arm | holdout IC | vs `prod` | SE | t | favours arm |
|---|---|---|---|---|---|
| `prod` | 0.0353 | — | — | — | — |
| `tpe10_40` | 0.0331 | −0.0021 | 0.0029 | −0.75 | 7/20 |
| `tpe5_15` | 0.0312 | −0.0041 | 0.0045 | −0.92 | 6/20 |
| `rand_15` | 0.0363 | **+0.0010** | 0.0034 | +0.31 | 9/20 |
| `rand_40` | 0.0375 | **+0.0022** | 0.0032 | +0.69 | 10/20 |
| `arbitrary` | 0.0333 | −0.0020 | 0.0039 | −0.51 | 5/20 |
| `oracle_40` | 0.0797 | +0.0444 | 0.0061 | +7.23 | 20/20 |

### XNYS — seed spread 0.0211

| arm | holdout IC | vs `prod` | SE | t | favours arm |
|---|---|---|---|---|---|
| `prod` | 0.0326 | — | — | — | — |
| `tpe10_40` | 0.0336 | +0.0010 | 0.0022 | +0.44 | 12/20 |
| `tpe5_15` | 0.0388 | +0.0062 | 0.0030 | +2.06 | 13/20 |
| `rand_15` | 0.0393 | **+0.0067** | 0.0046 | +1.46 | 13/20 |
| `rand_40` | 0.0390 | **+0.0063** | 0.0025 | +2.50 | 14/20 |
| `arbitrary` | 0.0275 | −0.0051 | 0.0034 | −1.50 | 9/20 |
| `oracle_40` | 0.0588 | +0.0262 | 0.0025 | +10.54 | 20/20 |

## The gate trips on both markets

`rand_40` beats `tpe10_40` on both markets — +0.0022 against −0.0021 on XJSE, +0.0063 against
+0.0010 on XNYS — and `rand_15` is not worse than `prod` on either. **Removing the learning
entirely does as well or better than keeping it.** By the rule fixed in advance, no trial-count
change is adopted.

Note what that does to the only arm that looked like a winner. `tpe5_15` on XNYS reaches t +2.06
and would have cleared criteria 1 to 3. It fails criterion 4, and it fails the gate: `rand_15`
does the same thing slightly better without consulting the objective at all. Shortening the
warm-up did not buy informed trials worth having; it bought different blind ones.

## Everything is smaller than the seed

The largest effect anywhere in the two tables is 0.0067. Changing only the seed moves the same
quantity by 0.0186 on XJSE and 0.0211 on XNYS. Every arm difference is therefore **an order of
magnitude below its own noise floor**, measured under this procedure rather than borrowed — which
by this project's standing rule makes the comparison among the CV-based rules underpowered, not a
finding about them.

The gate above does not depend on that, because it is a "not worse" test decided on point
estimates and answered in the same direction on both markets.

## What the oracle says, and what it does not

`oracle_40` beats every rule by a wide margin on 20 of 20 origins on both markets — on XJSE it
more than doubles the production arm, 0.0797 against 0.0353. Read carefully, that is not headroom
anyone can claim. Since `prod`, `rand_15`, `rand_40` and `arbitrary` all sit within noise of each
other, the oracle's margin is almost entirely the upward bias of a maximum over noisy
evaluations, exactly as it was for the early-stopping round count in
[round-count.md](round-count.md).

What it does establish is that the 40 trials of a study *contain* parameter sets scoring 0.06 to
0.08 on the holdout, and that **no rule ordering on cross-validated IC finds them**. The tuner's
own cross-validation does not rank trials in a way that transfers. That is the same defect
already recorded for the inner-validation split, now shown one level up: neither the split that
picks the tree count nor the folds that pick the hyperparameters carries information about the
holdout.

## A mechanism, from the learning rates

The mean selected learning rate separates the arms in a way the IC does not:

| market | `prod` | `rand_40` |
|---|---|---|
| XJSE (ceiling 0.02) | 0.0063 | 0.0085 |
| XNYS (ceiling 0.2) | **0.0403** | **0.0151** |

On XNYS, where nothing caps it, the informed trials pull the selected learning rate to nearly
three times what blind draws pick — and the high-rate regime is precisely what collapsed
candidates to IC ~0.006 in
[learning-rate-ceiling.md](learning-rate-ceiling.md). So the two findings are one finding: the
tuner's folds prefer high learning rates, the holdout does not, and the informed portion of the
search is the part doing the pulling. The per-market ceiling suppresses the symptom on XJSE. On
XNYS the same pull is visible and uncapped.

## Not resolved, and what it would take

Whether selecting on the folds beats **not selecting at all** — `prod` against `arbitrary` — is
the one question here worth resolving, and 20 origins does not resolve it. The sign is right on
both markets and neither reaches t 2.

Holding the effect and scaling the error as the square root of the sample:

- **XNYS** needs about **36 origins** (from 0.0051 at SE 0.0034). That is roughly 9 hours of
  compute, so it is reachable.
- **XJSE** needs about **300 origins** (from 0.0020 at SE 0.0039). The panel holds at most ~95
  origins at this stride, so on this market the question **cannot be resolved with the data that
  exists**, and should be reported that way rather than as a null.

## Caveats

- **The per-origin series was not retained on this run**, so the autocorrelation between
  neighbouring origins is unmeasured and the Newey-West lag of 3 is an assumption rather than a
  fitted choice. The module now keeps the series and reports the autocorrelation, so a re-run
  answers it. The conclusions above rest on point estimates and on the seed floor, neither of
  which depends on the error width.
- Two seeds. Enough to measure a floor and to quieten a cell, not enough to make one tight.
- `arbitrary` takes a single positional trial per cell rather than averaging over many random
  picks, so it carries more noise than the CV-based arms and its comparison is the weakest here.
- Successive holdouts overlap heavily by construction — the production holdout is ~315 days
  against a 21-day stride — so the 20 origins are nowhere near 20 independent windows.
- `oracle_40` reads the holdout. It is a bias bound and never a target; nothing here proposes
  selecting on it.

## What follows

Nothing changes in the tuner as a result of this. The measured position is that the search could
be replaced by its own warm-up, or by fixed sensible defaults, **at no cost detectable against
the seed** — which would make retrains cheaper and deterministic, and is worth testing as its own
change rather than assumed here. The JSE promotion stall is not a tuning-budget problem, and the
next thing worth measuring is the objective the folds compute, not how many times they are run.
