# A per-market learning-rate ceiling (2026-09-17)

**In short:** In September new models got worse because the tuner picked settings that looked good
in its own checks and failed on new data. Capping one setting fixed it in Johannesburg but not New
York, so the cap applies there only. London, measured the same way when it joined, needs the cap too.
Frankfurt, Paris, Zurich and Amsterdam, measured on 2026-10-28, do not: the cap removes too few of
their failures, so they keep the default.

Candidates on both markets looked to be degrading together through September. They were not,
and the markets turned out to need opposite answers. This records how that was established and
why XJSE now searches learning rates only up to 0.02 while XNYS keeps 0.2.

## What looked like decay

Three weekly retrains in a row scored worse on the promotion holdout:

| market | candidate | holdout IC | momentum IC |
|---|---|---|---|
| XJSE | v9 → v10 → v11 | 0.0757 → 0.0074 → 0.0056 | 0.1010 → 0.0930 → 0.0837 |
| XNYS | v10 → v11 → v12 | 0.0641 → 0.0455 → 0.0074 | 0.0201 → 0.0208 → 0.0224 |

It was not the market. Successive training panels overlap by about 99.8% (each adds a week to
data from 2018-04-04) and successive holdouts by about 98%, and the momentum baseline scored on
those holdouts barely moves. The data being judged was nearly unchanged; the models were not.

## What it was: the tuned learning rate

Every candidate that collapsed had been tuned to a high learning rate, and in production every
candidate before September had been tuned low:

| candidates | learning rate | outcome |
|---|---|---|
| 20 before September, both markets | 0.001–0.018 | all held up (mean IC about 0.06) |
| XJSE v10, v11 and XNYS v12 | 0.15–0.19 | all collapsed (IC about 0.006) |

On a single fixed panel and holdout, swapping in the high-rate parameters lowers holdout IC, so
this is not a correlation with harder weeks. The signature is overfitting of the tuner's own
folds: the high-rate parameters score **better** on Optuna's cross-validation and **worse** on
the holdout.

## What it was not

**Not the tuning-leak fix.** The leak (development-history incident 33) was fixed days before
the first collapse, and on the current panel removing it did flip XJSE into the high-rate
regime on all three seeds tried. But rebuilding the exact panels production trained on — holdout
end dates matching the recorded ones — reproduced none of the three high-rate choices, with the
leak or without it. On the current panel the fix also pushed XNYS's rate *down*. It is one more
perturbation to an unstable tuner, not the cause.

**Not reproducible, and that is informative.** Production tunes at seed 42 and nothing varies
it, and no training, feature or pipeline code changed between those retrains and the rebuild.
Same code, seed and panel dates gave a different result, which leaves the stored history itself
as what moved; which data changed was not identified. The seeded sampler turns shifts that
small into learning rates two orders of magnitude apart, so a single weekly tuning is closer to
a draw than a measurement.

## Testing a ceiling

Decided before running: a ceiling works if it clearly lowers the collapse rate **and** its
paired IC change against the current ceiling is not significantly negative. A collapse is
holdout IC below 0.02 — under every one of the twenty low-rate candidates, and well above the
three collapses.

Six panels rolling back 63 trading days, three seeds (42, 7, 123), ceilings of 0.2, 0.06 and
0.02, per market. Every comparison is paired on market, panel, seed and holdout; seeds are
averaged within a panel before any error is taken across panels. The capped tuner was first
checked to reproduce production's own tuner exactly at the current ceiling.

| market | ceiling | collapses | mean holdout IC | paired vs 0.2 |
|---|---|---|---|---|
| XJSE | 0.2 | 6/18 | 0.0303 | — |
| XJSE | 0.06 | 5/18 | 0.0467 | +0.0164 (t +2.04), 4/6 panels |
| XJSE | **0.02** | **3/18** | **0.0519** | **+0.0215 (t +2.63), 5/6 panels** |
| XNYS | 0.2 | 3/18 | 0.0453 | — |
| XNYS | 0.06 | 5/18 | 0.0407 | −0.0046 (t −0.92) |
| XNYS | 0.02 | 4/18 | 0.0416 | −0.0037 (t −1.19) |

**XJSE passes.** Uncapped, the tuner went above 0.02 in 14 of 18 runs, so the ceiling has work
to do. As it tightens, cross-validation IC falls (0.050 → 0.041) while holdout IC rises
(0.030 → 0.052) — the overfitting signature, reversed.

**XNYS fails.** Uncapped, the tuner went above 0.06 in only 3 of 18 runs, so there is little to
remove, and XNYS candidates collapse at low rates too: 4 of 18 at the 0.02 ceiling.

