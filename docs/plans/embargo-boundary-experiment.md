# Does the embargo boundary cause the JSE inversion?

**Status: RUN 2026-09-01. H rejected — and the premise withdrawn.** The experiment did what it
was designed to do: D ≈ E on both markets, which is the decision rule below for concluding the
effect is not the gap. It was then overtaken. **The inversion this set out to explain does not
exist** — it was a five-origin sampling artifact, corrected in
[model staleness](../findings/model-staleness.md#what-was-reported-and-how-it-failed). Results
are recorded in [what the arms showed](#what-the-arms-showed) because the arms are still a
clean null on the embargo, but the question at the top of this page no longer has a subject.

Designed 2026-08-26, written before measuring, because
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

## What the arms showed

Five origins × 15 seeds = 75 paired differences per age bucket, paired on (origin, seed),
differences against arm B. **These are the same five origins that produced the artifact**, so
read them as a comparison between arms and not as a level.

| arm | emb | cut | age 0–20 | age 21–41 | age 42–62 | age 63–83 |
|---|---|---|---|---|---|---|
| A | 0 | 0 | −0.1822 (t −0.7) | −0.0915 (t −1.1) | −0.0940 (t −2.8) | +0.0557 (t +2.6) |
| B | 21 | 21 | **−0.1767** | **−0.0802** | **−0.0623** | **+0.0319** |
| C | 42 | 42 | −0.1620 (t +1.8) | −0.0749 (t +0.4) | −0.0728 (t −0.9) | +0.0589 (t +2.9) |
| D | 63 | 63 | −0.1623 (t +1.4) | −0.0992 (t −1.5) | −0.0908 (t −2.6) | +0.0564 (t +2.3) |
| E | 21 | 63 | −0.1600 (t +2.0) | −0.0787 (t +0.1) | −0.0860 (t −1.8) | +0.0664 (t +3.5) |

Arms A–D move the embargo and the training end together and so attribute nothing on their own.
Arm E splits them, pooled over ages 0–62:

| contrast | holds fixed | isolates | XJSE | XNYS |
|---|---|---|---|---|
| D vs E | training end at origin − 63d | **the gap** | −0.0092 (t −0.98) | +0.0012 (t +0.38) |
| E vs B | embargo at 21d | training recency | −0.0018 (t −0.20) | +0.0092 (t +2.22) |

D ≈ E on both markets — the rule below for rejecting H — and on the JSE the gap contrast carries
the wrong sign for it besides. Every arm reproduced the (artifactual) inversion: at age 0–20 the
five span −0.1600 to −0.1822, against an effect of 0.18.

**One arm looked like a signal and was not.** Pooled over ages 0–62, arm A sits below the
control at t −2.15 — the direction H predicts. But the difference is at ages 42–62, not at
0–20 where H needs it, and *every* arm sits below B there including both with a wider embargo.
No embargo effect moves emb-0 and emb-63 the same way, so this is B's draw:

| | age 0–20 | age 21–41 | age 42–62 | age 63–83 |
|---|---|---|---|---|
| B − mean of the other four arms | −0.0101 (t −1.64) | +0.0059 (t +0.55) | **+0.0236 (t +2.75)** | **−0.0274 (t −3.98)** |

With B excluded, the widest embargo contrast — A vs D, emb 0 against 63 — is −0.0051 (t −0.61).

Run at 15 seeds rather than the 5 costed below: at 5 seeds the control's 42–62 bucket sat 0.026
from where 15 put it, and both readings of the sweep were unsafe at that n. That instability was
the first sign of the sampling problem that the
[staleness correction](../findings/model-staleness.md) later found underneath all of it.

## Related

- [Model staleness](../findings/model-staleness.md) — the observation, and the round count
  ruled out
- [Can the round count be chosen well?](../findings/round-count.md) — the fitting procedure
  this replaces as a candidate
- [How to measure things here](../measurement.md) — pairing, error selection, and unresolved-vs-null
