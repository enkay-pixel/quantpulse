# The promotion margins, re-measured (2026-10-18)

**In short:** A new model replaces the champion only if it scores better by a margin set from how
much a score moves by chance. Re-measured while adding London, that chance movement had grown
since the margins were set, to three times the JSE's margin, so the margins were raised to match.
No past decision changes. The four European markets were measured the same way on 2026-10-28, and
Frankfurt's again on its first champion on 2026-10-31; their margins run from 0.009 to 0.031.

## What the margin is

The gate promotes a challenger whose holdout IC beats the champion's, and the standing momentum
rule's, by `Exchange.ic_promotion_margin`. The margin is meant to be larger than the difference
luck alone produces: two standard deviations of the holdout IC when the champion's specification is
refitted with nothing changed but the random seed. A challenger that wins by less cannot be told
apart from the champion reseeded.

The margins in use, 0.006 for the NYSE and 0.008 for the JSE, were set on 2026-08-08 from a
spread of about 0.003 and 0.004.

## How it was re-measured

For each market, the current champion's tuned parameters are read from MLflow and refitted on
today's panel under sixteen seeds, through production's own `train_final_model`, then scored on
the gate's holdout at the market's width. The spread across seeds is the margin's quantity
exactly: the gate decides on one holdout at a time, so seeds on that holdout are the right sample.
That is unlike most findings here, where one window standing in for the market is the flaw.

Scripts and logs: `~/quantpulse-experiments/m12-london/` (`margin_study.py`,
`margin_regime_check.py`).

| market | champion | holdout IC, mean of 16 | sd | **2 sd** | margin in use |
|---|---|---|---|---|---|
| XNYS | v10 | 0.0269 | 0.0047 | **0.009** | 0.006 |
| XJSE | v3 | 0.0206 | 0.0130 | **0.026** | 0.008 |
| XLON | v1 | 0.0633 | 0.0133 | **0.027** | none yet |

## Why it moved

On 2026-08-23 the final fit's early stopping changed from RMSE to IC, so that it watches the
metric the gate decides on. Refitting each champion under both rules shows what that did to the
spread:

| market | rule | sd | rounds kept (median, range) |
|---|---|---|---|
| XJSE | RMSE (before) | **0.0038** | 60 (4–129) |
| XJSE | IC (now) | 0.0130 | 7 (1–50) |
| XNYS | RMSE (before) | 0.0052 | 172 (122–214) |
| XNYS | IC (now) | 0.0047 | 63 (1–102) |
| XLON | RMSE (before) | 0.0086 | 16 (7–21) |
| XLON | IC (now) | 0.0133 | 1.5 (1–34) |

- **The JSE is explained.** Under the old rule its spread is 0.0038, matching the recorded 0.004.
  Stopping on IC ends its fits after a handful of rounds, and which handful depends on the seed,
  so the round count becomes a second draw on top of the fit. The margin was set before that
  change and never re-measured after it, so for eight weeks it sat at a third of the noise.
- **The NYSE is not.** Its spread is about 0.005 under either rule, against 0.003 recorded. The
  panel and the champion's parameters have both changed since, and which of them widened it was
  not separated.
- **London's champion is barely more than one tree.** It keeps one or two rounds under most seeds,
  which is also why its forecasts take only nine distinct values across 41 names. It is positive
  under every seed (0.043 to 0.092).

The mechanism matches what [three-tree-champion.md](three-tree-champion.md) found about the
early-stopping split, which does not predict the holdout: the round it picks is close to arbitrary,
and that arbitrariness now shows up in every IC the gate compares.

## Europe (2026-10-28)

