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
draws out. Whether it does was a separate measurement, and it has since been run:
[crediting the gate](#crediting-the-gate-2026-09-01) below.

## Crediting the gate (2026-09-01)

The measurement the section above asks for, run. Rather than comparing fits, this replays the
**policy**. At each retrain point, in order: build the panel available at that moment,
embargoed so no forward label leaks; carve the gate's holdout off the end of it exactly as
`train_final_model` does; fit a candidate, re-score the incumbent **on that same holdout**, and
score the fit-free standing competitor on it too; ask the real `decide_promotion` at the
market's own IC margin; then score whatever is now deployed on the forward window. The champion
carries across origins, so the origins run in order and the seed is what varies.

Three policies on identical forward windows, 49 retrain points 21 trading days apart, three
seeds, errors Newey-West as above:

| | XJSE | XNYS |
|---|---|---|
| the gate promoted at | **9%** of retrain points | **14%** |
| gated — what the gate deploys | +0.0012 | +0.0387 |
| always — deploy every candidate | +0.0053 | +0.0331 |
| never — keep the first promoted model | +0.0050 | +0.0434 |
| **gated − never** | **−0.0038 ± 0.0143 (t −0.3)** | **−0.0047 ± 0.0095 (t −0.5)** |
| gated − always | −0.0041 (t −0.5) | +0.0085 (t +0.9) |

**Crediting the gate does not reverse the answer.** Gated minus never is negative on both
markets and favours never retraining in a majority of windows (29/49 and 26/41). Nothing here
resolves — closing the gated-minus-never gap would need roughly 2,700 windows on the JSE and
670 on the NYSE against the 41–49 available — so this is *not shown to help*, not *shown to
harm*. The gate is not selecting badly either: against blind retraining it is +0.0085 on the
NYSE and −0.0041 on the JSE, both inside their noise.

### The gate promotes too rarely for the cadence to matter

The averages hide the mechanism. Across 49 opportunities the gate promoted between **one and
nine** times depending on market and seed:

- On **XNYS nothing was deployed at all until 2023-01/03** — eight months of refusing every
  candidate, because none beat the momentum competitor on its own holdout.
- On **XJSE at seed 42 the gate promoted once in four years**, at the first retrain point.
  For that seed the deployed model and the never-retrained one are identical in all 49 windows.
- Overall the deployed model *is* the never-retrained one in 44% of JSE windows and 13% of
  NYSE windows.

So the schedule changes what is deployed a handful of times per market per four years, and
those changes are not measurably better than not making them. That is a sharper statement than
the mean difference, and it is the reason the mean difference is small: **the cadence's room to
matter is bounded by how rarely the gate says yes.**

### What this run is not

`always − never` here is **not** the fresh-minus-stale figure in the table above. That compares
a model against one fitted 21 trading days earlier; this compares a fresh model against a
2022-vintage one whose lag grows to years. Same direction, different contrast — it is not a
replication of the −0.0173 and should not be read as one.

Two caveats carry: hyperparameters are held at `DEFAULT_PARAMS` where production tunes per
retrain, and the cadence simulated is 21 trading days rather than weekly, chosen so forward
windows tile without overlapping labels. A weekly cadence offers roughly four times as many
promotion opportunities against the same gate, which raises the number of chances rather than
the quality of any one of them.

## What this changes

Nothing automatically. The cadence stays where it is until someone decides otherwise; the
point of this note is that the decision now has a measurement under it in the direction
opposite to the one usually assumed.

What can be said: **the cadence's value rested entirely on the promotion gate, and the gate
has now been credited without changing the answer.** Weekly retraining does not buy a better
model on average; deploying only what the gate approves does not buy one either. Its main
effect is to create promotion opportunities — twelve a quarter — against a gate that says yes
to roughly one in eight of them, and whose own noise floor this project has had to measure and
correct more than once. Fewer retrains may be safer rather than merely cheaper, and nothing
measured so far argues against that.

## Related

- [Model staleness](model-staleness.md) — no decay out to 83 days, which is what makes this
  result unsurprising in hindsight.
- [Feature ablation and pruning](feature-ablation-and-pruning.md) — paired-on-seed comparison,
  the same technique used here.
- [The unbeatable incumbent](unbeatable-incumbent.md) — an earlier case of a training window,
  not model quality, explaining a score.
