# ML Test Score audit (2026-08-14)

Scored against the rubric in **"The ML Test Score: A Rubric for ML Production Readiness and
Technical Debt Reduction"** (Breck, Cai, Nielsen, Salib, Sculley — Google, IEEE Big Data
2017): 28 tests in four sections, scored 0 (absent), 0.5 (done manually or documented but
not automated), 1 (automated and repeatable). The final score is the **minimum** of the four
section totals, not the average — the rubric's whole point is that balance matters, and a
system is only as production-ready as its weakest dimension.

> Scored from the rubric's structure as recalled, not from a copy of the paper open at the
> time. The 28 item headings and the scoring bands should be checked against the original
> before this is quoted externally. The per-item evidence below is from the codebase and is
> exact.

**Why this exists.** Seven fault-injection drills on 2026-08-13 found four bugs, and every
one mapped to a documented failure pattern with a known preventive — two root causes
(boundary-value testing, duplicated state) accounted for all of them. Ad-hoc drilling was
rediscovering textbook material at high cost. A published rubric says what to look for
instead of waiting to be surprised, and produces a claim that can be cited.

## Score

| Section | Total | Reading |
|---|---|---|
| Features and Data | 5.0 | Strong — schema, quality gates, tested feature code |
| **Model Development** | **2.5** | **Weakest. Sets the final score.** |
| ML Infrastructure | 5.0 | Strong gate, integration testing and rollback; no canary |
| Monitoring | 6.0 | Strongest — this is where the incident log's lessons went |

**ML Test Score = 2.5** (the minimum), which the rubric reads as *basic productionisation* —
a first pass complete, with real gaps remaining. Was 2.0 at the first scoring; the baseline
gate moved Model Development to 2.5 and the rollback path moved Infrastructure to 5.0.

Note what the second of those did to the headline: **nothing**. Infrastructure went from 4.0
to 5.0 and the score did not move, because Model Development is the binding constraint. That
is the rubric working as designed — it refuses to let strength in one dimension pay for
weakness in another, and it says plainly where the next effort belongs.

The shape is the finding. Monitoring at 6.0 against model development at 2.5 says the
**pipeline around the model has had far more adversarial attention than the model itself**.
That is the direct consequence of how this was built: thirty incidents, almost all of them in
data movement, orchestration and serving, each one hardening the plumbing. Nothing forced
comparable scrutiny onto the modelling.

## Features and Data — 5.0

| # | Test | Score | Evidence |
|---|---|---|---|
| 1 | Feature expectations captured in a schema | 1 | `FEATURE_COLUMNS` + `FEATURE_VERSION`, DB CHECK constraints, 59 dbt data tests, `data/quality.py` |
| 2 | All features are beneficial | 0.5 | `quantpulse ablation` and `quantpulse prune` run drop-one, single-feature and forward-selection sweeps against a floor measured per run. The study exists, but **it is underpowered**: on one holdout the seed-only spread (2 sd 0.0375 / 0.0228) exceeds every effect being tested, so no feature is shown to help or hurt |
| 3 | No feature's cost is too much | 0.5 | All derived from stored OHLCV, vectorized, full recompute ~4s — bounded in practice, never measured per feature |
| 4 | Features meet meta-level requirements | 1 | Market data only, no PII; gitleaks over every staged diff on a public repo |
| 5 | Pipeline has privacy controls | 1 | No personal data exists; loopback-only ports; credentials in `.env` |
| 6 | New features can be added quickly | 0.5 | Vectorized `compute_features` + version bump, but no automated history migration |
| 7 | All input feature code is tested | 1 | `tests/unit/test_features.py` |

## Model Development — 2.5

