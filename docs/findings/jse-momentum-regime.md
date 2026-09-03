# Why the JSE candidate keeps losing to momentum (2026-09-03)

Six consecutive rejections on the JSE since 2026-07-25, with `check-retrain` reporting the
same reason each week: *the latest candidate loses to the momentum baseline*. That reads as a
model going wrong. It is not what happened.

## What was measured

The [gate-conditional policy replay](retrain-value.md#crediting-the-gate-2026-09-01) records,
at each of 49 retrain points 21 trading days apart, exactly what the promotion gate saw: the
candidate's IC and the standing momentum competitor's IC **on the same holdout**, scored
through the same `score_holdout`. Three seeds, tuned, with the
[holdout leak](../development-history.md) fixed. Nothing new was fitted for this note.

Momentum is fit-free, so its *forward* IC could be scored directly on the same 21-day windows
the staleness work uses, with no model involved at all.

## The candidate did not get worse

| | first 12 retrains | last 12 retrains |
|---|---|---|
| candidate IC on the gate's holdout | +0.0154 | **+0.0446** |
| momentum IC on the same holdout | −0.0910 | **+0.0776** |

The candidate is at a **four-year high** on the metric the gate judges it by. Its forward IC is
flat at [+0.0058 ± 0.0289](model-staleness.md#the-curves-at-46-origins) throughout, which is
the same no-skill reading this project has recorded for that market for months.

**Momentum moved, by 0.17.** It swung from strongly negative to strongly positive, and it
overtook a candidate that was improving.

## The regime is real, not a trailing-window artifact

The gate scores on a holdout carved from the end of the training panel — the recent past. A
signal riding a regime looks good there whether or not it earns anything going forward, so
momentum was scored on the forward windows too:

| XJSE, 49 forward windows | IC | |
|---|---|---|
| 63-day momentum | +0.0290 ± 0.0318 (t +0.9) | first half −0.0308, second half **+0.0864** |
| 21-day reversal | +0.0197 ± 0.0277 (t +0.7) | |
| the model | +0.0058 ± 0.0289 (t +0.2) | flat |

Momentum's recent edge is genuine forward signal. Over the full four years it is **not
resolved** (t +0.9) — but in the second half, and in the last twelve windows (+0.0843), it is
predicting and the model is not.

On XNYS the same measurement gives momentum −0.0047 (t −0.2), flat in both halves. Momentum
does not work there, which is why the NYSE model beats it.

## On this market the gate measures the competitor, not the model

| | corr(margin, candidate IC) | corr(margin, momentum IC) |
|---|---|---|
| XJSE | +0.489 | **−0.765** |
| XNYS | **+0.831** | −0.516 |

Whether the JSE candidate clears the gate is mostly a fact about momentum. On the NYSE it is
mostly a fact about the model — which is what a working gate looks like, and the contrast is
the point.

Momentum's spread across the 49 points is wider than the candidate's (sd 0.0674 against
0.0498; range −0.159..+0.132 against −0.095..+0.097), so the more volatile term dominates a
difference that decides promotions.

## The uncomfortable symmetry

Through 2022-06 to 2023-07 the gate **promoted** this model repeatedly. Momentum's IC over that
stretch was around −0.13, and the candidate's was about zero — the same about-zero it has now.

So the JSE model was never shown to be good. It was promoted when its competitor was bad, and
is rejected now that its competitor is good. Both verdicts were about momentum.

That cuts both ways, and the forward-looking half is the one worth planning for: **if momentum
reverts, this model will start passing the gate again on no more skill than it has today.** The
gate would promote it for exactly the reason it promoted it in 2022. Nothing in the promotion
path can distinguish "the model earned it" from "the competitor stopped earning it", because
the gate only ever sees a difference.

## What this does and does not say

It does **not** say the gate is broken. Refusing to deploy a no-skill model against a rule that
currently predicts is the correct call, and the six rejections are the gate working. The
finding is about *why*, and about what will happen when the regime turns.

It does **not** rescue the JSE model. Its forward IC is zero in every period measured.

Two caveats sit on the numbers. The gate's holdout is a trailing ~311-session window that
overlaps heavily between adjacent retrain points, so the 49 points are far from independent
and the correlations above are descriptive rather than inferential. And momentum's full-period
forward IC is unresolved at t +0.9: a regime is not a law, and this one is roughly a year old.

## Related

- [Baseline comparison](baseline-comparison.md) — where momentum became a standing competitor;
  its own caveat named the momentum-rich stretch, and this is that caveat coming true
- [Does retraining buy anything?](retrain-value.md) — the policy replay these numbers come from
- [Model staleness](model-staleness.md) — the JSE model's forward IC, measured across origins
- [Why nothing could beat the NYSE incumbent](unbeatable-incumbent.md) — the other case where a
  promotion verdict turned out to be about something other than model quality
