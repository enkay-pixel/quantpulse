# Findings

Measurement write-ups, one per investigation. Each states a question, how it was measured,
what came back, and what the result does *not* support.

| Finding | Question | Outcome |
|---|---|---|
| [Baseline comparison](baseline-comparison.md) | Does the model beat a one-line momentum rule? | Not on the JSE. Momentum became a standing competitor in the gate. |
| [Feature ablation and pruning](feature-ablation-and-pruning.md) | Do the thirteen features earn their place? | The markets disagree about the same feature. Pruning helps the NYSE under tuning (t +3.00); not acted on. |
| [Why nothing could beat the NYSE incumbent](unbeatable-incumbent.md) | Why were five retrains rejected? | The champion was trained two days before a backfill tripled the panel. Not skill. |
| [Model staleness](model-staleness.md) | How fast does a model go stale? | **Corrected 2026-08-30** — not measurably, on either market. The six-week NYSE bound and the rising JSE curve were both five-origin artifacts; across 46 origins neither decays. The cadence is unmeasured, not justified. |
| [Why the champion has three trees](three-tree-champion.md) | Is early stopping broken? | No, but it is useless: **re-measured 2026-08-30**, the inner split carries no information about the holdout either way, and neither it nor CV stopping beats picking a round at random. |
| [Can the round count be chosen well?](round-count.md) | Is there a fix for that? | No, and **corrected 2026-08-30** — no count is shown to suit either market; the JSE result was one holdout's draw. A lower learning rate does flatten the curve, but costs 66% of peak IC on the JSE. |
| [Is there a variance risk premium?](variance-risk-premium.md) | Did options cost more than the underlying delivered? | Not measurably — IV 32.5% against realised 32.2%, t 0.80 at day level. A unit error first reported it at t 80. |

The method these share is written down once in
[How to measure things here](../measurement.md). It is worth reading first: most of these
findings exist because an earlier version of them got the measurement wrong.

Three rows above were corrected on 2026-08-30 by a single audit. All three had been measured
across seeds on one window, or across five origins pooled as twenty-five fits — which counts
the same window several times, because re-drawing the seed re-draws the fit and not the market.
Every claim measured that way changed when the origin was rolled, and two reversed outright. If
a row here rests on seeds rather than windows, treat it as unmeasured rather than weak.
