# Why nothing can beat the NYSE incumbent (2026-08-23)

Five consecutive retrains were rejected on the NYSE. The incumbent re-scores at **IC 0.1777**
on the shared holdout while every fresh candidate lands near 0.060. The cause is not skill.

**Champion v1 was trained on a different panel from every challenger.** The `features` table
records when each row was written:

| written | covers | rows |
|---|---|---|
| 2026-07-18 | 2023-04-04 → 2026-07-17 | 41,200 |
| 2026-07-20 | 2018-04-04 → 2026-07-20 | 63,000 |

v1 was trained on 2026-07-18, when history began in **2023-04**. Two days later the panel was
backfilled to 2018, roughly tripling it. Every candidate since trains on the long panel.

Reproduced end to end, same hyperparameters throughout:

| trained on | trees | IC on the current holdout |
|---|---|---|
| v1's short panel (2023-04 →) | 25 | **+0.1792** |
| the full panel (2018-04 →) | 21 | +0.0366 |
| *champion v1 itself* | *25* | *+0.1777* |

The short-panel refit matches the champion to within 0.0015 on the same tree count. The
holdout sits immediately after the recent regime, so a model that saw only that regime scores
five times better on it than one diluted by five extra years. **The gate is comparing a
window specialist against generalists, on the specialist's window.**

Three things follow.

1. **The incumbent's advantage is an artifact of when it was trained**, and it will persist
   for as long as v1 holds the alias. This is the promotion stall, fully explained.
2. **The holdout score is not predicting live behaviour.** v1 scores 0.1777 on the backtest
   window and the live book is −1.15% at Sharpe −1.27 over 24 sessions. Whatever the 0.1777
   measures, it is not what the strategy earns.
3. The same backfill already caused one incident: v2 was demoted on 2026-07-25 for being
   "promoted on mismatched holdouts (panel grew 07-20)". The mismatch was corrected for the
   *challenger* and never for the *incumbent*, which is the model the backfill actually
   stranded.

`model_runs` records each run's holdout window but not the span of the panel it trained on,
so nothing in the data would have shown this. Two models fitted to different histories are
not comparable, and the gate has no way to know.

## The early-stopping mismatch is fixed, and it invalidates the sweeps above

`_fit_one` now early-stops on IC — the metric the gate decides on — instead of RMSE. Measured
paired across ten seeds on **one holdout**, so this table carries the weakness described in
[the seed-is-not-a-sample rule](../measurement.md#the-seed-is-not-a-sample-of-the-market) and
has not been re-measured across origins. The panel finding above does not: it is a mechanical
reproduction, not a statistical estimate — the short-panel refit matches the champion to
within 0.0015 IC, and no error bar is doing any work in that claim.

| market | trees (median) | paired IC delta | seeds better |
|---|---|---|---|
| XNYS | 1 → 12 | −0.0019 ± 0.0033 (t −0.57) | 4/10 |
| XJSE | 1 → 22 | **+0.0389 ± 0.0112 (t +3.48)** | 8/10 |

Clearly better on the JSE, indistinguishable on the NYSE. The change is right on principle
either way: a stopping rule has to watch the metric the decision is made on.

**The sweeps above have been re-run under the new rule** and are the corrected numbers. The
NYSE findings survived and sharpened; the JSE pruning result reversed sign. What the old rule
had produced was not wrong in direction so much as underpowered, since a one-tree model can
split on a single feature.

## A second, smaller finding

On the full panel, early stopping fires after **one boosting round** in seven of eight seeds:
the final fit validates on an inner split using RMSE, while the gate scores IC, and RMSE on
noisy 21-day forward returns plateaus immediately. Holding trees fixed, IC peaks near 10–25
trees (0.062) against 0.050 at one tree. So candidates are also being cut short — worth about
0.01 IC, independent of the panel problem above.

## Related

- [Why the champion has three trees](three-tree-champion.md) — found while chasing this
- [Model staleness](model-staleness.md) — what a model is worth as it ages, which is the
  other half of the incumbency question
- [How to measure things here](../measurement.md)