## How far to trust it

- **The t-statistics are optimistic.** Panels share most of their holdout (63-day stride
  against roughly 300 days), so they are not independent. The XJSE direction is robust
  regardless: 5 of 6 panels improve, and dropping the largest leaves +0.016 with 4 of 5.
- **Collapses halving on XJSE is weak evidence alone** at 18 runs a side. The IC change is the
  stronger evidence.
- **This is the gate's holdout, not live returns.**
- **It will not end the JSE promotion stall by itself.** Capped candidates average 0.052 IC,
  and the momentum competitor has recently scored 0.084–0.101 on the same holdouts.

## What the ceiling actually does (corrected 2026-09-27)

The measurements above stand. The mechanism implied by the phrase "searches learning rates only
up to 0.02" does not, and [tuning-budget.md](tuning-budget.md) is why.

Two thirds of the tuner's trials are not a search. Optuna's TPE sampler draws its first ten
trials without consulting the objective, and the budget is fifteen — so ten of them are a fixed
grid set by the seed and the bounds, redrawn identically at every retrain. **The ceiling
therefore rescales that fixed grid far more than it constrains any search.** Under the 0.02
bound, all ten XJSE warm-up draws land between 0.0011 and 0.0113, entirely inside the band that
historically held up; under 0.2, five of the ten sit above 0.02.

This reframes two things written above.

- The instability recorded under "Not reproducible, and that is informative" has a smaller
  cause than a chaotic sampler. Only five trials respond to the data at all, and the argmax
  across fifteen — ten of them fixed — flips between a warm-up draw and an informed trial on
  tiny differences in fold IC. Nine consecutive XJSE retrains returned warm-up draw #2 and then
  three did not; that is the flipping, not a search wandering.
- The overfitting signature is real and is now attributable. Measured across 20 rolling origins,
  the *informed* trials are what pull the selected learning rate up: on XNYS, where nothing caps
  it, the production arm picks a mean rate of 0.0403 against 0.0151 for blind draws at the same
  budget. The folds prefer high rates and the holdout does not, and the informed portion of the
  search is the part doing the pulling.

So the ceiling works, and it works by keeping a fixed grid inside a safe band on the market where
that grid strays. It is a guard rail, not a better search — and the JSE champion it protects,
v3, is itself one of those warm-up draws rather than a tuned model.

## An apparent contradiction, resolved

[Round count](round-count.md) found that lowering the learning rate cost XJSE 66% of peak IC.
That experiment fixed the round count at 20–200, which starves a low learning rate: 200 rounds
at 0.002 barely moves a model off its starting prediction. Production and this test fit with
early stopping over up to 1,500 rounds, so a low rate has room to learn. The round counts the
low-rate fits here settled on were not measured, so this is the likely reconciliation rather
than a confirmed one.

## London (2026-10-18)

London joined as the third market with the default 0.2, and was measured the same way before its
first challenger: six panels rolling back 63 trading days, rebuilt from the bars available on each
panel's end date; seeds 42, 7 and 123; ceilings 0.2, 0.06 and 0.02; the same decision rule, fixed
before running. Each run calls production's own tuner, and the 0.2 run on the newest panel at
seed 42 reproduced London's first champion exactly (learning rate 0.06408, holdout IC 0.06561).

| market | ceiling | collapses | mean holdout IC | paired vs 0.2 |
|---|---|---|---|---|
| XLON | 0.2 | 6/18 | 0.0382 | — |
| XLON | 0.06 | 3/18 | 0.0585 | +0.0203 (t +1.36), 4/6 panels |
| XLON | **0.02** | **0/18** | **0.0729** | **+0.0348 (t +3.22), 6/6 panels** |

**XLON passes, more clearly than XJSE did.** Uncapped, the tuner went above 0.02 in 15 of 18 runs,
and five of the six collapses came from rates above 0.1. Dropping the panel with the largest gain
(+0.086) leaves +0.0245 with 5 of 5 panels improving. The caveats above carry over: the panels
share most of their holdout, so the t-statistic is optimistic, and this is the gate's holdout, not
live returns.

London's first champion, v1, was tuned to 0.064 under the old bound and stays champion; the ceiling
applies from its first challenger. Its promotion margin was measured on v1's specification, and a
capped challenger keeps more boosting rounds, so the margin is re-measured when the champion changes
([promotion-margin.md](promotion-margin.md)). Scripts and log: `~/quantpulse-experiments/m12-london/`.

## Europe (2026-10-28)

