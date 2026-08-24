# Why the champion has three trees (2026-08-23)

XNYS v9 was promoted with three trees, which looked like the early-stopping fix having gone
wrong. It had not. Early stopping followed its signal correctly; the signal is the problem.

**The inner-validation IC is negative at every boosting round** on the NYSE — between −0.07
and −0.02 over 200 rounds, never positive. Stopping picks the least-bad early round because
that is genuinely the best that split has to offer.

Worse, the two curves disagree. Tracking inner-validation IC and holdout IC round by round:

| market | correlation between the curves | holdout IC given up |
|---|---|---|
| XNYS | **−0.555** ± 0.126 (all five seeds negative) | 0.0254 ± 0.0053 |
| XJSE | **+0.436** ± 0.140 (four of five positive) | 0.0255 ± 0.0029 |

On the NYSE more boosting improves the inner split and *degrades* the holdout. On the JSE the
curves agree in direction. But the cost is the same on both, and it is large: ~0.025 of IC,
which is the size of the full-model IC itself (0.0272 and 0.0248).

That cost is measured against an **oracle** — the best round found by looking at the holdout,
which no honest rule may use. Peeking at the holdout to choose the round is exactly the
leakage the inner split was introduced to stop.

## No available stopping rule recovers it

The obvious alternative is to pick the round from purged walk-forward folds of the training
portion, which does not leak. Measured over three seeds:

| market | inner-val pick | CV pick | oracle |
|---|---|---|---|
| XNYS | +0.0372 | +0.0456 | +0.0699 |
| XJSE | +0.0548 | +0.0368 | +0.0778 |

CV stopping helps one market and hurts the other, and both stay far below the oracle. **The
holdout-optimal round is not predictable from training data here.**

## What this means

The tree count is close to arbitrary with respect to what the gate measures, and the spread
between rounds (~0.03 IC) is as large as the skill being measured. That is another noise
source under every IC on this page, alongside the seed. It is not fixed by changing the
stopping metric — that change was still right, since RMSE stopped after one round — and it is
not fixed by moving to CV stopping either.

Two directions worth trying, neither attempted here: fix the round count outright rather than
stopping adaptively, chosen by averaging CV curves over many seeds so the choice is at least
stable; or reduce the learning rate and cap rounds so the curve is flat enough that the choice
stops mattering. Both are modelling changes.

## Related

- [Why nothing could beat the NYSE incumbent](unbeatable-incumbent.md) — the stall this
  was found while investigating
- [Feature ablation and pruning](feature-ablation-and-pruning.md) — re-run after the
  early-stopping fix landed
- [How to measure things here](../measurement.md)
