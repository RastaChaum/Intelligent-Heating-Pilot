"""Unit tests for HeatingCycle value object — avg_heating_slope with min_effective_duration filter.

These tests validate the guard introduced to prevent aberrant slope values (e.g. 140 000 °C/h)
that arise when dead_time_cycle ≈ total_duration, leaving an effective heating window
of near-zero duration as denominator.

Feature: HeatingCycle.avg_heating_slope — min_effective_duration_minutes filter
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from custom_components.intelligent_heating_pilot.domain.value_objects.heating import HeatingCycle

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

BASE_TIME = datetime(2024, 1, 15, 7, 0, 0)


def make_cycle(
    total_duration_minutes: float,
    dead_time_minutes: float | None,
    temp_increase: float = 2.0,
    min_effective_duration_minutes: float = 5.0,
    start_temp: float = 18.0,
    dead_time_end_temp: float | None = None,
) -> HeatingCycle:
    """Create a HeatingCycle with the given parameters.

    Args:
        total_duration_minutes: Total cycle duration (start → end).
        dead_time_minutes: Dead time in minutes, or None if unknown.
        temp_increase: Temperature rise over the cycle (°C). Default 2.0.
        min_effective_duration_minutes: Guard threshold. Default 5.0.
        start_temp: Starting indoor temperature. Default 18.0.
        dead_time_end_temp: Temperature when the dead time ended, or None if not recorded.

    Returns:
        An immutable HeatingCycle value object.
    """
    return HeatingCycle(
        device_id="climate.test_vtherm",
        start_time=BASE_TIME,
        end_time=BASE_TIME + timedelta(minutes=total_duration_minutes),
        target_temp=start_temp + temp_increase + 0.5,
        start_temp=start_temp,
        end_temp=start_temp + temp_increase,
        tariff_details=None,
        dead_time_cycle_minutes=dead_time_minutes,
        min_effective_duration_minutes=min_effective_duration_minutes,
        dead_time_end_temp=dead_time_end_temp,
    )


# ---------------------------------------------------------------------------
# TestHeatingCycleAvgHeatingSlope
# ---------------------------------------------------------------------------


class TestHeatingCycleAvgHeatingSlope:
    """Validate that avg_heating_slope respects the min_effective_duration_minutes guard.

    GREEN: The skeleton implementation is complete — all tests in this class are expected
    to PASS with the current code.
    """

    def test_nominal_slope_with_dead_time_excluded(self) -> None:
        """Slope is calculated on the effective window (total − dead_time).

        Given: total=30 min, dead_time=10 min ending at 18.5 °C, min_eff=5 min
        Effective duration = 30 − 10 = 20 min = 1/3 h
        Rise after the dead time = 20.0 − 18.5 = 1.5 °C → slope = 4.5 °C/h.
        """
        cycle = make_cycle(
            total_duration_minutes=30.0, dead_time_minutes=10.0, dead_time_end_temp=18.5
        )

        slope = cycle.avg_heating_slope

        assert slope != 0.0, "Nominal case should return a non-zero slope"
        assert slope == pytest.approx(4.5, rel=1e-4)

    def test_bug_scenario_dead_time_equals_total_duration_returns_zero(self) -> None:
        """THE BUG SCENARIO: slope must be 0.0 when effective duration ≈ 0.

        A safety shutoff can produce a cycle where dead_time ≈ total_duration,
        leaving an effective window of ~ 0. Without the guard, the slope
        formula amplifies noise to tens-of-thousands °C/h.

        Given: total=14.20 min, dead_time=14.10 min, min_eff=5 min
        Effective duration = 0.10 min < 5 min → slope must be 0.0.

        # FAILS with buggy code (no guard → ~1200 °C/h returned for 2°C rise)
        # PASSES with fix (guard returns 0.0)
        """
        # Safety shutoff: heating started but cut almost immediately
        cycle = make_cycle(
            total_duration_minutes=14.20,
            dead_time_minutes=14.10,
            temp_increase=2.0,  # Without guard this would give ~1200 °C/h
            min_effective_duration_minutes=5.0,
        )

        assert cycle.avg_heating_slope == 0.0, (
            "When effective duration < min_effective_duration_minutes, "
            "avg_heating_slope must return 0.0 to prevent aberrant values"
        )

    def test_exact_boundary_effective_equals_min_slope_is_computed(self) -> None:
        """At the exact boundary (eff == min_eff), slope should be computed (not filtered).

        Given: total=14 min, dead_time=9 min ending at 18.2 °C, min_eff=5 min
        Effective duration = 5 min == min_eff → NOT filtered (condition is strict <)
        Slope = (20.0 − 18.2) / (5/60) = 21.6 °C/h (non-zero).

        # PASSES with fix (boundary is inclusive: eff >= min is allowed)
        """
        cycle = make_cycle(
            total_duration_minutes=14.0,
            dead_time_minutes=9.0,
            min_effective_duration_minutes=5.0,
            dead_time_end_temp=18.2,
        )

        slope = cycle.avg_heating_slope

        assert slope != 0.0, "At exact boundary (eff == min_eff), slope must be computed"
        assert slope == pytest.approx(21.6, rel=1e-3)

    def test_just_below_boundary_returns_zero(self) -> None:
        """Just below the boundary (eff < min_eff), slope must be 0.0.

        Given: total=14 min, dead_time=9.1 min, min_eff=5 min
        Effective duration = 4.9 min < 5 min → filtered → slope=0.0.

        # FAILS with buggy code (no guard)
        # PASSES with fix
        """
        cycle = make_cycle(
            total_duration_minutes=14.0,
            dead_time_minutes=9.1,
            min_effective_duration_minutes=5.0,
        )

        assert cycle.avg_heating_slope == 0.0

    def test_no_dead_time_uses_total_duration(self) -> None:
        """When dead_time_cycle_minutes is None, total duration is used for slope.

        Given: total=30 min, dead_time=None, min_eff=5 min
        Effective duration = 30 min >> 5 min → slope computed normally.
        Slope = 2.0 / (30/60) = 4.0 °C/h.

        # PASSES with fix
        """
        cycle = make_cycle(
            total_duration_minutes=30.0,
            dead_time_minutes=None,
            temp_increase=2.0,
        )

        assert cycle.avg_heating_slope == pytest.approx(4.0, rel=1e-4)

    def test_default_min_effective_duration_is_five_minutes(self) -> None:
        """HeatingCycle without explicit min_effective_duration_minutes defaults to 5.0.

        # PASSES with fix (field default = 5.0 in dataclass)
        """
        cycle = HeatingCycle(
            device_id="climate.test",
            start_time=BASE_TIME,
            end_time=BASE_TIME + timedelta(minutes=30),
            target_temp=21.0,
            start_temp=18.0,
            end_temp=20.0,
            tariff_details=None,
            dead_time_cycle_minutes=None,
            # min_effective_duration_minutes NOT provided → should default to 5.0
        )

        assert cycle.min_effective_duration_minutes == 5.0

    def test_zero_temp_increase_returns_zero_slope(self) -> None:
        """A cycle with no temperature rise produces slope=0.0 regardless of duration.

        This is not related to the guard but is a useful baseline assertion.
        """
        cycle = make_cycle(
            total_duration_minutes=30.0,
            dead_time_minutes=None,
            temp_increase=0.0,
        )

        assert cycle.avg_heating_slope == 0.0


# ---------------------------------------------------------------------------
# TestHeatingCycleSlopeFromDeadTimeEnd (#245)
# ---------------------------------------------------------------------------


class TestHeatingCycleSlopeFromDeadTimeEnd:
    """The slope measures the rise after the dead time, over the time after it (#245).

    The rise during the dead time (at least 0.2 °C by definition) belongs to the dead
    time: counting it in a window that excludes the dead time overestimated the slope.
    """

    def test_rise_during_dead_time_is_not_counted(self) -> None:
        """18.0 → 19.8 °C over 138 min, dead time 42 min ending at 18.2 °C → 1.0 °C/h."""
        cycle = make_cycle(
            total_duration_minutes=138.0,
            dead_time_minutes=42.0,
            temp_increase=1.8,
            dead_time_end_temp=18.2,
        )

        assert cycle.avg_heating_slope == pytest.approx(1.0)

    def test_cached_cycle_without_dead_time_end_temp_falls_back_to_threshold(self) -> None:
        """Cycles cached before the temperature was recorded assume start + 0.2 °C.

        By definition the dead time ends once the room gained 0.2 °C.
        """
        cycle = make_cycle(
            total_duration_minutes=138.0,
            dead_time_minutes=42.0,
            temp_increase=1.8,
            dead_time_end_temp=None,
        )

        assert cycle.avg_heating_slope == pytest.approx(1.0)

    def test_dead_time_end_temp_ignored_without_dead_time(self) -> None:
        """Without a dead time, the slope stays measured from the cycle start."""
        cycle = make_cycle(
            total_duration_minutes=60.0,
            dead_time_minutes=None,
            temp_increase=1.0,
            dead_time_end_temp=18.5,
        )

        assert cycle.avg_heating_slope == pytest.approx(1.0)

    def test_heating_phase_starts_at_dead_time_end(self) -> None:
        """The heating phase begins when the dead time ends, at its recorded temperature."""
        cycle = make_cycle(
            total_duration_minutes=138.0, dead_time_minutes=42.0, dead_time_end_temp=18.3
        )

        assert cycle.heating_phase_start_time == BASE_TIME + timedelta(minutes=42)
        assert cycle.heating_phase_start_temp == 18.3

    def test_heating_phase_starts_with_cycle_without_dead_time(self) -> None:
        """Without a dead time, the heating phase is the whole cycle."""
        cycle = make_cycle(total_duration_minutes=60.0, dead_time_minutes=None)

        assert cycle.heating_phase_start_time == BASE_TIME
        assert cycle.heating_phase_start_temp == 18.0

    def test_dead_time_end_temp_defaults_to_none(self) -> None:
        """Cycles built without it (cache from older versions) have no recorded value."""
        cycle = make_cycle(total_duration_minutes=60.0, dead_time_minutes=10.0)

        assert cycle.dead_time_end_temp is None
