"""Routing preheat actuator: picks the actuator that serves a scheduler's kind."""

from __future__ import annotations

import logging
from collections.abc import Mapping

from ...domain.interfaces.preheat_actuator_interface import IPreheatActuator
from ...domain.interfaces.scheduler_ownership_resolver_interface import ISchedulerOwnershipResolver
from ...domain.value_objects.actuation_result import ActuationResult
from ...domain.value_objects.cancel_reason import CancelReason
from ...domain.value_objects.scheduled_timeslot import ScheduledTimeslot
from ...domain.value_objects.scheduler_kind import SchedulerKind

_LOGGER = logging.getLogger(__name__)


class RoutingPreheatActuator(IPreheatActuator):
    """Sends each slot to the actuator of its scheduler's kind.

    The table is given by the composition root, which is where the choice of mode lives. A
    kind with no actuator (an unknown scheduler, a native schedule without the opt-in) is
    served as unsupported: the anticipation is computed, nothing is sent, nothing is raised.
    """

    def __init__(
        self,
        resolver: ISchedulerOwnershipResolver,
        actuators: Mapping[SchedulerKind, IPreheatActuator],
    ) -> None:
        """Initialize the router.

        Args:
            resolver: Tells which integration owns a scheduler entity.
            actuators: The actuator of each supported kind.
        """
        self._resolver = resolver
        self._actuators = dict(actuators)

    async def start(self, timeslot: ScheduledTimeslot) -> ActuationResult:
        """Start the preheat with the actuator of the slot's scheduler kind.

        Args:
            timeslot: The slot to preheat for.

        Returns:
            The actuator's result, or ``UNSUPPORTED`` when the kind has none.
        """
        actuator = self._actuator_for(timeslot)
        if actuator is None:
            _LOGGER.debug(
                "Scheduler %s is not actuated: anticipation computed only",
                timeslot.scheduler_entity,
            )
            return ActuationResult.UNSUPPORTED
        return await actuator.start(timeslot)

    async def cancel(self, timeslot: ScheduledTimeslot, reason: CancelReason) -> None:
        """Cancel the preheat with the actuator of the slot's scheduler kind.

        Args:
            timeslot: The slot whose preheat is cancelled.
            reason: Why it is cancelled.
        """
        actuator = self._actuator_for(timeslot)
        if actuator is not None:
            await actuator.cancel(timeslot, reason)

    async def recover(self, next_timeslot: ScheduledTimeslot | None) -> bool:
        """Recover with every distinct actuator; the next slot goes to its owner only.

        Args:
            next_timeslot: The slot that is next now, if any.

        Returns:
            True when an actuator has a preheat in progress for ``next_timeslot``.
        """
        owner = self._actuator_for(next_timeslot) if next_timeslot is not None else None
        in_progress = False
        for actuator in self._distinct_actuators():
            slot = next_timeslot if actuator is owner else None
            in_progress = await actuator.recover(slot) or in_progress
        return in_progress

    def _actuator_for(self, timeslot: ScheduledTimeslot) -> IPreheatActuator | None:
        kind = self._resolver.resolve(timeslot.scheduler_entity)
        return self._actuators.get(kind)

    def _distinct_actuators(self) -> list[IPreheatActuator]:
        distinct: list[IPreheatActuator] = []
        for actuator in self._actuators.values():
            if not any(actuator is seen for seen in distinct):
                distinct.append(actuator)
        return distinct
