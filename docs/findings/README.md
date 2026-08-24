# Findings

Measurement write-ups, one per investigation. Each states a question, how it was measured,
what came back, and what the result does *not* support.

| Finding | Question | Outcome |
|---|---|---|
| [Baseline comparison](baseline-comparison.md) | Does the model beat a one-line momentum rule? | Not on the JSE. Momentum became a standing competitor in the gate. |
| [Feature ablation and pruning](feature-ablation-and-pruning.md) | Do the thirteen features earn their place? | The markets disagree about the same feature. Pruning helps the NYSE under tuning (t +3.00); not acted on. |
| [Why nothing could beat the NYSE incumbent](unbeatable-incumbent.md) | Why were five retrains rejected? | The champion was trained two days before a backfill tripled the panel. Not skill. |
| [Model staleness](model-staleness.md) | How fast does a model go stale? | NYSE skill lasts ~6 weeks, so the weekly cadence is justified. The JSE curve rises with age. |
| [Why the champion has three trees](three-tree-champion.md) | Is early stopping broken? | No — the inner-validation split does not predict holdout performance. |
| [Can the round count be chosen well?](round-count.md) | Is there a fix for that? | No general one. The round count is a per-market quantity; a fixed 25 rounds beats early stopping on the JSE only. |

The method these share is written down once in
[How to measure things here](../measurement.md). It is worth reading first: most of these
findings exist because an earlier version of them got the measurement wrong.
