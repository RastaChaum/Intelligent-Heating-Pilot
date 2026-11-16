"""WakeUpTargetPolicy: the fixed target, the schedule's, and every fallback in between."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.intelligent_heating_pilot.domain.services.wake_up_target_policy import (
    WakeUpTargetPolicy,
)
from custom_components.intelligent_heating_pilot.domain.value_objects import (
    ScheduledTimeslot,
    SlotAction,
    SlotsAround,
    WakeUpSourceConfig,
)

NOW = datetime(2026, 11, 16, 5, 30, tzinfo=UTC)
FIXED = SlotAction(preset="eco")
FROM_SCHEDULE = WakeUpSourceConfig("sensor.alarm", fixed_target=FIXED, target_from_schedule=True)
FROM_SCHEDULE_ONLY = WakeUpSourceConfig("sensor.alarm", target_from_schedule=True)
FIXED_ONLY = WakeUpSourceConfig("sensor.alarm", fixed_target=FIXED)
COMFORT = SlotAction(preset="comfort")
BOOST = SlotAction(preset="boost")


def _slot(action: SlotAction | None, temperature: float, at_hours: int = 1) -> ScheduledTimeslot:
    return ScheduledTimeslot(
        target_time=NOW + timedelta(hours=at_hours),
        target_temp=temperature,
        timeslot_id=f"slot_{temperature}",
        scheduler_entity="schedule.plan",
        action=action,
    )


@pytest.fixture
def policy() -> WakeUpTargetPolicy:
    return WakeUpTargetPolicy()


def test_a_fixed_source_ignores_the_schedule(policy: WakeUpTargetPolicy) -> None:
    slots = SlotsAround(following=_slot(BOOST, 23.0))

    assert policy.resolve(FIXED_ONLY, slots, reference_target=17.0) == FIXED


def test_both_slots_known_the_higher_wins(policy: WakeUpTargetPolicy) -> None:
    in_effect, following = _slot(COMFORT, 21.0, -2), _slot(SlotAction(preset="eco"), 18.0)

    chosen = policy.resolve(FROM_SCHEDULE, SlotsAround(in_effect, following), reference_target=21.0)

    assert chosen == COMFORT


def test_both_slots_known_the_following_wins_when_it_is_higher(policy: WakeUpTargetPolicy) -> None:
    in_effect, following = _slot(SlotAction(preset="eco"), 18.0, -2), _slot(BOOST, 23.0)

    assert policy.resolve(FROM_SCHEDULE, SlotsAround(in_effect, following), 18.0) == BOOST


def test_equal_temperatures_take_the_following_slot(policy: WakeUpTargetPolicy) -> None:
    in_effect, following = _slot(COMFORT, 21.0, -2), _slot(SlotAction(temperature=21.0), 21.0)

    assert (
        policy.resolve(FROM_SCHEDULE, SlotsAround(in_effect, following), 17.0) == following.action
    )


def test_both_known_the_reference_is_not_needed(policy: WakeUpTargetPolicy) -> None:
    slots = SlotsAround(_slot(COMFORT, 21.0, -2), _slot(BOOST, 23.0))

    assert policy.resolve(FROM_SCHEDULE, slots, reference_target=None) == BOOST


def test_a_single_following_slot_higher_than_the_reference_is_used(
    policy: WakeUpTargetPolicy,
) -> None:
    assert (
        policy.resolve(FROM_SCHEDULE, SlotsAround(following=_slot(COMFORT, 21.0)), 17.0) == COMFORT
    )


@pytest.mark.parametrize("reference", [21.0, 22.0])
def test_a_single_slot_not_higher_than_the_reference_falls_back(
    policy: WakeUpTargetPolicy, reference: float
) -> None:
    slots = SlotsAround(following=_slot(COMFORT, 21.0))

    assert policy.resolve(FROM_SCHEDULE, slots, reference) == FIXED


def test_a_single_slot_with_an_unknown_reference_falls_back(policy: WakeUpTargetPolicy) -> None:
    slots = SlotsAround(following=_slot(COMFORT, 21.0))

    assert policy.resolve(FROM_SCHEDULE, slots, reference_target=None) == FIXED


def test_a_single_in_effect_slot_follows_the_same_rule(policy: WakeUpTargetPolicy) -> None:
    slots = SlotsAround(in_effect=_slot(COMFORT, 21.0, -2))

    assert policy.resolve(FROM_SCHEDULE, slots, reference_target=17.0) == COMFORT
    assert policy.resolve(FROM_SCHEDULE, slots, reference_target=21.5) == FIXED


def test_no_slot_falls_back_to_the_fixed_target(policy: WakeUpTargetPolicy) -> None:
    assert policy.resolve(FROM_SCHEDULE, SlotsAround(), reference_target=17.0) == FIXED


def test_no_slot_and_no_fixed_target_gives_nothing(policy: WakeUpTargetPolicy) -> None:
    assert policy.resolve(FROM_SCHEDULE_ONLY, SlotsAround(), reference_target=17.0) is None


def test_a_slot_without_an_action_cannot_give_a_target(policy: WakeUpTargetPolicy) -> None:
    """A schedule IHP does not drive may give a slot with no action to apply."""
    slots = SlotsAround(following=_slot(None, 21.0))

    assert policy.resolve(FROM_SCHEDULE, slots, reference_target=17.0) == FIXED
    assert policy.resolve(FROM_SCHEDULE_ONLY, slots, reference_target=17.0) is None


def test_an_unusable_in_effect_slot_leaves_the_following_one_alone(
    policy: WakeUpTargetPolicy,
) -> None:
    slots = SlotsAround(in_effect=_slot(None, 25.0, -2), following=_slot(COMFORT, 21.0))

    assert policy.resolve(FROM_SCHEDULE, slots, reference_target=17.0) == COMFORT
    assert policy.resolve(FROM_SCHEDULE, slots, reference_target=21.0) == FIXED
