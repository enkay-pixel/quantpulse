# A live check before replacing the tuner (pre-registered 2026-10-04)

**Status: pre-registered, not yet measured.** This page reaches `main` in the same change that adds
the shadow, so no shadow row exists until its decision rule is fixed — the rule in
[How to measure things here](../measurement.md#fix-the-decision-rule-before-the-run-where-the-merge-cannot-erase-it).

## Why

[The fixed-defaults study](fixed-defaults.md) found the pipeline's defaults non-inferior to the tuner
on XJSE, narrowly, and better on XNYS. Its own rule makes that *subject to a live check*, because the
holdouts it rests on had been read by every round before it, and because holdout IC does not predict
live returns well here. This is that check.

## What the shadow is

Each Saturday, after the production candidate is fitted, gated and committed, the same retrain fits
`fixed_default` — the defaults under the market's ceiling — on the same panel, holdout and seed, and
records it as a `shadow` row beside the candidate. It is never registered, never gated and never
champion, and the table refuses a shadow with any decision, because the live record's start date and
the backfilled boundary identify champions by the decision alone. It runs in its own session after
production commits, so it cannot fail the retrain.

## What it can and cannot show

**The weekly holdout comparison is not new evidence.** Successive holdouts overlap by about 98%, so
each week largely repeats the comparison the study already made. It is reported every Saturday as a
check that the shadow behaves in production the way it did in the study, and it feeds no decision.

**The new evidence is forward.** Each week's two candidates can be scored on dates after their panel
ended — returns that did not exist when they were fitted, which no study has read.

**And it is weak.** A forward window is 21 sessions; an IC on 29 to 50 names over 21 sessions is very
noisy; and weekly windows overlap about four times, so eight Saturdays hold roughly two independent
windows. Resolving a difference of 0.01 would take on the order of a year. **This check cannot re-prove
that the defaults are better. It can catch evidence that they are worse** — that the study's result
was an artefact of windows read too often. The rule is built for that job and no other.

## Measure

For each weekly retrain *D*, with the production candidate's holdout ending at *H*:

- **Forward window**: the 21 sessions of that market's calendar after *H*, scored as their 21-day
  labels mature. Twenty-one because it is the label horizon, so the choice is not a free parameter.
- **Both candidates are refitted** with `--as-of H`, which reproduces a retrain's panel exactly. Each
  refit is checked before it is used: the tuned refit's holdout IC must equal the production row's
  stored value, and the fixed refit's must equal the shadow row's. A refit that does not reproduce its
  week is not that week's model, and the week is reported as unrecoverable rather than used.
- **Per session**, the cross-sectional Spearman IC between prediction and realised 21-day return; **per
  week**, the mean over the window, for each arm; the **paired difference** Δ = fixed − tuned.
- **Across weeks**, the mean of Δ, with a Newey-West error at lag 4, since each window overlaps the
  next four.

## Decision rule, fixed in advance

Over the **eight weekly retrains from 2026-10-10 to 2026-11-28**, read once the last of their forward
windows has matured — around the end of December. Per market, against the gate's own margin
(0.008 XJSE, 0.006 XNYS):

1. **Harm shown — keep the tuner** if the one-sided 95% *upper* bound on mean Δ is below −margin: the
   fixed configuration is worse by more than the gate would ever treat as luck, even at its most
   favourable.
2. **Otherwise, switch that market to `fixed_default`.** The study already supports switching; this
   check exists to stop it, not to approve it, and an unresolved result does not stop it.
3. **Not a clean run** if the shadow failed, or was unpaired, in two or more of the eight weeks, or
   if two or more weeks could not be recovered. That is an engineering problem to fix, and the
   window is extended by as many weeks as were lost before anything is read.

The weekly holdout differences are reported alongside and decide nothing.

## Disclosures

- **The direction of the burden is a choice, and it is the important one.** A rule of "switch only if
  the live data proves the defaults better" would never fire inside a year at this sample size, so it
  would amount to never switching. This rule puts the burden on harm instead, on the strength of the
  study. If that is the wrong place for it, the place to change it is here, before the first shadow
  runs.
- **On XJSE the tuned arm is already a fixed point.** Its tuner has returned the same warm-up draw for
  three straight weeks, so the XJSE comparison is between two fixed configurations.
- **The forward scorer is built** — `quantpulse shadow-forward`, implementing the measure above with
  every constant the rule fixes. Its foundation was checked on real data before the first shadow
  week, without reading any forward return: refitting with `--as-of` the 2026-10-03 candidates'
  holdout end reproduces v14 and v15 to twelve decimal places, a difference of exactly zero, and the
  fixed refits match the dry run. So every week's real models can be recovered.
- **Holdout IC is the metric throughout**, as in the study. The gate's drawdown floor and Sharpe veto
  are not checked here.

## Addition: interim reports withhold the scores

Made before the first shadow week, and stricter than the protocol above rather than different from
it — the decision rule is unchanged.

Windows start maturing around 9 November and the rule reads once, around the end of December. A
report that showed each week's difference as it matured would invite reading it early, and under a
rule that stops the switch only on harm, looking often enough lets noise stop it. So until the rule
can be read, `quantpulse shadow-forward` shows each week's health and progress — its status, how
many sessions have matured, whether its refit reproduced — and withholds the scores. Engineering
problems still surface early, as rule 3 requires; the effect does not. A test fails if a score is
shown before the window closes.

## Addition: the reading is the first readable run

Made before the first shadow week, and stricter than the protocol above rather than different from
it — the decision rule is unchanged.

"Read once" leaves open *which* run is the reading. The scorer can be run on any day, and a verdict
computed after a data revision can differ from one computed before it — so a reader who disliked the
first verdict could read again later without moving a single threshold. A weekly job,
`scripts/check-shadow-forward.sh` (Mondays), closes that. The first of its runs to find a market's
rule readable saves the output, with the commit and image that produced it, to
`~/quantpulse-experiments/shadow-run/<market>.verdict.txt`, and that market is never scored again.
**That file is the reading.** The day it happens is set by the exchange calendars, not chosen.

The same job reports lost weeks as they happen, so rule 3's engineering problems are found while the
window is still open. For the same reason a retrain now counts as due from the day after its
Saturday: counted on the day itself, a run that morning would file a retrain that had not yet fired
as lost.

## Disclosure: a dry run, before the first shadow week

Recorded here, before the first shadow week, because it was seen.

After deployment, the shadow was run once against the live panel to check it worked end to end,
inside a session that was then rolled back — nothing was written, and the live id sequence did not
move. No ingest had run since the retrain of 2026-10-03, so the panel was that retrain's, and the
shadow paired with its candidates on both markets.

**It went against the study.** On that one holdout:

| | `fixed_default` | candidate | difference | margin |
|---|---|---|---|---|
| XJSE | 0.0081 | v14 0.0352 | **−0.0271** | −0.008 |
| XNYS | 0.0177 | v15 0.0254 | **−0.0077** | −0.006 |

How much it should weigh: it is one holdout, and the study measured the paired difference on a single
holdout to move by about 0.025 when only the seed changes, so −0.027 is roughly one such swing. It is
also a holdout comparison, which this rule says decides nothing. It is reported because it is the
first look on data later than the study's pin, and because it points the other way.

**Nothing in the rule changes.** No threshold moves, no arm changes, and the reading still waits for
the forward windows. But it is a reason not to treat the switch as a foregone conclusion — which is
what this check is for — and it bears on the disclosure above about where the burden sits: under a
rule that switches unless harm is shown, an early unfavourable reading like this one does not stop
the switch unless the forward evidence confirms it.

## Results

Not yet measured.
