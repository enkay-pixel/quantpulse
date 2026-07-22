"""Headroom checks must fire early enough to act on and stay quiet otherwise — a monitor
that cries wolf gets ignored, which is worse than not having it."""

from quantpulse.monitoring.resources import (
    DATABASE_CEILING_BYTES,
    MIN_RUNWAY_DAYS,
    Breach,
    ResourceReport,
    check_headroom,
)

GB = 1024**3


def report(**overrides: object) -> ResourceReport:
    base = {
        "database_bytes": {"market": 180 * 1024**2, "dagster": 12 * 1024**2},
        "market_rows": {"features": 104250},
        "bytes_per_day": 8.0 * 1024**2,
        "runway_days": 2500.0,
        "memory_used_bytes": 269 * 1024**2,
        "memory_limit_bytes": 384 * 1024**2,
    }
    return ResourceReport(**{**base, **overrides})  # type: ignore[arg-type]


def test_healthy_stack_reports_nothing() -> None:
    assert check_headroom(report()) == []


def test_short_runway_is_flagged_with_the_number_in_it() -> None:
    breaches = check_headroom(report(runway_days=30.0))
    assert [b.name for b in breaches] == ["database_runway"]
    assert "30 days" in breaches[0].detail


def test_runway_floor_is_inclusive_of_headroom() -> None:
    """Exactly at the floor is still fine; one day under is not."""
    assert check_headroom(report(runway_days=float(MIN_RUNWAY_DAYS))) == []
    assert check_headroom(report(runway_days=MIN_RUNWAY_DAYS - 1.0))


def test_memory_pressure_names_the_remedy() -> None:
    breaches = check_headroom(report(memory_used_bytes=370 * 1024**2))
    assert [b.name for b in breaches] == ["memory_pressure"]
    assert "docker-compose.yml" in breaches[0].detail


def test_unknown_memory_is_not_treated_as_pressure() -> None:
    """Off Linux there is no cgroup to read; absence must not look like a breach."""
    assert check_headroom(report(memory_used_bytes=None, memory_limit_bytes=None)) == []


def test_breaches_accumulate_rather_than_short_circuit() -> None:
    breaches = check_headroom(report(runway_days=5.0, memory_used_bytes=380 * 1024**2))
    assert {b.name for b in breaches} == {"database_runway", "memory_pressure"}


def test_memory_fraction_is_none_without_a_limit() -> None:
    assert report(memory_limit_bytes=None).memory_fraction is None
    assert report().memory_fraction == 269 / 384


def test_ceiling_is_generous_enough_to_be_a_denominator_not_a_wall() -> None:
    """Guards the intent: the ceiling exists to convert growth into runway. If someone
    lowers it near current usage, the check becomes a permanent alarm."""
    assert DATABASE_CEILING_BYTES >= 10 * GB


def test_breach_is_hashable_and_comparable() -> None:
    assert Breach("a", "b") == Breach("a", "b")
