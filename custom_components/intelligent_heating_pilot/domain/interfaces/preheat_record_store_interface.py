"""Preheat record store interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..value_objects.preheat_record import PreheatRecord


class IPreheatRecordStore(ABC):
    """Contract for persisting the one preheat record of an IHP instance.

    The record must survive a restart and a reload of the integration.
    """

    @abstractmethod
    async def load(self) -> PreheatRecord | None:
        """Return the stored record, or None when there is none."""

    @abstractmethod
    async def save(self, record: PreheatRecord) -> None:
        """Store the record, replacing any earlier one.

        Args:
            record: The record to keep.
        """

    @abstractmethod
    async def clear(self) -> None:
        """Remove the stored record, if any."""
