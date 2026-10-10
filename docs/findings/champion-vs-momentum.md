# Does the live JSE champion beat momentum going forward? (pre-registered 2026-10-10)

**Status: measured 2026-10-10. By the pre-registered rule v3 is ahead — because momentum
collapsed, not because v3 found anything.** The sections down to the results are the
pre-registration, pushed to `main` on its own before any code or run existed, under the rule in
[How to measure things here](../measurement.md#fix-the-decision-rule-before-the-run-where-the-merge-cannot-erase-it).
They are unchanged.

## Why

Every JSE candidate since the momentum check was added on 2026-08-15 — ten of them — has lost to
63-day momentum on the gate's holdout, inside a run of twelve rejections.
[Why the JSE candidate keeps losing to momentum](jse-momentum-regime.md) showed that verdict tracks
momentum rather than the model, and that the *retraining procedure* has no forward skill on this
market (+0.0058 ± 0.0289 across 49 windows). Neither page measured the model
actually serving predictions. That is **v3**, promoted 2026-07-25, before the momentum check existed.
It still scores every JSE session, and nothing has scored it on data it was not chosen on.

This measures that: v3 against momentum on the sessions after its holdout, which neither its fit nor
its promotion saw.

## What it can and cannot show

**It will very probably not resolve, and that is known now.** The window holds 53 sessions, and each
label is a 21-session return, so the window contains about two and a half independent periods. One
21-session window of JSE IC has ranged from −0.53 to +0.35 for a single model
([measurement](../measurement.md#the-seed-is-not-a-sample-of-the-market)), and pairing cancels only
the part the two signals share. With that little data, only a gap of roughly 0.1 or more could clear
the bound below.

It is worth running anyway. It is the only measurement of the model actually serving predictions, it
is cheap, and the record grows by about one independent window a month, so the same command re-run
later answers the same question with more data.

It cannot show that the JSE model *as a procedure* has or lacks skill — that is measured already,
across 49 windows. One fixed model on one stretch speaks for itself.

## Window, fixed in advance

- **Model:** `quantpulse-lgbm-xjse` version 3 (MLflow run `4c04305d`), loaded by version, not alias.
- **Its holdout end:** v3 was fitted on 2026-07-25 from data ending 2026-07-24. Its last matured label
  was 21 sessions earlier, **2026-06-25**. v3's run records no training span, so this is reconstructed
  from the XJSE trading calendar — and verified by re-scoring v3 on the holdout that implies, which
  must reproduce its recorded holdout IC of 0.062548.
- **Forward window:** **2026-06-26 to 2026-09-09**, 53 sessions — every session after the holdout
  whose 21-session label had matured by the pin, **`--as-of 2026-10-09`**.
- **Momentum:** the gate's standing competitor exactly — `mom_63_cs_rank`, unfitted.

## Measure

For each session *t* in the window: the rank IC of v3's score against the realised 21-session
return, and the rank IC of momentum against the same return, over the same tickers. These are the
per-date values the gate's `information_coefficient` averages. A session where either IC is
undefined — fewer than three tickers, or a constant score — is dropped from both, so every
comparison is paired.

**Δ = mean over sessions of (v3 IC − momentum IC)**, with a Newey-West error at lag 20, because each
label overlaps the next twenty.

v3's scores are replayed from the stored features, which covers the 21 sessions before it went live.
The replay is checked against the scores it actually served on the 32 sessions it was live, and the
served-only window is reported beside the main one.

## Reading rule, fixed in advance

1. **Momentum ahead** if the one-sided 95% *upper* bound on Δ is below zero.
2. **v3 ahead** if the one-sided 95% *lower* bound is above zero.
3. **Otherwise not resolved**, reported with how many more sessions the current mean would need at
   the current error — never as "no difference".

Reported alongside, deciding nothing: each signal's own mean IC; Δ in the three consecutive
21-session blocks (the last is 11 sessions); and the served-only Δ.

**None of these outcomes changes anything automatically.**

- If momentum is ahead, that is evidence that the predictions the JSE champion serves are beaten
  forward by a rule with no parameters. That would support marking them so on the dashboard. Whether
  to do that is a separate decision.
- If v3 is ahead, the forward record contradicts the trailing-holdout verdict for this model. That
  would support asking whether a trailing-holdout momentum check is the right gate on this market.
- If it is not resolved, nothing changes, and the command is re-run when the record is longer.

## Disclosures

- **Momentum on part of this window has already been seen, in four places:**
  - The [baseline comparison](baseline-comparison.md) scored both signals on a holdout ending
    2026-07-14, which includes the window's first 13 sessions, inside a 311-session average.
  - The [regime study](jse-momentum-regime.md), dated 2026-09-03, scored momentum's forward IC on
    rolling windows running to within weeks of that date, which likely overlap this window's first
    weeks.
  - The weekly gate reports show momentum's trailing-holdout IC falling from 0.0837 to 0.0518 over
    the five retrains of 2026-09-12 to 2026-10-10. Over those retrains this window's last 19
    sessions entered that holdout and sessions from a year earlier left it, so momentum probably did
    worse on those 19 than on the ones they replaced.
  - All of these were seen before this was designed, and the question was proposed after the
    rejection streak had been read.
- **v3 is a warm-up grid point** ([tuning budget](tuning-budget.md)) with a learning rate of 0.0011,
  so its scores may tie heavily within a session. Ties are handled by the rank correlation; a session
  where v3 scores every ticker the same is dropped by the rule above.
- **v3 uses 63-day momentum as one of its thirteen inputs.** The comparison is therefore partly
  between momentum and a model that already contains it, which is why it is paired.

## Results (measured 2026-10-10, pinned at 2026-10-09)

| XJSE, 2026-06-26 to 2026-09-09 | sessions | v3 IC | momentum IC | Δ | one-sided 95% bound | reading |
|---|---|---|---|---|---|---|
| replayed | 53 | −0.0097 | −0.2383 | **+0.2286** ± 0.0899 | lower +0.0807 | v3 ahead |
| served only | 32 | −0.1246 | −0.2544 | +0.1297 ± 0.0776 | lower +0.0021 | v3 ahead, barely |

| 21-session block | v3 | momentum | Δ |
|---|---|---|---|
| 06-26 to 07-24, before v3 went live | +0.1685 | −0.2140 | +0.3825 |
| 07-27 to 08-25 | −0.0362 | −0.2707 | +0.2344 |
| 08-26 to 09-09, 11 sessions | −0.2994 | −0.2229 | −0.0765 |

**Both checks held, one exactly.** Re-scoring the holdout the reconstructed window implies gives
v3's recorded holdout IC to every digit (0.062547779031685), so the window and the model are the
right ones. The replay matches what v3 served closely but not exactly: per-session ICs correlate
0.999 over the 32 live sessions (−0.1267 replayed, −0.1246 served), while single scores differ by
up to 0.00098 against a typical within-session spread of 0.0014. Since the holdout reproduces
exactly, the difference is in what the serving path saw on the day. **Traced the same day: there
is no train/serve skew.** On 29 of the 32 live sessions the replay equals the served score
exactly. The whole gap is 2026-08-11 to 08-13, when STX40.JO's bar was written after the session
had been scored — the late benchmark bar the [runbook](../runbook.md#host-agents-launchd)
records — so those three sessions were ranked over 28 tickers and STX40.JO was never scored on
them. Scored dates are never re-scored, by design, so the served record keeps what was actually
served. Evidence: `~/quantpulse-experiments/served-vs-replay-asof-2026-10-09/`. The served-only
row does not depend on the replay either way, and it reads the same as the replayed one.

### What it says

- **Momentum collapsed.** Its forward IC was −0.24 across the window and below −0.21 in every
  block. Every gate run from 2026-08-15 to 2026-10-10 scored it between +0.12 and +0.05 on its
  trailing holdout, and rejected every JSE candidate for losing to it. The trailing-holdout check
  was measuring a regime that had already turned — the [regime study](jse-momentum-regime.md)'s
  warning, arriving in the opposite direction to the one it planned for.
- **v3 did not find anything.** Its own forward IC is about zero (−0.0097), positive before it went
  live and negative since (−0.125 on the sessions it served). "Ahead" means it lost less.
- **The lead is all in the first 42 sessions.** In the latest 11, v3 was behind.

### What it does not say

- That v3 is a good model. Its forward IC is zero or negative in every way it was cut.
- That momentum has no forward value. Across 49 windows its edge is unresolved (t +0.9), and this
  is about two and a half independent windows.
- How far to trust the error. The per-session difference has a lag-1 autocorrelation of 0.74, and a
  lag-20 Newey-West error from 53 sessions is rough, as the pre-registration said. The gap, 0.23,
  is well past the roughly 0.1 the pre-registration said a resolvable one would need; the
  served-only row clears its bound by 0.002.

Under the pre-registered reading, this supports asking whether a trailing-holdout momentum check is
the right gate on this market. It changes nothing by itself.

Evidence: `~/quantpulse-experiments/champion-vs-momentum-asof-2026-10-09/`, holding the per-session
series, the run's attributes and log, `run.py` and the commit that ran it. To regenerate:
`quantpulse champion-forward --exchange XJSE --version 3 --data-end 2026-07-24 --as-of 2026-10-09`.

## Related

- [Why the JSE candidate keeps losing to momentum](jse-momentum-regime.md) — the same question for
  the retraining procedure, across 49 windows
- [Baseline comparison](baseline-comparison.md) — where momentum became the standing competitor
