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

## Related

- [Why nothing could beat the NYSE incumbent](unbeatable-incumbent.md) — an incumbent
  that never ages out is the failure this measures against
- [How to measure things here](../measurement.md) — the rolling-origin rule came from
  getting this wrong first