The four European markets joined on 2026-10-27 with a **placeholder** of 0.02, the value both
non-US markets had needed, and were measured before their first challenger exactly as London was.
Every panel was built from the bars stored by 2026-10-28 15:00 UTC, the bars their first models
trained on. The rule was written down before the first fit: a lower ceiling passes when it has **at
least three fewer collapses out of 18** than 0.2 (XJSE went 6 → 3 and XLON 6 → 0, both adopted) and
its paired change is not significantly negative (t ≥ −2). Otherwise the market takes the default.

The newest panel at seed 42 under the placeholder is exactly what each first model was, and all four
reproduce it: holdout IC 0.02228 against 0.0223 recorded for XETR, −0.04324 against −0.0432 for
XPAR, 0.02398 against 0.0240 for XSWX, and −0.00282 against −0.0028 for XAMS.

| market | ceiling | collapses | mean holdout IC | paired vs 0.2 |
|---|---|---|---|---|
| XETR | **0.2** | **2/18** | **0.0717** | — |
| XETR | 0.06 | 1/18 | 0.0730 | +0.0012 (t +0.23), 3/6 panels |
| XETR | 0.02 | 2/18 | 0.0707 | −0.0011 (t −0.24), 2/6 panels |
| XPAR | **0.2** | **18/18** | **−0.0331** | — |
| XPAR | 0.06 | 18/18 | −0.0288 | +0.0043 (t +10.21), 6/6 panels |
| XPAR | 0.02 | 18/18 | −0.0304 | +0.0026 (t +0.95), 3/6 panels |
| XSWX | **0.2** | **4/18** | **0.0221** | — |
| XSWX | 0.06 | 4/18 | 0.0253 | +0.0032 (t +0.81), 4/6 panels |
| XSWX | 0.02 | 5/18 | 0.0224 | +0.0003 (t +0.15), 4/6 panels |
| XAMS | **0.2** | **12/18** | **0.0094** | — |
| XAMS | 0.06 | 11/18 | 0.0121 | +0.0027 (t +0.78), 5/6 panels |
| XAMS | 0.02 | 11/18 | 0.0167 | +0.0074 (t +1.38), 5/6 panels |

**No market passes, so all four take the default 0.2.** No ceiling removes more than one collapse
anywhere.

- **The tuner overshoots about as often, but the fast rates are not what fails.** Uncapped, it went
  above 0.02 in 8 to 13 of 18 runs, against London's 15. In London five of the six collapses came
  from rates above 0.1. In Frankfurt, Zurich and Amsterdam only 5 of their 18 collapses at 0.2 did,
  so taking those rates away leaves most of the failures in place.
- **Paris collapses under every ceiling.** All 54 fits score below 0.02, the best of them 0.007.
  The +0.0043 at 0.06 is consistent, which is what t +10 measures, but it moves a mean of −0.033 to
  −0.029. There is nothing for a ceiling to rescue.
- **Amsterdam comes closest.** Both lower ceilings raise its mean on five of six panels, by up to
  +0.0074, but 11 of 18 fits still collapse. The rule asks for fewer failures, not a higher
  average, so it is not adopted on a rise the rule did not name.
- **Frankfurt barely collapses at all,** and has the highest mean of the four (0.07) under every
  ceiling.

The caveats above carry over: the panels share most of their holdout, so each t-statistic is
optimistic, and this is the gate's holdout, not live returns. Zurich's first champion, v1, was tuned
under the placeholder and stays champion. Frankfurt, Paris and Amsterdam have no model yet, so the
default first applies to the candidates of the 2026-10-31 retrain. Scripts and logs:
`~/quantpulse-experiments/m13-europe/phase5/`.

## What changed

`Exchange.learning_rate_ceiling` carries the value per market — 0.02 for XJSE and XLON, 0.2 for
XNYS and the four European markets — alongside `ic_promotion_margin` and `feature_columns`, which
are per market for the same reason. The tuner takes it as a required argument with no default, so
no caller can fall back to the widest range unnoticed. At a ceiling of 0.2 the tuner returns
exactly what it returned before the change, so XNYS training is unaltered. Europe's change from the
0.02 placeholder to 0.2 does alter what its tuner searches, from the 2026-10-31 retrain on.

## Related

- [Round count](round-count.md) — the fixed-round sweep reconciled above.
- [Why the champion has three trees](three-tree-champion.md) — early stopping on this panel.
- [Does retraining buy anything?](retrain-value.md) — the gate-conditional replay, and the
  tuning leak measured both ways.
- [Does the tuner's budget buy anything?](tuning-budget.md) — why most of the trials are not a
  search, and the mechanism correction above.
