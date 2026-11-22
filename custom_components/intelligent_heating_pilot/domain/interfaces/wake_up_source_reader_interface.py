"""Wake-up source reader interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..value_objects.wake_up_reading import WakeUpReading


class IWakeUpSourceReader(ABC):
    """Contract for reading the point in time held by a wake-up source entity.

    It only translates a state into a reading: whether the value is usable (past, too far
    away) is a domain rule, judged elsewhere.
    """

    @abstractmethod
    def read(self, entity_id: str) -> WakeUpReading:
        """Read the point in time held by a source entity.

        Never raises for a bad value: the reading then carries the reason. The same issue on
        the same entity is reported once until the value changes, so a source that stays
        unknown does not flood the log.

        Args:
            entity_id: The source entity.

        Returns:
            A reading whose value is timezone-aware, or the reason there is none.
        """
