"""Unit tests for PreheatSessionPolicy: every rule about applying, restoring and leaving alone."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.intelligent_heating_pilot.domain.constants import (
    PREHEAT_RESTORE_GUARD_MINUTES,
)
from custom_components.intelligent_heating_pilot.domain.services.preheat_session_policy import (
    ApplyDecision,
    PreheatSessionPolicy,
)
from custom_components.intelligent_heating_pilot.domain.value_objects.climate_snapshot import (
    ClimateSnapshot,
)
from custom_components.intelligent_heating_pilot.domain.value_objects.preheat_record import (
    PreheatRecord,
)
from custom_components.intelligent_heating_pilot.domain.value_objects.restore_decision import (
    RestoreDecision,
)
from custom_components.intelligent_heating_pilot.domain.value_objects.slot_action import SlotAction

NOW = datetime(2026, 11, 14, 5, 0, tzinfo=UTC)
PRESETS = ("eco", "comfort", "boost")


def _snapshot(**overrides) -> ClimateSnapshot:
    values = {
        "hvac_mode": "heat",
        "preset": "eco",
        "temperature": 18.0,
        "available_presets": PRESETS,
    }
    values.update(overrides)
    return ClimateSnapshot(**values)


def _record(
    applied: SlotAction | None = None,
    previous: ClimateSnapshot | None = None,
    slot_in=timedelta(hours=2),
):
    return PreheatRecord(
        timeslot_id="switch.plan_slot",
        scheduler_entity="switch.plan",
        slot_time=NOW + slot_in,
        previous=previous or _snapshot(),
        applied=applied or SlotAction(preset="comfort"),
        recorded_at=NOW,
    )


@pytest.fixture
def policy() -> PreheatSessionPolicy:
    return PreheatSessionPolicy()


class TestDecideApply:
    def test_a_slot_is_applied_when_nothing_stops_it(self, policy) -> None:
        assert policy.decide_apply(_snapshot(), SlotAction(preset="comfort")) is ApplyDecision.APPLY

    def test_a_climate_that_is_off_is_left_alone(self, policy) -> None:
        decision = policy.decide_apply(_snapshot(hvac_mode="off"), SlotAction(preset="comfort"))

        assert decision is ApplyDecision.SKIP_OFF

    def test_a_preset_the_climate_does_not_offer_is_not_applied(self, policy) -> None:
        decision = policy.decide_apply(_snapshot(), SlotAction(preset="away"))

        assert decision is ApplyDecision.SKIP_PRESET_UNAVAILABLE

    def test_a_climate_without_presets_cannot_take_a_preset(self, policy) -> None:
        decision = policy.decide_apply(
            _snapshot(available_presets=()), SlotAction(preset="comfort")
        )

        assert decision is ApplyDecision.SKIP_PRESET_UNAVAILABLE

    def test_a_temperature_slot_needs_no_preset(self, policy) -> None:
        decision = policy.decide_apply(
            _snapshot(available_presets=()), SlotAction(temperature=21.0)
        )

        assert decision is ApplyDecision.APPLY

    def test_an_action_already_in_place_is_not_applied_again(self, policy) -> None:
        decision = policy.decide_apply(_snapshot(preset="comfort"), SlotAction(preset="comfort"))

        assert decision is ApplyDecision.SKIP_ALREADY_APPLIED

    def test_off_wins_over_an_unavailable_preset(self, policy) -> None:
        decision = policy.decide_apply(_snapshot(hvac_mode="off"), SlotAction(preset="away"))

        assert decision is ApplyDecision.SKIP_OFF


class TestRestoreFields:
    def test_the_previous_preset_is_restored_when_there_was_one(self, policy) -> None:
        fields = policy.restore_fields(_record(previous=_snapshot(preset="eco", temperature=18.0)))

        assert fields.preset == "eco"
        assert fields.temperature is None

    def test_a_temperature_slot_still_restores_the_previous_preset(self, policy) -> None:
        """A manual setpoint switched the thermostat off its preset; the preset must come back."""
        record = _record(applied=SlotAction(temperature=21.0), previous=_snapshot(preset="eco"))

        assert policy.restore_fields(record).preset == "eco"

    @pytest.mark.parametrize("no_preset", [None, "none", "None"])
    def test_the_previous_temperature_is_restored_when_there_was_no_preset(
        self, policy, no_preset
    ) -> None:
        fields = policy.restore_fields(
            _record(previous=_snapshot(preset=no_preset, temperature=19.0))
        )

        assert fields.preset is None
        assert fields.temperature == 19.0

    def test_nothing_is_restored_when_the_previous_state_had_neither(self, policy) -> None:
        fields = policy.restore_fields(_record(previous=_snapshot(preset=None, temperature=None)))

        assert fields.is_empty


class TestDecideRestore:
    def test_an_untouched_climate_far_from_the_slot_is_restored(self, policy) -> None:
        record = _record()

        decision = policy.decide_restore(record, _snapshot(preset="comfort"), NOW)

        assert decision is RestoreDecision.RESTORE

    def test_a_change_by_another_party_is_left_alone(self, policy) -> None:
        decision = policy.decide_restore(_record(), _snapshot(preset="boost"), NOW)

        assert decision is RestoreDecision.LEAVE

    def test_a_cancellation_inside_the_guard_window_is_a_completion(self, policy) -> None:
        """The scheduler is about to apply the very same action: restoring would undo it."""
        record = _record(slot_in=timedelta(minutes=PREHEAT_RESTORE_GUARD_MINUTES - 1))

        decision = policy.decide_restore(record, _snapshot(preset="comfort"), NOW)

        assert decision is RestoreDecision.DISCARD

    def test_the_guard_window_boundary_is_included(self, policy) -> None:
        record = _record(slot_in=timedelta(minutes=PREHEAT_RESTORE_GUARD_MINUTES))

        assert (
            policy.decide_restore(record, _snapshot(preset="comfort"), NOW)
            is RestoreDecision.DISCARD
        )

    def test_just_outside_the_guard_window_is_restored(self, policy) -> None:
        record = _record(slot_in=timedelta(minutes=PREHEAT_RESTORE_GUARD_MINUTES, seconds=1))

        assert (
            policy.decide_restore(record, _snapshot(preset="comfort"), NOW)
            is RestoreDecision.RESTORE
        )

    def test_a_slot_already_reached_is_discarded(self, policy) -> None:
        record = _record(slot_in=timedelta(minutes=-10))

        assert (
            policy.decide_restore(record, _snapshot(preset="comfort"), NOW)
            is RestoreDecision.DISCARD
        )

    def test_a_climate_switched_off_meanwhile_is_left_alone(self, policy) -> None:
        """Writing a preset to a thermostat somebody turned off would be overriding them."""
        decision = policy.decide_restore(
            _record(), _snapshot(hvac_mode="off", preset="comfort"), NOW
        )

        assert decision is RestoreDecision.LEAVE

    def test_an_unavailable_climate_is_left_alone(self, policy) -> None:
        assert policy.decide_restore(_record(), None, NOW) is RestoreDecision.LEAVE

    def test_the_guard_window_is_configurable(self) -> None:
        policy = PreheatSessionPolicy(restore_guard_minutes=30)
        record = _record(slot_in=timedelta(minutes=20))

        assert (
            policy.decide_restore(record, _snapshot(preset="comfort"), NOW)
            is RestoreDecision.DISCARD
        )

    def test_a_negative_guard_window_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="guard"):
            PreheatSessionPolicy(restore_guard_minutes=-1)


class TestClaimedByOther:
    def test_a_matching_snapshot_is_not_claimed(self, policy) -> None:
        assert not policy.is_claimed_by_other(_record(), _snapshot(preset="comfort"))

    def test_a_different_snapshot_is_claimed(self, policy) -> None:
        assert policy.is_claimed_by_other(_record(), _snapshot(preset="eco"))

    def test_an_unavailable_climate_is_not_claimed(self, policy) -> None:
        assert not policy.is_claimed_by_other(_record(), None)
