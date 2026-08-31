# Why the champion has three trees (2026-08-23)

> **Re-measured 2026-08-30 across 49 rolling origins.** Every figure below was taken across
> three or five *seeds* on **one holdout**, which says how much refitting moves that window's
> number and not whether the effect holds. Rolling the origin, **the two curves do not
> disagree, the NYSE inner-validation IC is not negative, and the cost is not a cost** — see
> [what the rolling measurement found](#what-the-rolling-measurement-found-2026-08-30). The
> page's conclusion that the tree count is close to arbitrary survives; its stated mechanism
> and its cost figure do not. The CV-stopping table was re-measured too: neither rule beats a
> random round, so CV stopping does not "help one market and hurt the other" either. Every
> figure on this page has now been re-run across origins.

XNYS v9 was promoted with three trees, which looked like the early-stopping fix having gone
wrong. It had not. Early stopping followed its signal correctly; the signal is the problem.

~~**The inner-validation IC is negative at every boosting round** on the NYSE — between −0.07
and −0.02 over 200 rounds, never positive.~~ **Not across origins:** only 18% of NYSE fits have
an inner curve negative at every round, and the mean inner-validation IC is **+0.0153 ± 0.0074**
— positive. Stopping picks the least-bad early round because that is genuinely the best that
split has to offer.

Worse, the two curves disagree. Tracking inner-validation IC and holdout IC round by round:

| market | correlation between the curves | holdout IC given up |
|---|---|---|
| XNYS | **−0.555** ± 0.126 (all five seeds negative) | 0.0254 ± 0.0053 |
| XJSE | **+0.436** ± 0.140 (four of five positive) | 0.0255 ± 0.0029 |

~~On the NYSE more boosting improves the inner split and *degrades* the holdout. On the JSE the
curves agree in direction.~~ **Neither holds across origins** — both correlations go to zero
(−0.008 and +0.080), so the markets do not disagree about this and neither curve predicts the
other. The cost figure does not survive either; see below.

That cost is measured against an **oracle** — the best round found by looking at the holdout,
which no honest rule may use. Peeking at the holdout to choose the round is exactly the
leakage the inner split was introduced to stop.

## What the rolling measurement found (2026-08-30)

49 origins every 21 trading days, three seeds each, 200 rounds with early stopping switched
off so the whole curve is visible. The inner-validation curve comes from the training callback;
the holdout curve is the 21-day window at the origin, scored at every fifth round. Errors are
across origins.

| | published (seeds, one holdout) | 49 rolling origins |
|---|---|---|
| curve correlation, XNYS | **−0.555** ± 0.126 | **−0.008 ± 0.078** (t −0.1) |
| curve correlation, XJSE | **+0.436** ± 0.140 | **+0.080 ± 0.071** (t +1.1) |
| inner-val IC negative at every round, XNYS | claimed always | 18% of fits; mean **+0.0153** |

**The central claim was that the two curves disagree, oppositely per market.** They do not
disagree at all — both correlations are indistinguishable from zero. The inner split neither
predicts the holdout nor anti-predicts it.

### The cost was the oracle, not the stopping rule

"Holdout IC given up" is the gap between the best round found by peeking and the round the
inner split picks. That gap is a **maximum over many noisy evaluations**, so it is biased
upward however the round is chosen — including by a rule that ignores the inner split entirely.
Measuring the same gap for pickers that cannot be using any signal:

| picker | XNYS | XJSE |
|---|---|---|
| the inner-validation split | +0.0550 ± 0.0071 | +0.0669 ± 0.0072 |
| *a round chosen at random* | +0.0609 ± 0.0076 | +0.0585 ± 0.0049 |
| *the median round* | +0.0618 ± 0.0080 | +0.0608 ± 0.0051 |

**Early stopping on the inner split is indistinguishable from picking a round at random** —
better by 0.006 on the NYSE, worse by 0.008 on the JSE, both within one standard error. The
published ~0.025 was not the price of following the inner split; it was the oracle's own bias,
which any picker pays.

That *supports* this page's conclusion — the round choice is arbitrary with respect to what the
gate measures — while removing the reason it gave. The inner split is not misleading. It is
uninformative, which is a different thing and points at a different fix.

Two limits on the re-measurement. The window is 21 days where the original used ~313 sessions,
so the **magnitudes above are not comparable to the published ones** — a shorter window makes
both the spread and the oracle gap larger by construction. What is comparable is the
picker-versus-control contrast and the correlations, since those hold the window fixed.

## No available stopping rule recovers it

The obvious alternative is to pick the round from purged walk-forward folds of the training
portion, which does not leak. Originally measured over three seeds on one holdout:

| market | inner-val pick | CV pick | oracle |
|---|---|---|---|
| XNYS | +0.0372 | +0.0456 | +0.0699 |
| XJSE | +0.0548 | +0.0368 | +0.0778 |

~~CV stopping helps one market and hurts the other~~ — **re-measured across the same 49 rolling
origins, it does neither.** Holdout IC achieved by each rule, with two rules that use no signal
at all included as controls:

| rule | XNYS | XJSE |
|---|---|---|
| inner-validation pick | +0.0316 ± 0.0239 | +0.0013 ± 0.0280 |
| CV pick | +0.0305 ± 0.0252 | +0.0074 ± 0.0261 |
| *a random round* | +0.0245 ± 0.0237 | +0.0041 ± 0.0269 |
| *the median round* | +0.0248 ± 0.0237 | +0.0073 ± 0.0272 |
| oracle (peeks at the holdout) | +0.0866 ± 0.0247 | +0.0681 ± 0.0274 |

**Neither rule beats a random round on either market.** Paired against the random control:
the inner-validation pick is +0.0072 (t +1.0) on the NYSE and −0.0028 (t −0.5) on the JSE; the
CV pick is +0.0060 (t +0.9) and +0.0033 (t +0.5). Compared directly with each other, CV minus
inner-validation is −0.0011 (t −0.2) on the NYSE and +0.0061 (t +0.9) on the JSE — both
unresolved, and both the *opposite* sign to the published per-market split. There is no
disagreement between the markets to explain.

The oracle is the one column that separates, by +0.0621 (t +9.2) and +0.0640 (t +11.8) over
random. That gap is what a maximum over many noisy evaluations is worth; it is not skill any
rule could capture, which is precisely why no rule captures it.

**The holdout-optimal round is not predictable from training data here.** That conclusion is
unchanged and now rests on a stronger test: two independent picking rules, across 49 origins,
neither distinguishable from choosing a round at random.

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

- [Can the round count be chosen well?](round-count.md) — both fixes proposed here were
  tested there, and neither works in general

- [Why nothing could beat the NYSE incumbent](unbeatable-incumbent.md) — the stall this
  was found while investigating
- [Feature ablation and pruning](feature-ablation-and-pruning.md) — re-run after the
  early-stopping fix landed
- [How to measure things here](../measurement.md)
