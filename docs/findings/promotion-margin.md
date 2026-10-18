# The promotion margins, re-measured (2026-10-18)

**In short:** A new model replaces the champion only if it scores better by a margin set from how
much a score moves by chance. Re-measured while adding London, that chance movement had grown
since the margins were set, to three times the JSE's margin, so the margins were raised to match.
No past decision changes.

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

## What changed

| market | before | now |
|---|---|---|
| XNYS | 0.006 | **0.009** |
| XJSE | 0.008 | **0.026** |
| XLON | — | **0.027** |

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
