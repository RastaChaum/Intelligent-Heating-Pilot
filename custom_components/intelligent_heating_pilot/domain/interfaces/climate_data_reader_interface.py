"""Climate data reader interface.

Unified interface for reading VTherm climate data: entity identification,
current heating slope, and heating active state.  All three concerns target
the *same* VTherm entity and are therefore grouped into a single contract
to avoid unnecessary fragmentation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class IClimateDataReader(ABC):
    """Contract for reading climate data from a VTherm entity.

    This interface unifies three previously separate readers
    (IVThermMetadataReader, IHeatingSlopeReader, IHeatingStateReader)
    that all operate on the same underlying VTherm climate entity.

    Implementors must be stateless with respect to the returned values;
    each call should read the current live state.
    """

    @abstractmethod
    def get_vtherm_entity_id(self) -> str:
        """Retrieve the VTherm (climate entity) ID.

        Returns:
            The VTherm entity ID (e.g., ``"climate.living_room_vtherm"``).
        """

    @abstractmethod
    def get_current_slope(self) -> float | None:
        """Retrieve the current heating slope in °C per hour.

        The slope is read from the VTherm entity's attributes and represents
        the instantaneous rate of indoor-temperature increase while heating
        is active.

        Returns:
            Current heating slope as a float, or ``None`` when:
            - The VTherm entity is unavailable.
            - The ``slope`` attribute is missing or cannot be parsed.
        """

    @abstractmethod
    def is_heating_active(self) -> bool:
        """Return whether heating is currently active on the VTherm.

        Heating is typically considered active when:
        1. ``hvac_mode`` is ``"heat"``, **and**
        2. ``current_temperature < target_temperature``.

        Returns:
            ``True`` when the VTherm is actively heating, ``False`` otherwise
            (including when the entity is unavailable).
        """

    @abstractmethod
    def get_target_temperature(self) -> float | None:
        """Retrieve the VTherm's current target temperature.

        Reads the live state of the underlying climate entity; implementations
        must not cache a previously observed value.

        Returns:
            Current target temperature in Celsius, or ``None`` when the VTherm
            entity is unavailable or its target temperature cannot be read.
        """

    @abstractmethod
    async def wait_for_state_change(self, timeout_seconds: float) -> bool:
        """Wait for the next state change of the VTherm entity.

        A triggered scheduler action reaches the VTherm a moment after the
        ``run_action`` service call returns (#256). Callers wait here, then
        read the live state again, instead of sleeping for a fixed time.

        Any state change counts (attributes included); the caller decides
        whether the new state is the one it expects.

        Args:
            timeout_seconds: Longest time to wait, in seconds.

        Returns:
            ``True`` when the VTherm state changed before the timeout,
            ``False`` when the timeout elapsed first.
        """
