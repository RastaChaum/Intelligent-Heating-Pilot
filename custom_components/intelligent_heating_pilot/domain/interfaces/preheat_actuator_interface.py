"""Preheat actuator interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from datetime import datetime

from ..value_objects.actuation_result import ActuationResult
from ..value_objects.cancel_reason import CancelReason
from ..value_objects.preheat_recovery import PreheatRecovery
from ..value_objects.scheduled_timeslot import ScheduledTimeslot

# Gives the next timeslot of one scheduler, or None when it has none or cannot be read
NextTimeslotOf = Callable[[str], Awaitable[ScheduledTimeslot | None]]


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
    async def recover(self, next_timeslot_of: NextTimeslotOf) -> PreheatRecovery:
        """Reconcile a preheat persisted before a restart or reload.

        Idempotent. The recorded slot is compared with the next slot of ITS OWN scheduler: a
        slot that is still next resumes the preheat; another slot, or a slot already reached,
        releases it. When the scheduler cannot answer, nothing is decided and the result says to
        ask again: deciding on a missing answer could undo a preheat that is still valid.

        Args:
            next_timeslot_of: Gives the next timeslot of a scheduler entity.

        Returns:
            What the reconciliation found.
        """

    @abstractmethod
    async def begin_hold(
        self, timeslot: ScheduledTimeslot, hold_until: datetime, handoff: bool
    ) -> None:
        """Keep the record of a slot whose time has come, so that a hold can end it later.

        Called instead of the completing cancellation for a wake-up slot that has a hold.

        Args:
            timeslot: The slot that was reached.
            hold_until: When the hold ends (timezone-aware).
            handoff: True when a scheduler slot bounds the hold: the scheduler then owns the
                setting and nothing is restored when the hold ends.
        """

    @abstractmethod
    async def end_hold(self, timeslot: ScheduledTimeslot) -> None:
        """End the hold of a slot: put the earlier state back where that is safe, and forget it.

        Does nothing when no hold is recorded for the slot.

        Args:
            timeslot: The slot whose hold ends.
        """

    @abstractmethod
    async def hand_over(self, timeslot: ScheduledTimeslot) -> ActuationResult:
        """Carry the preheat in progress over to another slot, without restoring in between.

        The earlier state and any change somebody else made are kept: the new slot takes the
        preheat over instead of starting a new one. Without a preheat in progress it is a plain
        start.

        Args:
            timeslot: The slot the preheat now heads for.

        Returns:
            What happened: see ``ActuationResult``.
        """
