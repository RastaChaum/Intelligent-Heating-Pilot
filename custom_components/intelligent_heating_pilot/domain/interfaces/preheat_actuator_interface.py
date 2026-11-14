"""Preheat actuator interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..value_objects.actuation_result import ActuationResult
from ..value_objects.cancel_reason import CancelReason
from ..value_objects.scheduled_timeslot import ScheduledTimeslot


class IPreheatActuator(ABC):
    """Contract for starting, cancelling and recovering a preheat for a slot.

    The scheduler decides what happens, when and whether; IHP decides how early. Callers ask
    for "the preheat of this slot" and never learn which integration answers: delegating to a
    scheduler's own run-action command, or driving the climate entity directly, is an
    implementation choice made outside the domain.
    """

    @abstractmethod
    async def start(self, timeslot: ScheduledTimeslot) -> ActuationResult:
        """Start the preheat of a slot.

        Never raises for a scheduler that cannot be actuated: that is ``UNSUPPORTED``.

        Args:
            timeslot: The slot to preheat for.

        Returns:
            What happened: see ``ActuationResult``.
        """

    @abstractmethod
    async def cancel(self, timeslot: ScheduledTimeslot, reason: CancelReason) -> None:
        """Cancel the preheat of a slot and undo what it changed, where that is safe.

        Args:
            timeslot: The slot whose preheat is cancelled.
            reason: Why it is cancelled.
        """

    @abstractmethod
    async def recover(self, next_timeslot: ScheduledTimeslot | None) -> bool:
        """Reconcile a preheat persisted before a restart or reload.

        Idempotent. A preheat for the next slot resumes; one for another or a passed slot is
        cancelled or discarded.

        Args:
            next_timeslot: The slot that is next now, if any.

        Returns:
            True when a preheat is in progress for ``next_timeslot``.
        """
