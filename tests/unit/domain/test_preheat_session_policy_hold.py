"""PreheatSessionPolicy.decide_hold_end: what happens to the thermostat when a hold ends."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from custom_components.intelligent_heating_pilot.domain.services.preheat_session_policy import (
    PreheatSessionPolicy,
)
from custom_components.intelligent_heating_pilot.domain.value_objects import (
    ClimateSnapshot,
    PreheatRecord,
    RestoreDecision,
    SlotAction,
)

NOW = datetime(2026, 11, 16, 8, 0, tzinfo=UTC)
PRESETS = ("eco", "comfort", "boost")
COMFORT = ClimateSnapshot("heat", "comfort", 21.0, PRESETS)


def _record(**overrides) -> PreheatRecord:
    values = {
        "timeslot_id": "sensor.alarm_2026-11-16",
        "scheduler_entity": "sensor.alarm",
        "slot_time": NOW - timedelta(minutes=90),
        "previous": ClimateSnapshot("heat", "eco", 17.0, PRESETS),
        "applied": SlotAction(preset="comfort"),
        "recorded_at": NOW - timedelta(hours=4),
        "hold_until": NOW,
    }
    values.update(overrides)
    return PreheatRecord(**values)


@pytest.fixture
def policy() -> PreheatSessionPolicy:
    return PreheatSessionPolicy()


def test_an_untouched_thermostat_is_restored(policy: PreheatSessionPolicy) -> None:
    assert policy.decide_hold_end(_record(), COMFORT) is RestoreDecision.RESTORE


def test_the_guard_window_of_a_cancellation_does_not_apply(policy: PreheatSessionPolicy) -> None:
    """The deadline passed on purpose: the end of the hold restores even right after it."""
    record = _record(slot_time=NOW - timedelta(minutes=1))

    assert policy.decide_hold_end(record, COMFORT) is RestoreDecision.RESTORE


def test_a_change_by_someone_else_is_left_alone(policy: PreheatSessionPolicy) -> None:
    changed = ClimateSnapshot("heat", "boost", 23.0, PRESETS)

    assert policy.decide_hold_end(_record(), changed) is RestoreDecision.LEAVE


def test_a_switched_off_thermostat_is_left_alone(policy: PreheatSessionPolicy) -> None:
    off = replace(COMFORT, hvac_mode="off")

    assert policy.decide_hold_end(_record(), off) is RestoreDecision.LEAVE


def test_an_unavailable_climate_is_left_alone(policy: PreheatSessionPolicy) -> None:
    assert policy.decide_hold_end(_record(), None) is RestoreDecision.LEAVE


def test_a_scheduler_handoff_restores_nothing_even_when_it_applied_the_same_action(
    policy: PreheatSessionPolicy,
) -> None:
    """A scheduler applying the same preset looks untouched: only the handoff tells."""
    record = _record(hold_handoff=True)

    assert policy.decide_hold_end(record, COMFORT) is RestoreDecision.DISCARD
    assert policy.decide_hold_end(record, None) is RestoreDecision.DISCARD
