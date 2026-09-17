# A per-market learning-rate ceiling (2026-09-17)

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

## An apparent contradiction, resolved

[Round count](round-count.md) found that lowering the learning rate cost XJSE 66% of peak IC.
That experiment fixed the round count at 20–200, which starves a low learning rate: 200 rounds
at 0.002 barely moves a model off its starting prediction. Production and this test fit with
early stopping over up to 1,500 rounds, so a low rate has room to learn. The round counts the
low-rate fits here settled on were not measured, so this is the likely reconciliation rather
than a confirmed one.

## What changed

`Exchange.learning_rate_ceiling` carries the value per market — 0.02 for XJSE, 0.2 for XNYS —
alongside `ic_promotion_margin` and `feature_columns`, which are per market for the same reason.
The tuner takes it as a required argument with no default, so no caller can fall back to the
widest range unnoticed. At a ceiling of 0.2 the tuner returns exactly what it returned before
the change, so XNYS training is unaltered.

## Related

- [Round count](round-count.md) — the fixed-round sweep reconciled above.
- [Why the champion has three trees](three-tree-champion.md) — early stopping on this panel.
- [Does retraining buy anything?](retrain-value.md) — the gate-conditional replay, and the
  tuning leak measured both ways.
