"""Scheduler commander interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime


class ISchedulerCommander(ABC):
    """Contract for scheduler control actions.

    Implementations of this interface execute scheduler commands using
    the scheduler component's run_action service.

    See: https://github.com/nielsfaber/scheduler-component/#schedulerrun_action

    Implementations may treat a scheduler that offers no such action (e.g. a
    native Home Assistant schedule helper) as compute-only: both commands are
    then no-ops and IHP only exposes the computed anticipation.
    """

    @abstractmethod
    async def run_action(self, target_time: datetime, scheduler_entity_id: str) -> bool:
        """Trigger a scheduler action for a specific timeslot.

        This will start heating in the mode configured in the scheduler
        for the timeslot at the given time. Never bypasses the scheduler's
        own conditions (no ``skip_conditions`` override).

        Args:
            target_time: The time of the scheduler timeslot to trigger
            scheduler_entity_id: Scheduler entity ID to control

        Returns:
            ``True`` if an actuation attempt was made on the underlying HACS
            Scheduler (whether or not its conditions ultimately let the
            action through — that is for the caller to verify separately).
            ``False`` for a native HA schedule entity, which is never
            actuated (compute-only).
        """
        pass

    @abstractmethod
    async def cancel_action(self, scheduler_entity_id: str) -> None:
        """Cancel current scheduler action and return to current timeslot.

        This is used to stop overshoot by reverting to the mode configured
        for the current time (now()).
        """
        pass
