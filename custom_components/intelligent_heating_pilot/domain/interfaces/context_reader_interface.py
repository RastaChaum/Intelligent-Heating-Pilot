"""Environment context reader interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class IContextReader(ABC):
    """Contract for accessing environment metadata and adapter context.

    This interface is used by the application layer for historical data
    adapter orchestration. It intentionally avoids Home Assistant imports.
    """

    @abstractmethod
    def get_hass(self) -> Any:
        """Retrieve the Home Assistant instance for adapter orchestration."""
        pass

    @abstractmethod
    def get_humidity_in_entity_id(self) -> str | None:
        """Retrieve the indoor humidity sensor entity ID."""
        pass

    @abstractmethod
    def get_humidity_out_entity_id(self) -> str | None:
        """Retrieve the outdoor humidity sensor entity ID."""
        pass

    @abstractmethod
    def get_outdoor_temp_entity_id(self) -> str | None:
        """Retrieve the outdoor temperature sensor entity ID."""
        pass

    @abstractmethod
    def get_cloud_cover_entity_id(self) -> str | None:
        """Retrieve the cloud coverage sensor entity ID."""
        pass
