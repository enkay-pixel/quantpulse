# Does retraining buy anything? (2026-09-01)

The [staleness curve](model-staleness.md) measures how a *frozen* model decays. That is not
the question the retrain cadence turns on. The cadence question is comparative: at a given
moment, is a model trained on everything available now better than the one trained some days
earlier? Scoring both on the **same** forward window holds the market fixed so only the
training cut-off differs — something a decay curve, whose ages are measured at different
times, cannot do.

Run with `quantpulse retrain-value`.

## Design

49 origins per market, spaced 21 trading days apart, over the back half of each panel
(XJSE 2022-06-01 to 2026-06-15, XNYS 2022-05-27 to 2026-06-05). At each origin a model is
fitted on everything up to 21 trading days before it — the same embargo the staleness curve
uses, so no forward label reaches the fit — and then scored on its own 21-day window and the
next three. A model fitted at one origin *is* the stale model for every later window, so all
lags come out of one set of fits: 49 origins x 3 seeds per market, not a multiple of it.

Fresh and stale are compared **at the same seed**, so seed-to-seed spread — larger on this
panel than the effect being looked for — differences out. Seeds are averaged **within** a
window before anything is pooled, so the sample counts windows, not fits.

## The result

Fresh minus stale IC, positive meaning retraining helped. The standard error allows for
correlation between neighbouring windows, because the model that is fresh for one window is
the stale model for the next few and a 21-day label straddles the window after it.

| market | lag | windows | fresh − stale | std err | t | favour fresh |
|---|---|---|---|---|---|---|
| XJSE | 21d | 48 | −0.0183 | 0.0095 | −1.92 | 18/48 |
| XJSE | 42d | 47 | −0.0054 | 0.0106 | −0.51 | 20/47 |
| XJSE | 63d | 46 | +0.0010 | 0.0128 | +0.08 | 24/46 |
| XNYS | 21d | 48 | −0.0173 | 0.0060 | −2.86 | 21/48 |
| XNYS | 42d | 47 | −0.0133 | 0.0084 | −1.59 | 18/47 |
| XNYS | 63d | 46 | −0.0135 | 0.0072 | −1.87 | 17/46 |

**Every resolvable difference has the wrong sign.** A freshly fitted model is not better than
one fitted three to thirteen weeks earlier; at the shortest lag on XNYS it is measurably
worse. This is consistent with the staleness curve rather than in tension with it: that curve
found no decay out to 83 days, and a model that does not decay has nothing for a retrain to
restore.

## How hard the negative result is

Three checks, because a mean that far from zero on a noisy panel usually deserves suspicion:

- **Serial correlation.** A Newey-West error bar allowing neighbouring windows to move
  together does not weaken the result; on XNYS at 21 days it sharpens it (t −2.59 to −2.86).
- **A single bad regime.** Split in half by time, both halves are negative on both markets
  (XJSE −0.0305 and −0.0062; XNYS −0.0220 and −0.0125).
- **Sign test.** Not significant anywhere (XNYS 21d: 21/48 favour fresh, p = 0.47).

The last one is the important qualification. The median window is only mildly negative
(−0.024 XJSE, −0.014 XNYS) and the mean is pulled down by a minority of windows where the
fresh model is much worse — the worst deltas are −0.31 and −0.16 against best cases of about
+0.10. The shape is **asymmetric**: retraining occasionally produces a considerably worse
model and rarely a considerably better one. That is a stronger argument against a fast
cadence than the mean alone, and a different one — it is about tail risk, not average loss.

## What this does and does not say

This measures retraining **unconditionally**. Production does not deploy every candidate: the
promotion gate compares candidate against incumbent and only then promotes. So this is not
directly a statement about the deployed model.

It does bound the argument, though. The gate scores both models on a **holdout carved from
the end of the training panel** — the recent past, not the forward window. If freshly fitted
models underperform going forward precisely because they are tuned to the recent past, then
the gate is selecting on the signal that misleads, and cannot be assumed to filter the bad
draws out. Whether it does is a separate measurement: a policy comparison that promotes only
when the gate would have, then scores what was actually deployed.

## What this changes

Nothing automatically. The cadence stays where it is until someone decides otherwise; the
point of this note is that the decision now has a measurement under it in the direction
opposite to the one usually assumed.

What can be said: **the cadence's value rests entirely on the promotion gate, not on
freshness.** Weekly retraining does not buy a better model on average, and its main effect is
to create promotion opportunities — twelve a quarter — against a gate whose own noise floor
this project has had to measure and correct more than once. Fewer retrains may be safer
rather than merely cheaper.

## Related

- [Model staleness](model-staleness.md) — no decay out to 83 days, which is what makes this
  result unsurprising in hindsight.
- [Feature ablation and pruning](feature-ablation-and-pruning.md) — paired-on-seed comparison,
  the same technique used here.
- [The unbeatable incumbent](unbeatable-incumbent.md) — an earlier case of a training window,
  not model quality, explaining a score.
