"""Climate commander interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..value_objects.restore_fields import RestoreFields
from ..value_objects.slot_action import SlotAction


class IClimateCommander(ABC):
    """Contract for writing to the climate entity IHP preheats.

    Implementations address only that climate entity, and mark each command so that schedulers
    that watch for manual changes do not take it for one.
    """

    @abstractmethod
    async def apply(self, action: SlotAction) -> None:
        """Apply a slot action: a preset as a preset, a temperature as a temperature.

        Args:
            action: The action to apply.
        """

    @abstractmethod
    async def restore(self, fields: RestoreFields) -> None:
        """Write back the given fields only; the HVAC mode is never written.

        Args:
            fields: The preset or temperature to set again.
        """
