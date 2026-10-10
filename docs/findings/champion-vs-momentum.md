# Does the live JSE champion beat momentum going forward? (pre-registered 2026-10-10)

**Status: pre-registered, not yet measured.** This page reaches `main` before the measurement is
built or run, under the rule in
[How to measure things here](../measurement.md#fix-the-decision-rule-before-the-run-where-the-merge-cannot-erase-it).

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

## Results

Not yet measured.

## Related

- [Why the JSE candidate keeps losing to momentum](jse-momentum-regime.md) — the same question for
  the retraining procedure, across 49 windows
- [Baseline comparison](baseline-comparison.md) — where momentum became the standing competitor
