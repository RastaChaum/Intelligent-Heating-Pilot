"""Environment reader interface.

Contract for reading current environmental conditions from external
data sources (e.g., Home Assistant entities).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..value_objects import EnvironmentState


class IEnvironmentReader(ABC):
    """Contract for reading environmental conditions.

    This interface defines how the domain accesses environmental data
    (temperatures, humidity, cloud coverage, etc.) without coupling to
    Home Assistant.

    Implementations of this interface translate Home Assistant entity states
    into domain value objects (EnvironmentState), enabling pure business logic
    testing and maintaining clear architectural separation.

    Edge Cases:
        - Missing sensors: Methods return None gracefully
        - Stale data: Implementations should handle validation
        - Entity not found: Return None, not raise exceptions
    """

    @abstractmethod
    async def get_current_environment(self) -> EnvironmentState | None:
        """Retrieve current environmental conditions.

        Reads environmental data from entity states and converts to a
        domain EnvironmentState value object.

        Returns:
            EnvironmentState with current conditions (indoor_temperature,
            outdoor_temp, humidity, cloud_coverage, timestamp), or None
            if required data (indoor_temperature, humidity, outdoor_temp)
            is unavailable.

        Edge Cases:
            - Returns None if VTherm entity is missing
            - Returns None if indoor_temperature cannot be read
            - Sensor-specific fallbacks:
                - outdoor_temp: Falls back to indoor_temperature if unavailable
                - indoor_humidity: Uses 50% default if unavailable
                - outdoor_humidity, cloud_coverage: Optional (can be None)
        """
        pass
