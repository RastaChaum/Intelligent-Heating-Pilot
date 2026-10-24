"""Home Assistant environment context reader adapter."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from ...domain.interfaces import IContextReader


class HAContextReader(IContextReader):
    """Exposes HA context and sensor metadata for historical data adapters."""

    def __init__(
        self,
        hass: HomeAssistant,
        outdoor_temp_entity_id: str | None = None,
        humidity_in_entity_id: str | None = None,
        humidity_out_entity_id: str | None = None,
        cloud_cover_entity_id: str | None = None,
    ) -> None:
        """Initialize the context reader.

        Args:
            hass: Home Assistant instance
            outdoor_temp_entity_id: Outdoor temperature sensor (optional)
            humidity_in_entity_id: Indoor humidity sensor (optional)
            humidity_out_entity_id: Outdoor humidity sensor (optional)
            cloud_cover_entity_id: Cloud coverage sensor (optional)
        """
        self._hass = hass
        self._outdoor_temp_entity_id = outdoor_temp_entity_id
        self._humidity_in_entity_id = humidity_in_entity_id
        self._humidity_out_entity_id = humidity_out_entity_id
        self._cloud_cover_entity_id = cloud_cover_entity_id

    def get_hass(self) -> Any:
        """Return the Home Assistant instance for adapters."""
        return self._hass

    def get_humidity_in_entity_id(self) -> str | None:
        """Return the indoor humidity sensor entity id (optional)."""
        return self._humidity_in_entity_id

    def get_humidity_out_entity_id(self) -> str | None:
        """Return the outdoor humidity sensor entity id (optional)."""
        return self._humidity_out_entity_id

    def get_outdoor_temp_entity_id(self) -> str | None:
        """Return the outdoor temperature sensor entity id (optional)."""
        return self._outdoor_temp_entity_id

    def get_cloud_cover_entity_id(self) -> str | None:
        """Return the cloud coverage sensor entity id (optional)."""
        return self._cloud_cover_entity_id
