# Baseline comparison result (2026-08-14)

`quantpulse baseline` scores every competitor on one shared holdout, cut exactly as the
promotion gate would cut it, through the same `pipeline.score_holdout`. Momentum and reversal
are fitted on nothing at all; ridge is fitted on the training window; the champion is only
*scored*, exactly as the gate re-scores an incumbent.

**XJSE** — holdout 2025-04-15 → 2026-07-14, 311 sessions:

| model | IC | Sharpe | ann. return | max DD |
|---|---|---|---|---|
| noise | −0.0216 | −1.49 | −7.83% | −12.31% |
| **momentum** | **0.1167** | **2.28** | 19.34% | **−3.58%** |
| ridge | 0.0777 | 1.96 | 21.37% | −7.53% |
| champion v3 | 0.0681 | 1.84 | 19.35% | −7.53% |
| reversal | −0.0031 | −1.47 | −12.72% | −21.53% |

**XNYS** — holdout 2025-04-15 → 2026-07-15, 313 sessions:

| model | IC | Sharpe | ann. return | max DD |
|---|---|---|---|---|
| **champion v1** | **0.1907** | **2.48** | 54.43% | **−5.13%** |
| ridge | 0.0532 | 1.53 | 27.77% | −7.25% |
| momentum | 0.0161 | −0.22 | −5.01% | −10.86% |
| noise | −0.0015 | 0.47 | 5.70% | −6.53% |
| reversal | −0.0388 | −0.73 | −14.01% | −31.21% |

**The JSE champion does not earn its place.** Plain 63-day momentum beats it on every metric
— IC 0.117 against 0.068, Sharpe 2.28 against 1.84, and half the drawdown — with zero
parameters and zero fitting. The linear ridge beats it too. Momentum had no fitting advantage
whatsoever in this comparison, which makes the result harder to explain away, not easier.

**The NYSE champion clearly does.** IC 0.191 against ridge's 0.053 and momentum's 0.016, on
the same window. Whatever the model is finding on the US panel, momentum is not it.

Two things this also settles:

- **Noise scored Sharpe +0.47 on XNYS** while its IC was −0.0015. A signal containing nothing
  produced a positive-looking Sharpe. That is direct support for the project's decision to
  gate on IC rather than Sharpe, previously argued from a seed re-roll and now visible from
  a pure control.
- **Momentum and reversal score oppositely** (0.117 vs −0.003 on XJSE, 0.016 vs −0.039 on
  XNYS), so the backtest is responding to signal direction rather than to some artefact that
  would flatter anything ranked.

Caveats that belong with the numbers, and the first of them was
[vindicated on 2026-08-30](../measurement.md#the-seed-is-not-a-sample-of-the-market): two
findings measured on one window were later refuted by rolling the origin, and repeating this
comparison across windows is still the outstanding work. This is **one holdout window**, and
it overlaps the
momentum-rich stretch incident 24 identified (raw 63-day momentum IC +0.039 Mar–Dec 2025,
−0.004 after). One noise draw is not a distribution. Neither observation rescues the JSE
champion — momentum beat it *on the window the gate itself would have used* — but both mean
the right next step is repeating this across several windows before concluding how general it is.

## Related

- [Feature ablation and pruning](feature-ablation-and-pruning.md) — the same margin
  mistake, caught later
- [Why nothing could beat the NYSE incumbent](unbeatable-incumbent.md) — why the gate
  stalled despite this baseline being in place
