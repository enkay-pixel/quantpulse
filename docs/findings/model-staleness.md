# Model staleness result (2026-08-23)

The weekly retrain cadence was chosen, never measured. `quantpulse staleness` freezes a model
and scores it on successive windows *after* its training data ends, so decay is read off a
curve. The freeze point is rolled across five origins and five seeds, and each age pools 25
window-fits — a single origin gives each age one 21-day window, whose IC swings far more with
*which* three weeks it covers than with anything about the model.

**XNYS** — skill for about six weeks, then negative:

| model age | IC | std err |
|---|---|---|
| 0–20 days | +0.0793 | 0.0319 |
| 21–41 days | +0.1253 | 0.0437 |
| 42–62 days | −0.0431 | 0.0430 |
| 63–83 days | −0.0704 | 0.0234 |

IC falls 0.1498 from the first bucket to the last (3.8 sd) and is still positive out to
41 days. **The weekly cadence is comfortably inside that bound** — the first thing this
project has done that measurement actually supports rather than merely permits. It also sets
the outer limit: a champion older than about six weeks is worse than nothing.

**XJSE** — the curve goes the wrong way:

| model age | IC | std err |
|---|---|---|
| 0–20 days | −0.1558 | 0.0526 |
| 21–41 days | −0.1106 | 0.0396 |
| 42–62 days | −0.1012 | 0.0407 |
| 63–83 days | +0.0219 | 0.0372 |

IC *rises* with age (2.8 sd) and is negative for the first two months. **A model that predicts
worst when it is freshest is not stale** — whatever is wrong sits in the training window, not
the cadence. This lines up with everything else measured on the JSE: it loses to a fit-free
momentum rule, its full-model IC is inside its own noise, and its live information ratio is
negative. Retraining it more often would not help; it is the wrong model for that market.

Both curves are measured at `DEFAULT_PARAMS`, like the feature sweeps, for the same reason —
retuning per origin would vary two things at once. The caveat carries over: this describes a
fixed-parameter model, and the deployed one is tuned.

## The round count is not the cause (2026-08-26)

[Can the round count be chosen well?](round-count.md) found that a fixed 25 rounds beats early
stopping outright on the JSE (+0.0166, t +3.43) and that early stopping picks badly there. The
curve above is measured at `DEFAULT_PARAMS`, which uses that same early stopping, so the
inversion had an obvious mechanical explanation: the frozen models are simply fit wrong.

They are not. Same harness, same five origins and five seeds, only the round count replaced —
25 rounds with a patience larger than that, so early stopping cannot fire:

| model age | early stopping | fixed 25 rounds |
|---|---|---|
| 0–20 days | −0.1682 | −0.1866 |
| 21–41 days | −0.0892 | −0.0927 |
| 42–62 days | −0.0913 | −0.1106 |
| 63–83 days | +0.0190 | +0.0135 |

Every pair sits well inside the standard errors above, and the fixed count is marginally worse
rather than better. **The inversion is not an artifact of the fitting procedure.** It survives a
different round count, five freeze points spanning 2022–2026, and five seeds.

That was the strongest mechanical candidate, so ruling it out narrows the question rather than
answering it. What remains is the shape: a model with no skill scores IC ≈ 0, and a consistent
−0.17 means it ranks systematically backwards on the three weeks after its training data, with
the anti-signal decaying to nothing by 63–83 days. Something learned is actively wrong for
about two months. The candidates left — label overlap at the embargo boundary, or a regime that
reverses just past the training window — need an experiment designed for them rather than a
config change.

The first run of this comparison also reproduced the published curve to within a standard error
on every bucket, three days after it was written.

## Related

- [Why nothing could beat the NYSE incumbent](unbeatable-incumbent.md) — an incumbent
  that never ages out is the failure this measures against
- [How to measure things here](../measurement.md) — the rolling-origin rule came from
  getting this wrong first
