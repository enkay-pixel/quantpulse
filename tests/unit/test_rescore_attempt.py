"""How often a session scored before its late bars arrived may be re-scored.

The late-bars sensor asks for a second scoring pass when bars land after their session was
scored. Like every "re-run until X appears" trigger here it needs a bound: a listing whose
features cannot be computed yet would otherwise ask again on every tick, forever.
"""

from quantpulse.orchestration.catchup import MAX_RESCORES_PER_SESSION, rescore_attempt


def test_the_first_rescore_is_attempt_one() -> None:
    assert rescore_attempt(17, []) == 1


def test_nothing_unscored_asks_for_nothing() -> None:
    assert rescore_attempt(0, []) is None


def test_waits_while_a_rescore_is_in_flight() -> None:
    """One run serves every market; a second beside it would only queue behind it."""
    assert rescore_attempt(17, [("QUEUED", "17")]) is None
    assert rescore_attempt(17, [("STARTED", "17")]) is None


def test_more_late_bars_after_a_rescore_ask_again() -> None:
    """New York's 2026-10-23 arrived in four batches: a pass after the third leaves the
    fourth's names to a later one."""
    assert rescore_attempt(2, [("SUCCESS", "15")]) == 2


def test_a_pass_that_scored_nothing_new_is_not_repeated() -> None:
    """Same count after a successful pass: those listings cannot be scored yet, and another
    pass would not change that."""
    assert rescore_attempt(2, [("SUCCESS", "15"), ("SUCCESS", "2")]) is None


def test_a_failed_pass_is_retried_within_the_bound() -> None:
    assert rescore_attempt(17, [("FAILURE", "17")]) == 2
    failures = [("FAILURE", "17")] * MAX_RESCORES_PER_SESSION
    assert rescore_attempt(17, failures) is None
