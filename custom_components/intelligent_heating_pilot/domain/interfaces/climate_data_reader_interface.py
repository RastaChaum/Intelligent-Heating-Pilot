"""Climate data reader interface.

Unified interface for reading climate data: entity identification,
current heating slope, and heating active state.  All three concerns target
the *same* climate entity and are therefore grouped into a single contract
to avoid unnecessary fragmentation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..value_objects.climate_snapshot import ClimateSnapshot


class IClimateDataReader(ABC):
    """Contract for reading climate data from any climate entity.

    This interface unifies three previously separate readers
    (IVThermMetadataReader, IHeatingSlopeReader, IHeatingStateReader)
    that all operate on the same underlying climate entity.

    Implementors must be stateless with respect to the returned values;
    each call should read the current live state.
    """

    @abstractmethod
    def get_climate_entity_id(self) -> str:
        """Retrieve the ID of the climate entity IHP preheats.

        Returns:
            The climate entity ID (e.g., ``"climate.living_room"``).
        """

    @abstractmethod
    def is_heating_active(self) -> bool:
        """Return whether heating is currently active on the climate.

        Heating is typically considered active when:
        1. ``hvac_mode`` is ``"heat"``, **and**
        2. ``current_temperature < target_temperature``.

        Returns:
            ``True`` when the climate is actively heating, ``False`` otherwise
            (including when the entity is unavailable).
        """

    @abstractmethod
    def get_target_temperature(self) -> float | None:
        """Retrieve the climate current target temperature.

        Reads the live state of the underlying climate entity; implementations
        must not cache a previously observed value.

        Returns:
            Current target temperature in Celsius, or ``None`` when the climate
            entity is unavailable or its target temperature cannot be read.
        """

    @abstractmethod
    async def wait_for_state_change(self, timeout_seconds: float) -> bool:
        """Wait for the next state change of the climate entity.

        A triggered scheduler action reaches the climate a moment after the
        ``run_action`` service call returns (#256). Callers wait here, then
        read the live state again, instead of sleeping for a fixed time.

        Any state change counts (attributes included); the caller decides
        whether the new state is the one it expects.

        Args:
            timeout_seconds: Longest time to wait, in seconds.

        Returns:
            ``True`` when the climate state changed before the timeout,
            ``False`` when the timeout elapsed first.
        """

    @abstractmethod
    def read_climate_snapshot(self) -> ClimateSnapshot | None:
        """Read the climate's requested state now.

        Reads the live state of the climate entity; implementations must not cache.
        Where the entity publishes its requested state (hvac mode, target, preset), that is
        what is returned, not the values altered by safety, window or load shedding.

        Returns:
            The snapshot, or ``None`` when the climate entity is unavailable.
        """
