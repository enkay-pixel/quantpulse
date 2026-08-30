# How to measure things here

Every number in this project is small relative to its own noise. The same mistake has been
made six separate ways, each time by a different route, each time producing a confident
finding that later reversed. These are the rules that would have caught each one.

The sixth reversed two published findings at once and is the reason this page now says the
seed is not a sample of the market — so read that rule as the most recently earned, not the
most settled.

## A noise floor belongs to the procedure that produced it

Do not borrow a threshold. `Exchange.ic_promotion_margin` is two standard deviations of a
seed re-roll on *tuned* models; reused to judge an ablation refitting at default parameters
it is three to six times too small, and every feature clears it. Measure the floor under the
exact procedure being judged, on the same panel, at the same parameters.

A sweep whose floor exceeds the effect it is testing is **underpowered, not a finding**.

## Pair the comparison, do not compare point estimates

Score a variant against its control under the *same* seed, and summarise the differences.
The seed then cancels instead of being carried into the comparison as noise.

This is not a refinement. Judged unpaired against a global floor, a JSE sweep reported seven
of thirteen features as harmful; paired, none were, and the headline one turned out to be a
single lucky draw. A global threshold asks whether an estimate is *large*; pairing asks
whether it *repeats*. Those come apart exactly when a draw is lucky, which is the case worth
detecting.

## Use the error that matches the question

Averaging over seeds measures how much refitting moves a number. It says nothing about how
much the *window* moves it. A staleness curve quoting seed error across single 21-day windows
reported swings of 0.3 as significant decay; the windows were the dominant term, and rolling
the origin was what made the curve readable.

Ask which quantity is varying in the question being asked, and let the error describe that.

### The seed is not a sample of the market

This rule was written after seed error was quoted across single windows, and the fix at the
time was to roll the origin. That was right and it was not enough. The staleness curves rolled
five origins, then pooled 25 (origin, seed) fits into one error bar — which counts each origin
five times, because **re-drawing the fit does not re-draw the market**. The JSE inversion read
as t −3.2 pooled that way and t −1.3 across the five origins, with two of five origins the
opposite sign; at 46 origins it was zero. The NYSE six-week decay went the same way. Both had
stood for a week and both had investigations built on them.

The unit of generalisation is the **window**, not the fit. Concretely:

- Average within an origin first, then take the error across origins. Seeds reduce fit noise
  inside a cell; they do not add sample size.
- A quick check on whether the pooling is lying: compare the spread of the origin means with
  the spread of all the fits. If they are similar, the seeds carry no independent information
  and pooling has inflated n by the seed count.
- Five origins is not enough for anything with this much period-to-period variation. The JSE
  per-origin IC ranges −0.53 to +0.35. Tile the period with a short stride instead of sampling
  a few points in it, and check the autocorrelation of the resulting series rather than
  assuming independence.

One holdout is the degenerate case of the same error, and three findings on this page's
sibling pages were measured on one: seed error on a single window says only how much refitting
moves that window's number.

## An unresolved result is not a null result

Watch the mean as the sample grows. A mean that barely moves while the standard error falls
as the square root of n is a **stable estimate short of resolution**, not an absent effect.
Pruning under tuning read as "no effect" at three seeds and again at eight; at sixteen it
resolved at t +3.00, with the mean having moved by 0.002 the whole time.

Report "not resolved at this sample size, and here is what it would take", never "no effect".

## Never let the answer see the test

An oracle — the best round, the best subset, chosen by looking at the holdout — is not a
baseline any honest rule can reach. It is useful for bounding what is being given up, and
useless as a target. Selection runs on training data; the holdout is read once, at the end.

Related: a holdout read many times stops being out-of-sample in the way it was when it was
new. Prefer a fresh panel period to confirm anything a holdout has already been consulted
about repeatedly.

## Verify a test by breaking the code it guards

A green test proves nothing until it has been seen to fail. Break the guard, watch the test
fail, restore it — and **check the sabotage actually applied**, because a non-matching string
looks exactly like a test that cannot see the bug. More than one test in this repo passed its
first sabotage because it was scanning nothing, or asserting something the bug did not change.

## State when a number was measured, and on what

Panels grow, holdouts slide, and code changes underneath stored metrics. Two models fitted to
different histories are not comparable however carefully they share a holdout. Every figure
here carries its date and its window for that reason.

## Where this came from

- [Feature ablation and pruning](findings/feature-ablation-and-pruning.md)
- [Model staleness](findings/model-staleness.md)
- [Why nothing could beat the NYSE incumbent](findings/unbeatable-incumbent.md)
- [Why the champion has three trees](findings/three-tree-champion.md)
- [Baseline comparison](findings/baseline-comparison.md)
- [Can the round count be chosen well?](findings/round-count.md)
