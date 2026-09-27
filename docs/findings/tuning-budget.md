# Does the tuner's budget buy anything? (2026-09-26)

Everything above the Results heading was written and **committed before the run started**, so the
decision rule could not be chosen after seeing the numbers. That is checkable, but not from
`main`: the two commits were squashed into one on merge, so the separation survives only in
[PR #87](https://github.com/enkay-pixel/quantpulse/pull/87), where the pre-registration commit
and the results commit are still listed apart.

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

**Both projections were withdrawn on 2026-09-27.** XNYS was run at 36 origins and the comparison
still did not resolve, because the effect flipped sign instead of holding while the error
shrank — see "Three corrections this round forced" below. An arithmetic like this one assumes a
stable effect, and that assumption is the thing being tested.

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

## Second round: does a fold score order the holdout at all? (pre-registered 2026-09-27)

**Status: pre-registered, not yet measured.** Written and committed before the second run started.

The first round left one question open and answered it only indirectly. `prod` against
`arbitrary` compares **one selected fit per cell**, which is the weakest thing the run produces —
hence 20 origins resolving neither market. The same trials answer a sharper question at far higher
power: across the forty trials of a single study, does a better fold score go with a better
holdout score? If it does not, then no rule ordering on fold IC can work, and the arms' failure to
separate is explained rather than needing more origins.

The first run threw those trials away. It now keeps them.

### Measure

Spearman rank correlation — rank, because selection is an argmax — between fold IC and holdout IC
across the trials **within** each (origin, seed) cell. Seeds averaged within an origin, then mean
and Newey-West across origins at `max_lag = 3`, as before. Reported over the long TPE study's
forty trials, and split into the blind warm-up draws and the informed trials, because the informed
ones are drawn toward the fold optimum and whether that changes their transfer is the question
restated.

### The control that makes a null readable

A correlation near zero has two explanations that look identical: the fold score genuinely does
not order the holdout, or the IC estimates are too noisy to correlate with anything. So the same
cells are also correlated against the **learning rate**, which is already known to matter — high
rates win the folds and lose the holdout, and the sign should come out negative.

**If the control does not resolve, this run cannot answer the question and will be reported that
way.** A null on the fold score is only informative alongside a control that resolved on the same
data.

### Second-round decision rule, fixed in advance

1. If the learning-rate control resolves (|t| ≥ 2) and the fold-score correlation does not
   (|t| < 2), then **the folds do not order the holdout**: no selection rule on fold IC can work,
   the first round's unresolved arm comparison is explained, and the next thing to change is the
   objective rather than the budget or the sample size.
2. If the fold-score correlation resolves positive, selection is doing something real and the
   first round was simply underpowered to see it in a single selected fit — in which case the arm
   comparison is worth carrying to the sample size named above.
3. If neither resolves, the run says nothing and is reported as such.

Alongside this, XNYS runs at the **36 origins** the first round said its `prod` against
`arbitrary` comparison would need, under the criteria already fixed above. XJSE stays at 20: its
comparison needs about 300 origins against a panel that holds at most 95, so more origins there
buy nothing.

### Disclosure: the control is structurally weak on XJSE

A three-origin smoke test was run first, to check the new aggregation executed at all. It did, and
it correctly refused to conclude anything. It also made a design flaw plain, and since directional
numbers were seen before the full run, that is recorded here rather than presented afterwards as
foresight.

**The learning-rate control cannot work well on XJSE, by construction.** The ceiling confines the
rate to 0.001–0.02, while the effect the control relies on — high rates winning the folds and
losing the holdout — lives at 0.15–0.19. The ceiling removed the variance the control needs. On
XNYS, where the ceiling is 0.2, the range is intact and the control should resolve.

So the primary conclusion will rest on XNYS. On XJSE a null would be unreadable, and that is a
limitation of this design rather than a result. **The decision rule above is not changed** — no
threshold is being moved after seeing data, and the smoke-test numbers are used for nothing except
this disclosure. What was seen: the fold correlation came out positive overall and near zero over
the informed trials alone, on three origins, which is far too few to mean anything and is exactly
why the run is being done at twenty and thirty-six.

## Second-round results

Measured 2026-09-27, 6h40m. XJSE at 20 origins (2024-12-31 → 2026-08-05), XNYS at 36
(2023-09-19 → 2026-08-25), 2 seeds, every trial retained.

**XJSE reproduced the first round exactly** — every arm figure identical to three weeks of
numbers taken a day earlier, same seeds and origins. Worth stating because nothing else in this
document is a replication.

### Does a fold score order the holdout?

| | XJSE rho (t) | XNYS rho (t) |
|---|---|---|
| fold IC vs holdout, all 40 trials | +0.016 (+0.28) | +0.053 (+0.69) |
| …warm-up draws only | −0.077 (−1.05) | +0.036 (+0.65) |
| …informed trials only | −0.007 (−0.14) | +0.067 (+1.20) |
| …independent sampler's trials | +0.012 (+0.25) | +0.073 (+1.34) |
| **learning rate vs holdout (control)** | **+0.051 (+2.14)** | **−0.087 (−1.76)** |

**The question is not settled, and the rule fixed in advance is what says so.**

- **XNYS falls to rule 3.** The control does not resolve at |t| 1.76, so neither does anything
  else, and the run says nothing. This was the market the conclusion was supposed to rest on,
  because it is the one whose learning-rate range the ceiling leaves intact.
- **XJSE satisfies rule 1 by the letter** — control resolves at |t| 2.14, fold correlation does
  not at |t| 0.28 — so on that market the folds do not order the holdout. But **the control
  resolved with the sign opposite to the one predicted**. Positive, not negative. Within the
  capped band a higher rate scoring better is consistent with
  [round-count.md](round-count.md), where lowering the rate cost XJSE 66% of peak IC, but that
  reconciliation is offered after the fact. A control that contradicts its own prediction still
  shows holdout IC is rankable by something, which is its job; it is weaker evidence than one
  that had matched.

So the fold-score correlation is near zero on both markets, +0.016 and +0.053, and **this run
cannot establish that the null is real rather than the cells being too noisy to rank.** Reported
as unresolved, not as a null.

### The gate conclusion strengthened

At 36 origins on XNYS, against the first round's 20:

| arm | vs `prod` | t | favours |
|---|---|---|---|
| `tpe10_40` | +0.0051 | +1.79 | 23/36 |
| `tpe5_15` | +0.0094 | +2.84 | 26/36 |
| `rand_15` | +0.0088 | +2.24 | 26/36 |
| **`rand_40`** | **+0.0101** | **+4.64** | **28/36** |
| `arbitrary` | +0.0028 | +0.54 | 17/36 |
| `oracle_40` | +0.0345 | +7.79 | 36/36 |

Random search beats production TPE at t +4.64, up from +2.50, on 28 of 36 origins, and every
no-learning and short-warm-up arm beats it. The first round's gate holds and sharpens.

### Three corrections this round forced

**The first round's sample-size projection was wrong.** It said `prod` against `arbitrary` would
resolve on XNYS at about 36 origins. At 36 it still does not, and the effect did not grow — it
**flipped sign**, from −0.0051 (t −1.50) to +0.0028 (t +0.54). The projection scaled the error
while holding the effect fixed, and the effect was never fixed. That is this page's own warning
about a mean that moves, applied to its own arithmetic.

One qualification on the flip: the 16 added origins are all *earlier* (2023-09 to 2025-01), so
the two runs cover different periods rather than nested ones. Noise and a period effect are not
separable here.

**Criterion 4 was mis-specified.** It required a *paired* difference to exceed the *unpaired*
seed spread. Pairing cancels the seed — that is why it is done — so the floor should have been
the spread of the paired difference under seed re-draws, which was never measured. This changes
no conclusion, because the gate blocks adoption on its own, but the criterion should not be
applied as though it were sound.

**Pairing is now demonstrated rather than asserted.** Per-origin holdout IC autocorrelates at
0.89 on XJSE and 0.73 on XNYS, so these origins are nowhere near independent and a test on
*levels* at lag 3 would badly under-correct. The paired differences autocorrelate at 0.01 to
0.40. And on both markets the spread of origin means is within a few percent of the spread of
every individual fit (0.054 against 0.055; 0.036 against 0.039), confirming directly that the
seeds carry no information the origins do not — counting fits as samples would have inflated the
sample twofold.

Every trial is saved this run (3,420 rows for XNYS), so the next question will not need it
repeated. That omission is what made this round necessary.

## Third round: is the holdout score reproducible at all? (pre-registered 2026-09-27)

**Status: pre-registered, not yet measured.** Written and committed before the third run started.

The second round could not read its own null, because the only control it had — the learning rate
— is compressed by the ceiling on XJSE and fell short of resolution on XNYS. This round replaces
it with a control that depends on no parameter the pipeline caps.

### The control

Refit **the same parameters** at a second seed, holding panel, folds and holdout fixed, and
correlate the two holdout scores across the trials of a cell. That measures how reproducible a
holdout IC is when nothing changes but the fit's randomness.

It is the right control because **a measure cannot correlate with anything more strongly than it
correlates with itself.** So this reliability is a ceiling on every other correlation in the
table, and it is the quantity that tells a real null apart from an outcome too noisy to correlate
with anything.

**Correcting a cost claim made in the second round's write-up:** that round said this control
"doubles the cost of a run". It does not. Only the *final* fit is repeated — the folds are not
re-run, because the parameters are not being re-chosen — so it adds one fit against the six a
trial already pays, about **+17%**, not +100%. The earlier figure was wrong and made the control
look more expensive than it is.

### Attenuation, and why the correction is a bound

An observed correlation is deflated by unreliability on both sides, by roughly the square root of
each side's reliability. Dividing the observed fold correlation by the square root of the measured
holdout reliability therefore gives a **lower bound** on the true correlation — lower, because the
fold score has its own unmeasured unreliability which would only push the truth further up. If
even that bound is near zero, the null is not an artefact of a noisy outcome.

The correction is applied to the pooled means, not per cell: a per-cell reliability near zero
makes the division explode.

### Third-round decision rule, fixed in advance

1. **If reliability does not resolve (|t| < 2) or is not positive**, then a single fit's holdout IC
   is not a reproducible quantity at trial level. The fold question is then unanswerable by
   correlation at this granularity — and, more seriously, **the arm comparisons in the first two
   rounds are largely reading fit noise**, which would have to be said plainly.
2. **If reliability resolves positive and the disattenuated fold correlation is still below 0.2 in
   magnitude**, the null is real: no rule selecting on fold IC can work, and the tuner's objective
   is the thing to change.
3. **If reliability resolves positive and the disattenuated fold correlation is 0.2 or above**,
   then the folds do carry transferable information that the arms were too weak to see, and the
   selection rules deserve re-examination rather than replacement.

The learning-rate correlation is kept as a secondary control, reported with the caveat that a
market whose ceiling compresses its range cannot supply one.

Run at the same origins as the second round — XJSE 20, XNYS 36 — so the fold correlations being
corrected are the ones already measured rather than a fresh draw.

## What follows

Nothing changes in the tuner as a result of this. The measured position is that the search could
be replaced by its own warm-up, or by fixed sensible defaults, **at no cost detectable against
the seed** — which would make retrains cheaper and deterministic, and is worth testing as its own
change rather than assumed here. The JSE promotion stall is not a tuning-budget problem.

What the second round changes is which question is open. "Do the folds order the holdout" is the
right question and **this design cannot answer it**, because the only control available for it —
the learning rate — is destroyed by the ceiling on one market and falls short of resolution on
the other. Answering it needs a control that does not depend on a parameter the pipeline caps.
The obvious candidate is refitting the same parameters at a second seed and correlating the two
holdout scores: that measures whether holdout IC is a reproducible quantity at all, which is
what a null on the fold score needs in order to mean anything. It doubles the cost of a run,
which is why it was not done here, and it is the next thing to build rather than another sweep
of the budget.
