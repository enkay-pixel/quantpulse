# Model staleness result (2026-08-23, **corrected 2026-08-30**)

> **The original result was wrong.** Both curves below were measured at five origins, with an
> error bar that pooled 25 (origin, seed) fits — counting each origin five times, because the
> seed re-draws the fit and not the market. Rolled across 46 origins the JSE inversion and the
> NYSE six-week decay both disappear. The original numbers are kept in
> [what was reported, and how it failed](#what-was-reported-and-how-it-failed) rather than
> deleted, because two later investigations were built on them.

The weekly retrain cadence was chosen, never measured. `quantpulse staleness` freezes a model
and scores it on successive windows *after* its training data ends, so decay is read off a
curve.

## The curves, at 46 origins

Origins every 21 trading days from 2022-06 to 2026-03, so the age-0–20 windows **tile** the
period instead of sampling five points in it. Three seeds per origin, averaged within origin
first; the error then describes origin-to-origin variation, which is what a claim about the
market needs. Lag-1 autocorrelation across blocks is +0.196 (XJSE) and +0.020 (XNYS), and an
AR(1) correction leaves every t below unchanged.

| model age | **XJSE** IC | t | **XNYS** IC | t |
|---|---|---|---|---|
| 0–20 days | +0.0058 ± 0.0289 | +0.2 | +0.0352 ± 0.0235 | +1.5 |
| 21–41 days | +0.0259 ± 0.0284 | +0.9 | +0.0592 ± 0.0256 | +2.3 |
| 42–62 days | +0.0044 ± 0.0287 | +0.2 | +0.0376 ± 0.0240 | +1.6 |
| 63–83 days | +0.0003 ± 0.0307 | +0.0 | +0.0411 ± 0.0226 | +1.8 |

**There is no decay on either market, and no inversion on the JSE.** The NYSE model holds a
weak positive IC of roughly +0.04 out to 83 days rather than falling through zero at six
weeks. The JSE model sits at zero at every age — 43% of its age-0–20 blocks are negative,
which is what no skill looks like.

The JSE per-origin series runs from −0.53 to +0.35 and is mostly negative through
2022-12 – 2024-08 and mostly positive after. That swing is the whole finding: a five-point
sample of it can produce almost any curve.

## What was reported, and how it failed

| model age | XJSE published | XJSE at 46 origins | XNYS published | XNYS at 46 origins |
|---|---|---|---|---|
| 0–20 | −0.1558 | +0.0058 | +0.0793 | +0.0352 |
| 21–41 | −0.1106 | +0.0259 | +0.1253 | +0.0592 |
| 42–62 | −0.1012 | +0.0044 | −0.0431 | +0.0376 |
| 63–83 | +0.0219 | +0.0003 | −0.0704 | +0.0411 |

**Both runs are correct and they agree where they overlap.** Re-run at the five published
origins, this harness reproduces the published numbers: XJSE age 0–20 at −0.180 against −0.156,
and the whole XNYS curve at +0.067, +0.118, −0.037, −0.083 against +0.079, +0.125, −0.043,
−0.070. Nothing in the code was wrong. The five origins landed on the negative stretches —
their per-origin values on the JSE were −0.156, −0.560, −0.413, +0.181, +0.048.

The error bar is what hid it. Pooling 25 (origin, seed) fits reports the JSE inversion at
t −3.2; the same numbers pooled across the five origins give **t −1.3**, with two of five
origins positive. Almost all the variance is between origins — the spread of the five origin
means (0.309) is as large as the spread of all 25 fits (0.283), so the seeds were contributing
essentially no independent information while multiplying the apparent sample by five.

[measurement.md](../measurement.md) already carried the rule this breaks, and already recorded
a staleness curve failing it once before by quoting *seed* error across single windows. Rolling
the origin was the fix then. Five origins was not enough of it, and the pooled error bar made
the shortfall invisible.

One property of the curve was real and is worth keeping: a frozen model's ranking decorrelates
from itself as it ages — per-ticker prediction rank correlates +0.52, +0.36, +0.16 with its own
age-0–20 ranking at the three later ages. Whatever IC a frozen model starts with therefore
shrinks toward zero with age **mechanically**, without anything going stale. At the five
original origins the ratio of IC to surviving ranking is flat (−0.180, −0.164, −0.182), which
is the entire shape the curve was read as decay.

## What the JSE model actually learns

Measured while chasing the inversion, and unaffected by its collapse.

The model is a **volatility bet**, and it builds the same one on both markets:

| | vol_63 gain share | corr(pred, vol_63) out-of-sample | vol_63 IC within training |
|---|---|---|---|
| XJSE | 0.348 | +0.509 | +0.045 |
| XNYS | 0.331 | +0.461 | +0.040 |

The difference is whether that bet has anything to pay out. Scoring `vol_63` alone as if it
were the whole model, across the same 46 forward windows:

- **XNYS: +0.0878 ± 0.0352 (t +2.5)** — the relationship holds forward
- **XJSE: +0.0018 ± 0.0391 (t +0.0)** — there is nothing there

**The JSE model spends a third of its capacity on a feature that carries no forward signal in
that market.** It also overfits far harder: in-sample IC +0.2198 against the NYSE's +0.1271,
from 29 tickers and 58k rows against 50 and 105k. A model with that much capacity per name
fits the training panel tightly and arrives at zero out of sample, which is exactly what the
46-origin curve shows.

This appeared to disagree with [the ablation](feature-ablation-and-pruning.md), which had
`vol_63` helping the JSE and hurting the NYSE.
[It does not](feature-ablation-and-pruning.md#the-vol_63-disagreement-resolved-2026-08-30):
re-run across rolling origins, neither of the ablation's deltas survives (t +0.7 and +0.2,
down from +9.14 and −5.35), so there is no conflict — `vol_63` simply does nothing on the JSE
by either measure. What is resolved on the NYSE is stranger: ranking on `vol_63` raw beats a
tree fitted on `vol_63` alone by −0.0349 (t −3.1), and that beats the full model. The signal
is there and the model subtracts from it.

## What this changes

- **The retrain cadence has no measured support.** "Weekly is comfortably inside that bound"
  and "a champion older than about six weeks is worse than nothing" both rested on the NYSE
  decay, which is not there. Weekly is not shown to be wrong either — it is unmeasured again.
- **Two investigations were chasing an effect that does not exist.** The round count and the
  embargo boundary were both correctly found not to cause the inversion. Both conclusions
  stand; the reason is now simply that there was no inversion to cause.
- **The JSE model is still the wrong model for that market.** That conclusion never rested on
  the inversion: it loses to a fit-free momentum rule, its full-model IC sits inside its own
  noise, and its live information ratio is negative. What is corrected is the claim that it
  predicts *backwards*. It does not. It predicts nothing, and now there is a mechanism for
  why.

## Related

- [How to measure things here](../measurement.md) — the rule this broke, sharpened by it
- [Can the round count be chosen well?](round-count.md) — corrected the same day, for the
  same reason
- [Does the embargo boundary cause the JSE inversion?](../plans/embargo-boundary-experiment.md)
  — the pre-registered design whose premise this removes
- [Why nothing could beat the NYSE incumbent](unbeatable-incumbent.md) — an incumbent that
  never ages out is the failure this set out to measure against
