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

Two caveats carried: hyperparameters were held at `DEFAULT_PARAMS` where production tunes per
retrain, and the cadence simulated is 21 trading days rather than weekly, chosen so forward
windows tile without overlapping labels. A weekly cadence offers roughly four times as many
promotion opportunities against the same gate, which raises the number of chances rather than
the quality of any one of them. **The first caveat has since been closed** — see below. The
weekly stride has not been.

### With tuning in the loop, and the leak removed

Running the same replay with Optuna at every retrain point, as production does, turned up a
defect first: production tuned on the **whole** panel while `train_final_model` carved the
gate's holdout off the end of that same panel, so the tuning CV's last fold *was* the gate's
exam — 313 of 313 dates on XJSE, 314 of 314 on XNYS. Fixed in the promotion path
(development-history incident 33); the replay was then run both ways, deliberately, because
the difference is itself the measurement of what the leak was worth.

One seed rather than three: tuning costs 20–75s per retrain point, and this project's own
finding is that origins are the unit of generalisation while seeds add almost no sample size,
so the budget bought all 49 origins.

| | promoted | gated | never | gated − never |
|---|---|---|---|---|
| **XJSE** `DEFAULT_PARAMS`, 3 seeds | 9% | +0.0012 | +0.0050 | −0.0038 (t −0.3) |
| **XJSE** tuned, leaky | 12% | −0.0058 | +0.0039 | −0.0097 (t −0.8) |
| **XJSE** tuned, fixed, 3 seeds | 9% | +0.0023 | −0.0027 | +0.0051 (t +0.3) |
| **XNYS** `DEFAULT_PARAMS`, 3 seeds | 14% | +0.0387 | +0.0434 | −0.0047 (t −0.5) |
| **XNYS** tuned, leaky | 22% | +0.0362 | +0.0435 | −0.0073 (t −0.6) |
| **XNYS** tuned, fixed, 3 seeds | 13% | +0.0390 | +0.0303 | **+0.0088 (t +0.9)** |

**Nothing here resolves, and one thing changes sign.** On the best-specified run — tuned, no
leak, three seeds — the NYSE gate-conditional policy is nominally *better* than never
retraining, +0.0088 at t +0.9, where both other specifications put it negative. The JSE does
not. Whatever else this says, it is a warning against quoting the `DEFAULT_PARAMS` row as
though tuning were a detail.

Read the three rows within a market, not across the table: **`never` is not a fixed model.**
It is "the first model this policy deployed", and a different tuning path deploys a different
first model — the NYSE baseline moves from +0.0435 to +0.0310 between runs. Each row's paired
difference is internally valid; the baselines are not common.

### Seeds, and why they are not a nuisance parameter here

Run at three seeds on the tuned leak-free path, the two markets behave differently:

| seed | XJSE gated − never | XNYS gated − never |
|---|---|---|
| 7 | +0.0212 (t +1.4) | +0.0056 (t +0.4) |
| 42 | −0.0047 (t −0.2) | +0.0101 (t +1.1) |
| 123 | −0.0013 (t −0.0) | +0.0107 (t +0.7) |
| **pooled** | **+0.0051 ± 0.0200 (t +0.3)** | **+0.0088 ± 0.0099 (t +0.9)** |

**XNYS is a stable estimate short of resolution; XJSE is noise.** All three NYSE seeds are
positive within a band of 0.005, which is the pattern
[measurement.md](../measurement.md#an-unresolved-result-is-not-a-null-result) describes — a
mean that barely moves while the error falls. The JSE changes sign between seeds and pools to
nothing.

**The seed is not a nuisance parameter once tuning is in the loop.** With fixed parameters it
only re-draws the fit, which is why this project's earlier finding was that seeds add almost no
sample size. With Optuna it also seeds `TPESampler`, so it selects different hyperparameters
and therefore a different *policy* — a second source of real variation, and the reason the JSE
swings from −0.005 to +0.021 across three of them.

What would settle the NYSE figure is **about 205 windows against the 40 usable here**, and this
panel cannot supply them: the back half is already tiled end to end at a 21-day stride, and
shortening the stride would overlap the forward windows rather than add independent ones. More
compute will not close this. A longer panel, or live evidence, is what would.

### What the leak was worth

The leaky and fixed runs differ only in the frame handed to the tuner, so the comparison is
clean, and it is **market-dependent**:

| | candidate's holdout IC, leaky − fixed | promotion rate |
|---|---|---|
| XNYS | **+0.0165 ± 0.0040 (t +4.2)** | 22% → 12% |
| XJSE | −0.0013 ± 0.0054 (t −0.2) | 12% → 10% |

On the NYSE the leak inflated the candidate's exam score by a resolved margin and nearly
doubled the promotion rate — the bias the fix was made for. On the JSE it did neither.

What it did on **both** markets is churn the decisions. Of the promotions made under each path,
only 1 of ~6 on the JSE and 3 of 11 on the NYSE survive the change: five JSE promotions
happened only with the leak and four only without it. With tuned learning rates spanning two
orders of magnitude between neighbouring origins (XJSE median 0.1697, XNYS median 0.0077,
range 0.0011–0.1954), moving the tuning frame produces a *different* model rather than a
better-scoring one. Where the leak also inflates, as on the NYSE, that different model is one
the gate is more likely to accept.

Every champion promoted before the fix was selected under the leaky path, on both markets.

## What this changes

Nothing automatically. The cadence stays where it is until someone decides otherwise; the
point of this note is that the decision now has a measurement under it in the direction
opposite to the one usually assumed.

What can be said: **the cadence's value rests entirely on the promotion gate, and crediting
the gate does not produce a resolved case for retraining on either market.** Weekly retraining
does not buy a better model on average, and deploying only what the gate approves does not
buy one either — on five of the six specifications measured. The exception matters and is
stated rather than buried: on the NYSE, with tuning real and the holdout leak gone, the
gate-conditional policy is nominally ahead of never retraining (+0.0101, t +1.1). One seed,
unresolved, and the opposite sign to its own `DEFAULT_PARAMS` row.

So the honest position is narrower than "retraining does not pay". It is that **no
specification resolves either way, and this panel cannot make one resolve** — the NYSE figure
would need roughly five times the windows that exist. What can be said is that the estimate
closest to production is stable and positive on the NYSE and absent on the JSE, and that the
cadence's main effect is to create promotion opportunities — twelve a quarter — against a gate
that says yes to roughly one in eight of them, and whose own noise floor this project has had
to measure and correct more than once.
Fewer retrains may still be safer rather than merely cheaper on the JSE; on the NYSE the
measurement now leans the other way without reaching resolution. The cheap experiments are
spent — what is left is time.

## Related

- [Model staleness](model-staleness.md) — no decay out to 83 days, which is what makes this
  result unsurprising in hindsight.
- [Feature ablation and pruning](feature-ablation-and-pruning.md) — paired-on-seed comparison,
  the same technique used here.
- [The unbeatable incumbent](unbeatable-incumbent.md) — an earlier case of a training window,
  not model quality, explaining a score.