| # | Test | Score | Evidence |
|---|---|---|---|
| 1 | Model specs reviewed and submitted | 0.5 | `TrainConfig` versioned in git, ADRs recorded; no second reviewer |
| 2 | Offline and online metrics correlate | **0** | The open question. Incident 24 showed stored holdout Sharpe 0.205 re-scoring to 2.570 — offline metrics are known unstable. Live record is 14–18 days, too short to correlate |
| 3 | All hyperparameters tuned | 1 | Optuna TPE, 15 trials, seeded |
| 4 | Impact of model staleness known | **0** | Retrains weekly by schedule, not by measured decay. No experiment relating performance to model age |
| 5 | A simpler model is not better | 0.5 | `quantpulse baseline` runs the comparison, and since 2026-08-14 the promotion gate **enforces** it — no candidate is promoted without beating momentum. Still 0.5, not 1: the property remains violated for the XJSE *incumbent*, and the gate governs promotion, not incumbency |
| 6 | Quality sufficient on important slices | 0.5 | Per-market slices are first-class (own champion, own IC margin, own quantile width); no within-market slices by liquidity, size or volatility regime |
| 7 | Inclusion / fairness | **0** | No protected classes in market data. The honest analogue — does the signal work across liquidity and size tiers, or only in the largest names? — is unmeasured |

## ML Infrastructure — 5.0

| # | Test | Score | Evidence |
|---|---|---|---|
| 1 | Training is reproducible | 0.5 | `seed=42` through LightGBM and Optuna; but the panel grows with each backfill, so the same code on a later day draws a different holdout (incident 24). Deterministic given fixed data, not stable over time |
| 2 | Model specs unit tested | 1 | Promotion gate, CV, metrics and training config all covered |
| 3 | Full pipeline integration tested | 1 | 140 integration tests against a disposable DB running a real `dbt build` |
| 4 | Model quality validated before serving | 1 | The promotion gate — IC margin from measured seed noise, IC ≥ 0, drawdown floor, Sharpe veto, first-champion floor, incumbent re-scored on the candidate's exact holdout. The project's strongest single component |
| 5 | Debuggable on single examples | 0.5 | `/predictions/latest` and the positions endpoint allow inspecting a ticker-date; no dedicated debug path |
| 6 | Canary before serving | **0** | Promotion is an atomic alias switch to 100%. Mitigated by this being a paper book — nothing real is at risk |
| 7 | Quick and safe rollback | 1 | `quantpulse demote --exchange X --reason "…"` (2026-08-14), with `--dry-run`. Writes the audit row and moves the alias in an order that leaves the trail untouched if the registry refuses; falls back to the newest promotion with no later demotion, or clears the alias when there is none |

## Monitoring — 6.0

| # | Test | Score | Evidence |
|---|---|---|---|
| 1 | Dependency changes notify | 1 | Dependabot weekly, grouped, documented major ignores, CI on every PR |
| 2 | Data invariants hold | 1 | `run_quality_checks`, `recent_prices_quality`, `benchmark_freshness`, `option_snapshot_quality`, 59 dbt tests |
| 3 | Training and serving compute the same features | 1 | Structurally identical — one `features` table feeds both paths through the same `FEATURE_COLUMNS`. Skew is impossible by construction rather than checked for |
| 4 | Models are not too stale | 1 | `predictions_are_current` (4-day lag ceiling), drift sensor, weekly retrain |
| 5 | Model numerically stable | 0.5 | NaN never promotes; `dropna` guards on ingest; ratios nulled below 20 days. No explicit NaN/Inf monitoring on prediction output |
| 6 | Computing performance not regressed | 0.5 | `resource_headroom` covers memory and disk; training time and serving latency untracked |
| 7 | Prediction quality not regressed | 1 | Per-market KS/PSI drift, IC-based gate, `fct_signal_performance` quintile readout, live track record |

## Baseline comparison result (2026-08-14)

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

Caveats that belong with the numbers. This is **one holdout window**, and it overlaps the
momentum-rich stretch incident 24 identified (raw 63-day momentum IC +0.039 Mar–Dec 2025,
−0.004 after). One noise draw is not a distribution. Neither observation rescues the JSE
champion — momentum beat it *on the window the gate itself would have used* — but both mean
the right next step is repeating this across several windows before concluding how general it is.

## Feature ablation result (2026-08-22)

`quantpulse ablation` refits without each feature in turn and with each feature alone, on
the same holdout the gate uses. Hyperparameters are held at defaults rather than retuned per
subset, so the "full model" below is a freshly fitted default-parameter model, **not the
champion**. It measures the feature set, not the deployed model.

### The first reading of this was wrong

The sweep was originally judged against each market's `ic_promotion_margin` (0.0060 XNYS,
0.0080 XJSE), and on that basis it was written up as having found the root cause: no feature
carrying signal on the NYSE, eight of thirteen actively costing it, single features scoring
double the full model.

