"""Wake-up target policy: which action a wake-up source asks the thermostat for."""

from __future__ import annotations

from ..value_objects.scheduled_timeslot import ScheduledTimeslot
from ..value_objects.slot_action import SlotAction
from ..value_objects.slots_around import SlotsAround
from ..value_objects.wake_up_source_config import WakeUpSourceConfig


class WakeUpTargetPolicy:
    """Chooses the target of a wake-up source: its fixed one, or the schedule's.

    "From the schedule" takes the higher of the slot in effect and the slot that follows the
    wake-up time, so the target is never lower than what the schedule already asks for. When
    a scheduler can only show one of them, that one is used only if it is higher than the
    thermostat's current target: a following slot that is lower would otherwise lower a room
    that is already heated. Whatever the schedule cannot settle falls back to the fixed
    target. The policy holds no state.
    """

    def resolve(
        self,
        config: WakeUpSourceConfig,
        slots: SlotsAround,
        reference_target: float | None,
    ) -> SlotAction | None:
        """Choose the action a source asks for.

        Args:
            config: The source.
            slots: The schedule slots around the wake-up time.
            reference_target: The thermostat's target before IHP acted: its current one, or
                the one recorded before the preheat while it runs. None when unknown.

        Returns:
            The action to apply and reach, or None when the source has no usable target.
        """
        if config.target_from_schedule:
            from_schedule = self._from_schedule(slots, reference_target)
            if from_schedule is not None:
                return from_schedule
        return config.fixed_target

    @staticmethod
    def _usable(slot: ScheduledTimeslot | None) -> ScheduledTimeslot | None:
        """A slot without an action cannot be applied, so it cannot give a target."""
        return slot if slot is not None and slot.action is not None else None

    def _from_schedule(
        self, slots: SlotsAround, reference_target: float | None
    ) -> SlotAction | None:
        in_effect = self._usable(slots.in_effect)
        following = self._usable(slots.following)
        if in_effect is not None and following is not None:
            higher = following if following.target_temp >= in_effect.target_temp else in_effect
            return higher.action
        single = in_effect or following
        if single is None or reference_target is None:
            return None
        return single.action if single.target_temp > reference_target else None
