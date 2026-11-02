"""Unit tests for the shared rule deciding which cycles are learned from (#223, #255).

A cycle extracted with a known learning status is learned when it was not disturbed,
warmed the room, and has a positive heating slope, however slow (#255). A cycle cached
before that status was recorded keeps the former rule: a slope of at least
LEGACY_MINIMUM_REALISTIC_LHS.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from custom_components.intelligent_heating_pilot.domain.constants import (
    LEGACY_MINIMUM_REALISTIC_LHS,
)
from custom_components.intelligent_heating_pilot.domain.services.learning_cycle_filter import (
    filter_realistic_cycles,
    is_realistic_learning_cycle,
    is_usable_lhs,
)
from custom_components.intelligent_heating_pilot.domain.value_objects.heating import HeatingCycle
from tests.unit.domain.fixtures import create_test_heating_cycle, get_test_datetime

DEVICE_ID = "climate.test_vtherm"


def _legacy_cycle(slope: float) -> HeatingCycle:
    """A one-hour cycle cached before its learning status was recorded."""
    return create_test_heating_cycle(DEVICE_ID, get_test_datetime(), temp_increase=slope)


def _cycle(
    slope: float, disturbed: bool = False, heating_phase_observed: bool = True
) -> HeatingCycle:
    """A one-hour cycle extracted with a known learning status."""
    return replace(
        _legacy_cycle(slope), disturbed=disturbed, heating_phase_observed=heating_phase_observed
    )


class TestCyclesWithKnownStatus:
    """Cycles extracted since #255: explicit signals decide, not the speed."""

    def test_slow_undisturbed_cycle_is_learned(self) -> None:
        """A genuinely slow room (0.05 °C/h) is learned from."""
        assert is_realistic_learning_cycle(_cycle(0.05))

    def test_disturbed_cycle_is_not_learned_however_fast(self) -> None:
        """Safety mode or load shedding excludes the cycle, whatever its slope."""
        assert not is_realistic_learning_cycle(_cycle(3.0, disturbed=True))

    def test_cycle_that_never_warmed_the_room_is_not_learned(self) -> None:
        """Without a heating phase, the slope measured from the start is not learned."""
        assert not is_realistic_learning_cycle(_cycle(0.6, heating_phase_observed=False))

    @pytest.mark.parametrize("slope", [0.0, -0.3])
    def test_non_positive_slope_is_not_learned(self, slope: float) -> None:
        """A cycle that did not heat after its dead time carries no learning data."""
        assert not is_realistic_learning_cycle(_cycle(slope))


class TestCyclesCachedBeforeTheStatus:
    """Cycles cached before #255 keep the former speed floor."""

    def test_cycle_at_legacy_minimum_is_kept(self) -> None:
        """A slope exactly at LEGACY_MINIMUM_REALISTIC_LHS is still learned."""
        start_time = get_test_datetime()
        # Start from 0 so the slope is exactly the threshold (no float rounding)
        cycle = HeatingCycle(
            device_id=DEVICE_ID,
            start_time=start_time,
            end_time=start_time + timedelta(hours=1),
            target_temp=LEGACY_MINIMUM_REALISTIC_LHS,
            end_temp=LEGACY_MINIMUM_REALISTIC_LHS,
            start_temp=0.0,
        )

        assert is_realistic_learning_cycle(cycle)

    def test_cycle_below_legacy_minimum_is_rejected(self) -> None:
        """Its disturbance is unknown, so a slow cycle may be a #223 safety-mode cycle."""
        assert not is_realistic_learning_cycle(_legacy_cycle(LEGACY_MINIMUM_REALISTIC_LHS - 0.05))

    def test_cycle_without_dead_time_is_kept_as_before(self) -> None:
        """The heating phase is unknown too, so the former rule applies unchanged."""
        assert is_realistic_learning_cycle(_legacy_cycle(0.3))

    @pytest.mark.parametrize("slope", [0.0, -1.0])
    def test_non_positive_cycles_are_rejected(self, slope: float) -> None:
        """Cycles where temperature did not rise carry no learning data."""
        assert not is_realistic_learning_cycle(_legacy_cycle(slope))

    def test_partially_known_status_uses_the_former_rule(self) -> None:
        """A status with one side missing is not trusted."""
        cycle = replace(_legacy_cycle(0.1), disturbed=False)

        assert not is_realistic_learning_cycle(cycle)


def test_filter_keeps_only_learnable_cycles_in_order() -> None:
    """Filtering keeps learnable cycles and preserves their order."""
    fast = _legacy_cycle(3.0)
    slow_legacy = _legacy_cycle(0.1)
    slow = _cycle(0.1)
    disturbed = _cycle(1.0, disturbed=True)
    medium = _legacy_cycle(1.0)

    assert filter_realistic_cycles([fast, slow_legacy, slow, disturbed, medium]) == [
        fast,
        slow,
        medium,
    ]


def test_filter_empty_list_returns_empty_list() -> None:
    """No cycles in, no cycles out."""
    assert filter_realistic_cycles([]) == []


class TestUsableLearnedSlope:
    """A learned LHS is usable when strictly positive, however slow (#255)."""

    @pytest.mark.parametrize("lhs", [0.05, 0.15, 2.0])
    def test_positive_slope_is_usable(self, lhs: float) -> None:
        """A slow room keeps its own slope instead of the default."""
        assert is_usable_lhs(lhs)

    @pytest.mark.parametrize("lhs", [None, 0.0, -0.2])
    def test_missing_or_non_positive_slope_is_not_usable(self, lhs: float | None) -> None:
        """Such a slope would make the anticipation infinite or negative."""
        assert not is_usable_lhs(lhs)