That margin was the wrong yardstick, and the error was not small. It was measured on *tuned*
models selected by the gate. An ablation refits at default parameters, where early stopping
lands on a different tree count for every seed, and the spread under that procedure is far
larger. Measured directly — same panel, same parameters, same holdout, only the seed varied:

| market | seed IC spread (5 seeds) | sd | **2 sd** | margin originally used |
|---|---|---|---|---|
| XNYS | 0.0284 – 0.0726 | 0.0188 | **0.0375** | 0.0060 |
| XJSE | −0.0051 – 0.0250 | 0.0114 | **0.0228** | 0.0080 |

Every delta reported as a finding sat inside that floor. The largest, +0.0361, is below even
the 0.0375 it should have been judged against. The ranked list of "harmful" features was
seed noise, sorted.

`ablation_report` and `forward_select` now measure the floor themselves on each run rather
than borrowing one, and `forward_select` measures a second floor on the inner split, which
is smaller and therefore noisier than the full panel.

### What the corrected sweep shows

Two changes made the sweep able to resolve anything:

1. **Score across walk-forward folds, not one holdout.** A single holdout is one draw. Its
   seed-to-seed spread on this panel was wider than any effect a feature has, so a sweep
   judged on it ranks noise however carefully the margin is set. Averaging over the four
   purged folds shrinks that spread roughly with the square root of the fold count.
2. **Pair every comparison on the seed.** Each subset is scored against the full model
   fitted with the *same* seed, so the seed cancels rather than being carried into the
   comparison. Each feature then gets its own standard error instead of being judged against
   one global floor.

The second mattered more than the first. Fold-averaging alone dropped the floor from 0.0375
to 0.0136 on the NYSE, but it still reported **seven of thirteen** JSE features as
"costing signal" — and pairing showed **none of them** were. `ma_ratio_63` was the headline
of that list at +0.0238; paired across ten seeds it is +0.0032 ± 0.0033 (t +0.97), and its
per-seed differences change sign. The +0.0238 was simply the seed-42 draw, the largest of ten.

**A global floor cannot catch that.** It asks whether a point estimate is large; pairing asks
whether the difference is repeatable. Those come apart exactly when a draw is lucky, which is
the case the whole exercise is trying to detect.

### Results (paired, 4 folds x 10 seeds)

**XNYS** — full-model IC 0.0121. Three features actively hurt, and they are all the
long-horizon ones:

| feature | delta | std err | t | verdict |
|---|---|---|---|---|
| vol_63 | **+0.0234** | 0.0024 | **+9.92** | costs signal |
| ma_ratio_63 | +0.0100 | 0.0033 | +3.06 | costs signal |
| mom_63 | +0.0076 | 0.0029 | +2.60 | costs signal |
| *(other ten)* | −0.0015 to +0.0035 | | \|t\| < 1.7 | within noise |

Dropping `vol_63` alone takes fold-mean IC from 0.0121 to **0.0355**, with all ten seeds
agreeing. Dropping all three together gives +0.0189 (t +4.67) — *less* than dropping
`vol_63` by itself, because the deltas interact and do not add.

**XJSE** — full-model IC 0.0114. No feature costs signal; two carry it:

| feature | delta | std err | t | verdict |
|---|---|---|---|---|
| vol_63 | **−0.0096** | 0.0031 | **−3.12** | carries signal |
| ret_21_cs_rank | −0.0065 | 0.0023 | −2.85 | carries signal |
| *(other eleven)* | −0.0039 to +0.0032 | | \|t\| < 1.6 | within noise |

**The markets disagree about the same feature, strongly and in opposite directions.**
`vol_63` is the most harmful feature on the NYSE (t +9.92) and a genuinely useful one on the
JSE (t −3.12). A single shared feature list cannot be right for both. That is the first
result from this project that argues for a per-market feature set rather than a shared one,
and it is the kind of decision `Exchange` already exists to carry — it holds
`quantile_width` and `ic_promotion_margin` for exactly this reason.

One caveat on `vol_63`: it was singled out *because* it had the largest delta in this
measurement, so that particular figure is selection-inflated. The effect is far too large and
too consistent for selection to explain it away — t +9.92 with ten of ten seeds agreeing,
across four walk-forward folds — but the honest confirmation is a fresh panel period, not a
re-read of this one.

