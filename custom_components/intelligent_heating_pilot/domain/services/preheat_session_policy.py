"""Preheat session policy: the rules for applying a slot early and undoing it safely.

All rules live here, free of Home Assistant, so that they can be tested on plain values.
The actuators only read the climate, ask this policy, and write what it says.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum

from ..constants import PREHEAT_RESTORE_GUARD_MINUTES
from ..value_objects.climate_snapshot import ClimateSnapshot, is_real_preset
from ..value_objects.preheat_record import PreheatRecord
from ..value_objects.restore_decision import RestoreDecision
from ..value_objects.restore_fields import RestoreFields
from ..value_objects.slot_action import SlotAction, SlotActionKind

OFF_HVAC_MODE = "off"


class ApplyDecision(Enum):
    """Whether, and why not, an action should be applied to the climate."""

    APPLY = "apply"
    SKIP_OFF = "skip_off"
    SKIP_PRESET_UNAVAILABLE = "skip_preset_unavailable"
    SKIP_ALREADY_APPLIED = "skip_already_applied"


class PreheatSessionPolicy:
    """Pure rules for one preheat: apply or skip, restore or leave alone.

    The policy holds no state besides its configuration, so one instance serves every call.
    """

    def __init__(self, restore_guard_minutes: int = PREHEAT_RESTORE_GUARD_MINUTES) -> None:
        """Initialize the policy.

        Args:
            restore_guard_minutes: Delay before a slot within which a cancellation is a
                completion and restores nothing.

        Raises:
            ValueError: If the guard window is negative.
        """
        if restore_guard_minutes < 0:
            raise ValueError("The restore guard window cannot be negative")
        self._restore_guard = timedelta(minutes=restore_guard_minutes)

    def decide_apply(self, snapshot: ClimateSnapshot, action: SlotAction) -> ApplyDecision:
        """Decide whether the action should be applied now.

        A climate that is off is a user's choice. A preset the climate does not offer cannot
        be applied, and turning it into a temperature would break the rule that a preset is
        applied as a preset. An action already in place needs no command and no record.

        Args:
            snapshot: Current requested state of the climate.
            action: The action the slot applies.

        Returns:
            The decision, with the reason when the action is not applied.
        """
        if snapshot.hvac_mode.lower() == OFF_HVAC_MODE:
            return ApplyDecision.SKIP_OFF
        if (
            action.applied_kind is SlotActionKind.PRESET
            and action.preset is not None
            and not snapshot.offers_preset(action.preset)
        ):
            return ApplyDecision.SKIP_PRESET_UNAVAILABLE
        if snapshot.matches(action):
            return ApplyDecision.SKIP_ALREADY_APPLIED
        return ApplyDecision.APPLY

    def restore_fields(self, record: PreheatRecord) -> RestoreFields:
        """Choose what to write back to bring the climate to its earlier state.

        The earlier preset is restored when there was one, whatever IHP applied: a temperature
        slot takes a thermostat off its preset, and the setpoint follows the preset once it is
        back. Only a climate that had no preset gets its earlier temperature back.

        Args:
            record: The record of the preheat to undo.

        Returns:
            The preset or temperature to write; empty when the earlier state held neither.
        """
        previous = record.previous
        if is_real_preset(previous.preset):
            return RestoreFields(preset=previous.preset)
        return RestoreFields(temperature=previous.temperature)

    def decide_restore(
        self, record: PreheatRecord, snapshot: ClimateSnapshot | None, now: datetime
    ) -> RestoreDecision:
        """Decide what to do with the climate when the preheat is cancelled.

        Args:
            record: The record of the preheat to undo.
            snapshot: Current requested state, or None when the climate is unavailable.
            now: Current time (timezone-aware).

        Returns:
            ``DISCARD`` inside the guard window or after the slot, ``LEAVE`` when the climate
            is unavailable, was switched off, or someone else changed it, ``RESTORE`` otherwise.
        """
        if record.slot_time - now <= self._restore_guard:
            return RestoreDecision.DISCARD
        if snapshot is None or self._is_off(snapshot) or self.is_claimed_by_other(record, snapshot):
            return RestoreDecision.LEAVE
        return RestoreDecision.RESTORE

    @staticmethod
    def _is_off(snapshot: ClimateSnapshot) -> bool:
        """A climate switched off is somebody's choice: nothing is written to it."""
        return snapshot.hvac_mode.lower() == OFF_HVAC_MODE

    def is_claimed_by_other(self, record: PreheatRecord, snapshot: ClimateSnapshot | None) -> bool:
        """Tell whether someone else changed the climate after IHP acted.

        Args:
            record: The record of the preheat.
            snapshot: Current requested state, or None when the climate is unavailable.

        Returns:
            True when the state no longer matches what IHP applied. An unavailable climate
            is not a claim.
        """
        if snapshot is None:
            return False
        return not snapshot.matches(record.applied)
