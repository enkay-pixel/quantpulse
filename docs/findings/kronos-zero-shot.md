# Does an open foundation model rank stocks better than ours? (pre-registered 2026-10-21)

**In short:** A test of Kronos, a freely available model trained on price charts from 45 exchanges,
against this project's own model and the momentum rule, on dates Kronos never saw in training. It
only measures; nothing in production changes because of it.

**Status: pre-registered, not yet measured.** This page reaches `main` before any forecast on the
test dates exists, under the rule in
[How to measure things here](../measurement.md#fix-the-decision-rule-before-the-run-where-the-merge-cannot-erase-it).

## Why

Every model this project has served is LightGBM on thirteen engineered features, and the open
question is whether any of them has skill at all: the JSE champion shows none forward
([v3 against momentum](champion-vs-momentum.md)), and retraining does not buy a better model
([retrain value](retrain-value.md)). Kronos ([paper](https://arxiv.org/abs/2508.02739),
[code](https://github.com/shiyu-coder/Kronos)) is a different kind of model entirely: a transformer
pre-trained on more than 12 billion candlesticks, used here without fitting anything to our data.
If it ranks our stocks better than our own recipe does, that is worth knowing before any more
effort goes into the recipe. If it does not, a well-funded generic model is a useful floor.

## What it can and cannot show

**The leak, and why these dates avoid it.** Kronos's pre-training data "extends up to June 2024"
(the paper's forecasting setup), and its authors test from July 2024 for that reason. Every label
here is a return realised after 2024-07-01. The context Kronos reads before each test date reaches
back before the cutoff, which is fine: that is input, not answer. The weights on Hugging Face were
last changed on 2025-09-09, so as a stricter check the same analysis is repeated on test dates after
that day only.

**It will very probably not resolve small differences.** Each market has 27 test dates, 21 trading
days apart, so 27 non-overlapping windows. A single window's cross-sectional IC has ranged widely
on this panel ([measurement](../measurement.md#the-seed-is-not-a-sample-of-the-market)); with an
across-window standard deviation around 0.1 the error of a mean is about 0.02, so only gaps of
roughly 0.05 can clear the bound below. The strict window has 12 dates and resolves less.

**It is zero-shot, and one configuration.** Kronos is not fine-tuned, and its settings are fixed
here in advance rather than chosen on these dates, so no picking among configurations happens and
no oracle needs a control. Fine-tuning would be a separate question.

**Survivorship bias applies to every arm alike**: the universe is today's survivors.

## Measure

Per market (XNYS, XJSE, XLON), at test dates every 21 sessions of that market's calendar from the
first session on or after 2024-07-01, through the last whose 21-session forward window has been
recorded (27 per market; the first 2024-07-01, the last 2026-08-26 to 2026-09-04):

- **Members:** the market's active universe members with at least 400 bars on the test date, the
  same set for every arm on that date.
- **Label:** each member's return from the test date's close to the close 21 sessions later on the
  market's calendar. A member without that bar is left out of that date. (Production labels count
  rows instead; sessions are used here so a missing bar cannot stretch a label.)
- **Arms**, each a score per member on the test date, built only from bars stored by the run's
  as-of time and dated on or before the test date:
  1. **Kronos:** Kronos-small (24.7M parameters, revision `901c26c1`) with Kronos-Tokenizer-base
     (revision `0e011738`), both MIT. The last 400 daily bars of open, high, low, close and volume
     (Kronos fills `amount` as volume × mean price); forecast 21 steps; T = 1.0, top_p = 0.9,
     top_k = 0, five sample paths averaged, a fixed random seed per test date. Score: forecast
     close at step 21 over the last close, minus one.
  2. **The recipe:** LightGBM trained exactly as the weekly retrain trains a candidate, on the
     panel built from bars up to the test date (tuning with the market's learning-rate ceiling,
     final fit with the gate's holdout held out, seed 42), predicting the test date's features.
  3. **Momentum:** the standing competitor, `mom_63_cs_rank` on the test date.
  4. **Random:** a seeded random score per member, a negative control.
- **Per arm and date:** the Spearman rank correlation between score and label across members.
- **Per market and comparison:** the mean over dates of the difference between Kronos's IC and the
  other arm's, its Newey-West standard error with lag 1 (`quantpulse.ml.metrics.newey_west_se`),
  and one-sided 95% bounds (mean ± 1.645 × error).

## Decision rule, fixed in advance

Per market:

1. **Kronos ahead of the recipe** if the lower bound on mean(Kronos − recipe) is above 0; **behind**
   if the upper bound is below 0; otherwise **not resolved**. The same reading is made against
   momentum.
2. **Kronos has skill** if the lower bound on its own mean IC is above 0.
3. **Not a clean run** if the random arm's mean IC has a two-sided 95% interval excluding 0: the
   evaluation is then broken, and nothing above is read until it is fixed.

Across markets, read only once all three are in:

- **Ahead of the recipe in at least two markets and behind in none:** start a forward research
  shadow (Kronos scored each week and recorded beside the champion, used by no book), and plan its
  use for after the [shadow run](shadow-run.md)'s verdict, before which nothing that trains
  production may change.
- **Otherwise, skill in at least two markets:** record it. Using Kronos as an input to the recipe
  would be its own pre-registered study after the verdict.
- **Otherwise:** record the null and do not pursue Kronos.

The strict window (test dates after 2025-09-09) is reported beside every figure. If it reverses
the sign of a market's verdict, no action is taken on that market's reading.

## Disclosures

- **Compute and isolation.** Kronos runs on CPU in a throwaway container built from the project
  image plus CPU PyTorch, never in the stack or the production image; its code is read from the
  starred mirror and is not copied into this repository unless it is adopted, with attribution.
  Results, the exact script, the image's package versions and the commit go to
  `~/quantpulse-experiments/`.
- **Timing was measured before this page, and nothing else.** One forecast of all fifty NYSE
  members from 2023-06-01, inside the pre-training window, took 74 s with one sample path and 351 s
  with five; no accuracy figure was computed. That is why five paths, in batches of ten.
- **London is in from the start**, though its live record is days old: every arm here is a backtest
  on its history, which runs to 2018 like the others.

## Results

Not yet measured.
