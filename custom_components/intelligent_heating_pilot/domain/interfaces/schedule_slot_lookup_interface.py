"""Schedule slot lookup interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from ..value_objects.slots_around import SlotsAround


class IScheduleSlotLookup(ABC):
    """Contract for telling which schedule slots surround a moment.

    A separate port from ``ISchedulerReader``: that one answers "next slot from now", while a
    wake-up source needs the slots around a moment that may be hours away. Only the combining
    reader needs this (interface segregation).
    """

    @abstractmethod
    async def get_slots_around(self, moment: datetime) -> SlotsAround:
        """Tell the schedule slots around a moment, over all configured schedulers.

        ``following`` is the first slot starting after the moment (the earliest across
        schedulers); ``in_effect`` is the slot in effect at the moment, when a scheduler can
        say so. Absent means "cannot say", never "there is none": a scheduler that exposes
        only its next slot cannot tell which one is in effect, and a next slot that is not
        known to follow the moment (others may lie between now and then) is left out.

        Args:
            moment: The moment, timezone-aware.

        Returns:
            The slots that could be told; an empty ``SlotsAround`` when none could.
        """