Frankfurt, Paris, Zurich and Amsterdam joined on 2026-10-27 with a **placeholder** of 0.027, the
widest margin then measured, and were measured before their first challenger. Each specification was
refitted under seeds 0–15 on the bars stored by 2026-10-28 15:00 UTC and scored on the gate's
holdout, 2025-06-19 or 06-20 to 2026-09-28. This came after each market's learning-rate ceiling was
settled at 0.2 ([learning-rate-ceiling.md](learning-rate-ceiling.md#europe-2026-10-28)), because the
ceiling decides which specification the tuner returns.

Only Zurich has a champion, so it is measured on v1's specification, as London was. The other three
have none, so each is measured on what production's tuner chooses at seed 42 under the new ceiling.
That was decided before running, as was taking the value whatever it came out as.

| market | specification | learning rate | holdout IC, mean of 16 | sd | **2 sd** | placeholder |
|---|---|---|---|---|---|---|
| XETR | tuned | 0.0073 | 0.0249 | 0.0028 | **0.006** | 0.027 |
| XPAR | tuned | 0.0377 | −0.0328 | 0.0083 | **0.017** | 0.027 |
| XSWX | champion v1 | 0.0091 | 0.0306 | 0.0115 | **0.023** | 0.027 |
| XAMS | tuned | 0.0641 | 0.0334 | 0.0156 | **0.031** | 0.027 |

- **Amsterdam's is wider than the placeholder.** The placeholder was chosen as the widest margin
  then measured, so that no challenger could be promoted on too small a one. Amsterdam shows that
  was not a bound. It did no harm: Amsterdam's first model scored below zero, which no margin
  decides.
- **Frankfurt's was the narrowest measured on any market.** Its first model, judged on 2026-10-28,
  scored IC 0.0223 against momentum's −0.0017. That clears 0.006 and missed the placeholder by
  0.003. It was not re-judged: the 2026-10-31 retrain fitted a new candidate, promoted it, and the
  margin was re-measured on it (below).
- **Paris's specification never ranks the market.** All 16 seeds score below zero (−0.043 to
  −0.013), so the gate's floor of IC ≥ 0 stops its candidates before the margin is reached.
- **Amsterdam's tuned learning rate is London v1's,** 0.06408 in both. With the same seed and the
  same bounds, the tuner's first ten trials are the same draws in every market
  ([tuning-budget.md](tuning-budget.md)). A tuned specification is often one of those fixed draws,
  not something the market chose.

Scripts and logs: `~/quantpulse-experiments/m13-europe/phase5/`.

### Frankfurt, on its first champion (2026-10-31)

The 2026-10-31 retrain promoted XETR v2, so its margin was re-measured on v2's specification, as
the caveat below required, with the bars stored when that retrain started (13:00 UTC). The rule
was written down first: v2 refitted at seed 42 must reproduce its recorded holdout IC to four
decimals, and the margin is 2 sd of seeds 0–15, rounded, whatever it comes out as.

v2's parameters turned out to be **exactly the specification measured on 2026-10-28**: the tuner
returned the same point, one of its fixed warm-up draws ([tuning-budget.md](tuning-budget.md)).
Only the panel and the holdout moved, by three or four sessions.

| holdout | specification | holdout IC, mean of 16 | sd | **2 sd** |
|---|---|---|---|---|
| 2025-06-20 to 2026-09-28 | tuned (2026-10-28) | 0.0249 | 0.0028 | 0.006 |
| 2025-06-25 to 2026-10-01 | champion v2 (the same parameters) | 0.0204 | 0.0047 | **0.009** |

- **v2 reproduces** (0.03306 at seed 42, its recorded value), so the study measures what was
  promoted. **The margin is now 0.009.**
- **The same specification re-rolled wider three sessions later.** A sixteen-seed sd carries about
  ±18% sampling error on its own, so part of the change is the estimate and part is the window;
  they were not separated. A margin measured once is rougher than its three decimals suggest.
- **v2's 0.0331 is above all sixteen reseeded fits** (0.014 to 0.031). The specification's
  typical holdout IC is 0.020, so the score that promoted it is the top of its own spread. It
  still clears momentum (0.0018) plus 0.009 at the mean, and nothing is re-judged: the gate
  re-scores the champion model itself against each challenger.

Scripts and logs: `~/quantpulse-experiments/m13-europe/xetr-v2/`.

## What changed

| market | before | now |
|---|---|---|
| XNYS | 0.006 | **0.009** |
| XJSE | 0.008 | **0.026** |
| XLON | — | **0.027** |
| XETR | 0.027, placeholder; 0.006 on 2026-10-28 | **0.009** (2026-10-31, on champion v2) |
| XPAR | 0.027, placeholder | **0.017** |
| XSWX | 0.027, placeholder | **0.023** |
| XAMS | 0.027, placeholder | **0.031** |

`ic_promotion_margin` no longer has a default, so a new market must state one deliberately and
measure it before its first challenger is judged.

**No past decision changes.** The one promotion since the stopping change, NYSE v10 on 2026-08-29,
won by 0.0114 (0.0641 against the champion's 0.0527), which clears 0.009 as well. The JSE has
promoted nothing since v3 in July.

**Two pre-registered readings are held to the margins they named.** The shadow run's verdict
([shadow-run.md](shadow-run.md)) and the fixed-defaults study ([fixed-defaults.md](fixed-defaults.md))
both judged against 0.008 and 0.006. Each now holds those values in code as `REGISTERED_MARGINS`
rather than reading the registry, so this change cannot move what either concludes.

## What it does not support

- **It does not make the gate better at picking models.** A wider margin stops promotions that
  are a reseed's luck. It says nothing about whether holdout IC predicts live returns, which on
  this platform it has not.
- **The JSE gate is now very hard to clear.** A challenger needs +0.026 over both the champion and
  momentum, which has scored 0.04–0.11 on recent JSE holdouts. That was already close to true;
  this makes it explicit rather than leaving it to a margin that looked passable.
- **The spread belongs to the champion's specification.** A challenger with different parameters,
  say a higher learning rate that keeps more rounds, may re-roll narrower or wider. Each
  champion change is a reason to re-measure.
- **Two of Europe's margins rest on a specification no market has adopted.** Paris's and
  Amsterdam's were measured on what the tuner chose on one panel, and a later retrain tunes on a
  newer one and may choose differently; Amsterdam's spread is more than three times Frankfurt's.
  Each is re-measured on its market's first champion, as Frankfurt's was on 2026-10-31.
