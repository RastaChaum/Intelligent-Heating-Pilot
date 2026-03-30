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
    def get_current_target_temperature(self) -> float | None:
        """Retrieve the current target temperature from the VTherm entity.

        Reads the real-time target temperature set on the VTherm climate entity.
        This is used, for example, to resolve a target temperature for native HA
        schedule entities that do not store a temperature themselves.

        Returns:
            Current target temperature in °C, or ``None`` when:
            - The VTherm entity is unavailable.
            - The temperature attribute is missing or cannot be parsed.
        """