### Pruning, measured rather than inferred

Drop-one deltas do not add up — removing several features that each look costly can land
anywhere, because their effects interact. So `quantpulse prune` *selects* a set and then
*measures* it. Selection runs by walk-forward folds within the training portion only, paired
on the seed exactly as the drop-one sweep is, and a candidate is admitted only when its
improvement repeats. The untouched holdout is used once at the end, also paired across seeds.

| market | selected | pruned IC | full IC | paired delta | momentum |
|---|---|---|---|---|---|
| XNYS | vol_21 | 0.0675 | 0.0484 | **+0.0192** (t +4.20) | 0.0174 |
| XJSE | vol_63, ret_21 | 0.0505 | 0.0180 | **+0.0325** (t +3.84) | 0.1094 |

**A one- or two-feature model beats the thirteen-feature model on data neither had seen**, on
both markets, with the difference measured under matched seeds.

The two methods were built separately and agree. The drop-one sweep found `vol_63` *carries*
signal on the JSE and *costs* it on the NYSE; forward selection, which never reads that
result, picks `vol_63` first on the JSE and never picks it at all on the NYSE. Agreement
between an exclusion test and an inclusion test is the closest thing here to independent
confirmation.

Two things this does not say. The selection still chose among thirteen candidates, so the
identity of the winner is worth less than the size of the gap — a fresh panel period is what
would confirm *which* feature rather than *that* pruning helps. And the JSE's pruned model,
though far better than its full one, still scores 0.0505 against momentum's 0.1094: pruning
improves that market without rescuing it.

### The sweeps hold hyperparameters fixed, and that limits what they can say

Both the drop-one sweep and forward selection train at `DEFAULT_PARAMS`. That is deliberate:
retuning per subset varies two things at once, and the difference could no longer be
attributed to the feature. But it means every result above describes an **untuned** model,
and the deployed model is tuned by Optuna on every retrain.

Measured with tuning in the loop, the pruning benefit disappears:

| market | untuned paired delta | tuned paired delta |
|---|---|---|
| XNYS | +0.0192 (t +4.20) | **+0.0041 ± 0.0038** (t 1.08) |
| XJSE | +0.0325 (t +3.84) | **+0.0009 ± 0.0070** (t 0.13) |

A tuned thirteen-feature model and a tuned one-feature model reach the same IC on the NYSE
(~0.060 each). The tuner finds regularization that absorbs the unhelpful columns, which is
what regularization is for. So "these features hurt" is true *at fixed default parameters*
and does not transfer to the model that actually runs.

`Exchange.feature_columns` exists to carry a per-market list, and both markets are set to
"all" because nothing yet justifies otherwise. Any future feature decision needs evidence
gathered the way the gate trains — with tuning in the loop — not from these sweeps alone.

This does not make the sweeps useless. They still show, robustly, that the feature set is
doing very little work: a single column matches thirteen once either is tuned. It is the
*action* that the evidence does not support, not the diagnosis.

### What actually survives as a finding

Stripping out everything the noise floor now disallows, two results stand:

- **The JSE model has no measurable skill.** Full-model IC 0.0054 ± 0.0114 across seeds —
  indistinguishable from zero — while fit-free momentum scores 0.1094 on the same holdout.
  This agrees with the standing-competitor comparison and is the stronger statement of it.
- **The NYSE model has weak positive skill.** IC 0.0521 ± 0.0188, against momentum's 0.0174.
  Small, noisy, but the model is doing something momentum alone does not.

The earlier conclusion — "the problem is the feature set" — is not supported. The feature
set has not been shown to be the problem or not to be; the measurement was never powerful
enough to say. What can be said is that the JSE model does not beat a one-line rule, which
was already known before this sweep ran.

Making the sweep able to answer the question needs more resolution than one holdout provides:
repeated splits or several walk-forward windows, averaging IC across them so the floor falls
below the effects being tested. That is the prerequisite for any feature decision, and it is
worth more than any change to the current feature list.

## Why nothing can beat the NYSE incumbent (2026-08-23)

Five consecutive retrains were rejected on the NYSE. The incumbent re-scores at **IC 0.1777**
on the shared holdout while every fresh candidate lands near 0.060. The cause is not skill.

