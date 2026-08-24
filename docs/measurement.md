# How to measure things here

Every number in this project is small relative to its own noise. The same mistake has been
made five separate ways, each time by a different route, each time producing a confident
finding that later reversed. These are the rules that would have caught each one.

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
