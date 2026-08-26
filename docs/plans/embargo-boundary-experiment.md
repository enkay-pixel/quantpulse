# Does the embargo boundary cause the JSE inversion?

**Status: DESIGNED 2026-08-26, not yet run.** Written before measuring, because
[measurement.md](../measurement.md) says never let the answer see the test, and the arms below
are chosen to make one hypothesis fail rather than to find a number that supports it.

## What is being explained

[Model staleness](../findings/model-staleness.md) freezes a model and scores it on windows
after its training data ends. On the JSE:

| model age | IC |
|---|---|
| 0–20 days | −0.1682 |
| 21–41 days | −0.0892 |
| 42–62 days | −0.0913 |
| 63–83 days | +0.0190 |

A model with no skill scores IC ≈ 0. A consistent −0.17 means it ranks systematically
*backwards* on the three weeks immediately after its training data, and the anti-signal decays
to nothing by 63–83 days. That same doc rules out the fitting procedure: a fixed 25 rounds,
which beats early stopping outright on this market, reproduces the inversion unchanged.

## The mechanics as they stand

- `make_forward_returns` labels each row with the 21-day forward return and drops rows with no
  future, so a row at date *t* carries information from *t+21*.
- `split_by_date(frame, fraction, embargo_days)` cuts at the fraction boundary and then drops
  the `embargo_days` dates *before* the cut. With `embargo_days = 21 = horizon`, the last
  training row is at *cut − 21*, whose label reaches exactly to the cut.
- `_fit_frozen` applies the same split again to carve an inner early-stopping tail, so the
  embargo is applied twice on the way to a frozen model.

The last training label therefore terminates *at* the boundary, not before it. One horizon of
embargo is the minimum that prevents a label crossing it, with nothing to spare.

## Hypothesis, and the problem with it

**H:** the relationship the model learns is anchored on labels that terminate at the boundary,
and that relationship is inverted for the window immediately following.

The obvious version of this predicts the wrong sign. If labels leaked *into* the forward
window, the model would have partially seen those returns and IC at 0–20 days would be
**positive**. It is the most negative bucket. So plain forward leakage is already inconsistent
with the observation, and H survives only in the subtler form: the boundary-terminating labels
teach a relationship that reverses just past them.

Stating that now matters. The experiment is worth running because it can *kill* H cheaply, not
because H is likely.

## Arms

`embargo_days` is the only thing that varies. Everything else — 5 origins, 5 seeds,
`DEFAULT_PARAMS`, `step_days = 21`, `n_steps = 4`, the same panel — is held fixed.

| arm | embargo | what it changes |
|---|---|---|
| A | 0 | labels straddle the boundary; maximal overlap |
| B | 21 | current behaviour, the control |
| C | 42 | one clear horizon of separation |
| D | 63 | two |

## The confound, and the arm that controls it

Raising the embargo removes training dates, so arms C and D differ from B in **two** ways: a
wider label gap *and* a training set that ends earlier. A monotonic weakening of the inversion
would be consistent with either.

| arm | embargo | training end | isolates |
|---|---|---|---|
| D | 63 | origin − 63 | gap + recency |
| E | 21 | truncated to origin − 63 | recency alone |

Arm E holds the training end date where arm D puts it while keeping the narrow gap. Then:

- **D ≈ E** → the effect is recency of information, not the boundary. H dead.
- **D ≠ E** → the gap itself matters. H survives.

Without E the experiment cannot attribute anything, which is the whole reason it is designed
rather than just run.

## Pairing and error

Per [measurement.md](../measurement.md): score every arm under the *same* (origin, seed) pair
and summarise the **differences** against arm B, per age bucket. The seed and the window then
cancel instead of entering as noise.

The question is whether the embargo moves the curve, so the varying quantities are origin and
seed together: 5 × 5 = 25 paired differences per bucket, and the error is their spread. The
unpaired standard errors already published (±0.053 at 0–20) are the wrong yardstick here and
must not be reused.

## Predictions, recorded in advance

- **If H holds:** the inversion weakens monotonically B → C → D, and D ≠ E.
- **If recency:** B → C → D still weakens, but D ≈ E.
- **If neither:** all arms sit within noise of B, as the round count did. H dead, and the cause
  is in what the model learns from the panel rather than at any boundary.
- **Arm A is the sharpest test.** Removing the embargo entirely should make the inversion
  *worse* under H. If A is indistinguishable from B, H is in serious trouble regardless of what
  C and D do.

## Control market

Run the identical sweep on XNYS, whose curve decays normally. If the arms move XNYS the same
way, the effect belongs to the harness, not to the JSE.

## Cost, and what to do if unresolved

A 25-fit curve takes about 15 seconds. Five arms across two markets is roughly 250 fits, a few
minutes. That matters for the rule that an unresolved result is not a null result: if the
paired differences are stable but short of resolution, more seeds are cheap here, and the doc
should report what n would be needed rather than "no effect".

## Related

- [Model staleness](../findings/model-staleness.md) — the observation, and the round count
  ruled out
- [Can the round count be chosen well?](../findings/round-count.md) — the fitting procedure
  this replaces as a candidate
- [How to measure things here](../measurement.md) — pairing, error selection, and unresolved-vs-null
