# Findings

Measurement write-ups, one per investigation. Each states a question, how it was measured,
what came back, and what the result does *not* support.

| Finding | Question | Outcome |
|---|---|---|
| [Baseline comparison](baseline-comparison.md) | Does the model beat a one-line momentum rule? | Not on the JSE. Momentum became a standing competitor in the gate. |
| [Feature ablation and pruning](feature-ablation-and-pruning.md) | Do the thirteen features earn their place? | Not shown either way. Pruning helps the NYSE under tuning (t +3.00); the "markets disagree about `vol_63`" result was **withdrawn 2026-09-01**. Ranking on `vol_63` raw beats every fitted model on the NYSE (t −3.1). |
| [Why nothing could beat the NYSE incumbent](unbeatable-incumbent.md) | Why were five retrains rejected? | The champion was trained two days before a backfill tripled the panel. Not skill. |
| [Model staleness](model-staleness.md) | How fast does a model go stale? | **Corrected 2026-09-01** — not measurably, on either market. The six-week NYSE bound and the rising JSE curve were both five-origin artifacts; across 46 origins neither decays. The cadence is unmeasured, not justified. |
| [Why the JSE candidate keeps losing to momentum](jse-momentum-regime.md) | Is the promotion stall a model going wrong? | No — the candidate is at a four-year high on the gate's own metric. Momentum swung +0.17 and overtook it. On the JSE the verdict tracks the competitor (corr −0.77) rather than the model. |
| [A per-market learning-rate ceiling](learning-rate-ceiling.md) | Why did both markets' candidates collapse in September? | Not the market and not the tuning-leak fix: the tuner overshot into learning rates that win its own folds and lose the holdout. A 0.02 ceiling lifts XJSE holdout IC 0.030 → 0.052 (t +2.63, 5/6 panels) and fails on XNYS, so it is set per market. It will not end the JSE stall alone. |
| [Does the tuner's budget buy anything?](tuning-budget.md) | Would more trials, or fewer blind ones, produce a better candidate? | No, and the budget is the wrong question: two thirds of the trials are a seeded warm-up grid redrawn identically every retrain, and **13 of the 27 candidates ever produced are exact matches to one of its ten points** — the JSE champion among them. Random search beats production TPE (XNYS +0.0101, t +4.64, 28/36 origins), so no trial count was adopted. A third round settled why, with a control that depends on no capped parameter — the same parameters refitted at a second seed: **a single fit's holdout IC is mostly fit noise** (reliability 0.13 XJSE, 0.33 XNYS), and the folds do not order it even after correcting for that (+0.044 / +0.093). Tuning is largely decorative here; fixed defaults are the next thing to test. Three of this finding's own claims were withdrawn along the way, including a pre-registered argument that did not follow. |
| [Can a fixed configuration replace the tuner?](fixed-defaults.md) | Is a fixed configuration no worse than a tuned one, at 1 fit a candidate instead of 61? | **Yes on both markets, by the pre-registered rule** — narrowly on XJSE (worst case −0.0053 against a −0.008 margin, −0.0078 under the plainest error), and on XNYS the defaults beat the tuner (+0.0123, t +2.73, worst case above zero). Not a switch: the result rests on heavily-read holdouts, so it waits on a live check. |
| [A live check before replacing the tuner](shadow-run.md) | Do the defaults hold up on data no study has read? | **Pre-registered, running from 2026-10-10.** A shadow beside each weekly candidate, scored forward. Built to catch harm, not to re-prove benefit, which would take a year. |
| [Does retraining buy anything?](retrain-value.md) | Is a freshly fitted model better than an older one, and does the gate change that? | No to both. Every resolvable lag has the wrong sign (XNYS 21d −0.0173, t −2.86), and replaying the promotion policy leaves it negative (−0.0038 / −0.0047, unresolved). The gate promotes at 9–14% of retrain points, which bounds what any cadence can buy. |
| [Why the champion has three trees](three-tree-champion.md) | Is early stopping broken? | No, but it is useless: **re-measured 2026-09-01**, the inner split carries no information about the holdout either way, and neither it nor CV stopping beats picking a round at random. |
| [Can the round count be chosen well?](round-count.md) | Is there a fix for that? | No, and **corrected 2026-09-01** — no count is shown to suit either market; the JSE result was one holdout's draw. A lower learning rate does flatten the curve, but costs 66% of peak IC on the JSE. |
| [Is there a variance risk premium?](variance-risk-premium.md) | Did options cost more than the underlying delivered? | Not measurably — IV 32.5% against realised 32.2%, t 0.80 at day level. A unit error first reported it at t 80. |

The method these share is written down once in
[How to measure things here](../measurement.md). It is worth reading first: most of these
findings exist because an earlier version of them got the measurement wrong.

Three rows above were corrected on 2026-09-01 by a single audit. All three had been measured
across seeds on one window, or across five origins pooled as twenty-five fits — which counts
the same window several times, because re-drawing the seed re-draws the fit and not the market.
Every claim measured that way changed when the origin was rolled, and two reversed outright. If
a row here rests on seeds rather than windows, treat it as unmeasured rather than weak.