**Champion v1 was trained on a different panel from every challenger.** The `features` table
records when each row was written:

| written | covers | rows |
|---|---|---|
| 2026-07-18 | 2023-04-04 → 2026-07-17 | 41,200 |
| 2026-07-20 | 2018-04-04 → 2026-07-20 | 63,000 |

v1 was trained on 2026-07-18, when history began in **2023-04**. Two days later the panel was
backfilled to 2018, roughly tripling it. Every candidate since trains on the long panel.

Reproduced end to end, same hyperparameters throughout:

| trained on | trees | IC on the current holdout |
|---|---|---|
| v1's short panel (2023-04 →) | 25 | **+0.1792** |
| the full panel (2018-04 →) | 21 | +0.0366 |
| *champion v1 itself* | *25* | *+0.1777* |

The short-panel refit matches the champion to within 0.0015 on the same tree count. The
holdout sits immediately after the recent regime, so a model that saw only that regime scores
five times better on it than one diluted by five extra years. **The gate is comparing a
window specialist against generalists, on the specialist's window.**

Three things follow.

1. **The incumbent's advantage is an artifact of when it was trained**, and it will persist
   for as long as v1 holds the alias. This is the promotion stall, fully explained.
2. **The holdout score is not predicting live behaviour.** v1 scores 0.1777 on the backtest
   window and the live book is −1.15% at Sharpe −1.27 over 24 sessions. Whatever the 0.1777
   measures, it is not what the strategy earns.
3. The same backfill already caused one incident: v2 was demoted on 2026-07-25 for being
   "promoted on mismatched holdouts (panel grew 07-20)". The mismatch was corrected for the
   *challenger* and never for the *incumbent*, which is the model the backfill actually
   stranded.

`model_runs` records each run's holdout window but not the span of the panel it trained on,
so nothing in the data would have shown this. Two models fitted to different histories are
not comparable, and the gate has no way to know.

### A second, smaller finding

On the full panel, early stopping fires after **one boosting round** in seven of eight seeds:
the final fit validates on an inner split using RMSE, while the gate scores IC, and RMSE on
noisy 21-day forward returns plateaus immediately. Holding trees fixed, IC peaks near 10–25
trees (0.062) against 0.050 at one tree. So candidates are also being cut short — worth about
0.01 IC, independent of the panel problem above.

## Gaps, ranked by value per unit of effort

1. ~~No simpler-model baseline~~ — **built, and momentum is now a standing competitor in
   the gate (2026-08-14).** No candidate is promoted on either market without beating a
   fit-free momentum rule by the per-market IC margin, first champions included. What
   remains is the *existing* XJSE champion, which loses to momentum and which the gate
   cannot touch: it governs promotion, not incumbency. Withdrawing it is now a single
   command (`quantpulse demote`, built the same day) — but whether to pull it is a judgement
   call, not something the pipeline should make.
2. **Model staleness unmeasured** (Model 4). The weekly retrain cadence is arbitrary. One
   experiment — score a frozen champion forward and watch IC decay — turns it into a
   measurement.
3. ~~No feature ablation~~ — **built and run 2026-08-22; the sweep is underpowered on one
   holdout.** Drop-one, single-feature and forward selection all exist, and all report the
   same thing: the seed-only noise floor (0.0375 XNYS, 0.0228 XJSE) is larger than any
   effect being measured, so nothing survives pruning and nothing is shown to be harmful.
   The next step is not a feature change but more resolution — repeated splits or several
   walk-forward windows, averaged, so the floor drops below the effects. Every feature
   decision waits on that.
4. **Offline/online correlation** (Model 2). Cannot be closed by work, only by time; it is
   what the live track record accrues toward.
5. **No canary** (Infra 6). Genuinely low priority while the book is paper.

## What the rubric does not cover

Three of this week's findings were environmental — a vendor misdating a bar into a gap,
JSE bars publishing two days late, an outage cascade. No rubric predicts vendor behaviour,
and those came from reality rather than review.

One more sits outside it entirely: on 2026-08-13 a wrong inference was written into
`CLAUDE.md` and the data dictionary as guidance, and a change was proposed on top of it that
would have written corrupt data. No checklist catches believing your own bad inference —
only measuring before acting does. Both failure sources are real, and they need different
remedies.
