"""Home Assistant climate data reader adapter.

Unified adapter that reads VTherm metadata, current heating slope,
and heating active state from a single VTherm entity.
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from ...domain.interfaces.climate_data_reader_interface import IClimateDataReader
from ..vtherm_compat import get_vtherm_attribute


class HAClimateDataReader(IClimateDataReader):
    """Reads climate data from a Home Assistant VTherm entity.

    Combines the responsibilities of the former ``HAVThermMetadataReader``,
    ``HAHeatingSlopeReader`` and ``HAHeatingStateReader`` into a single
    thin adapter.
    """

    def __init__(self, hass: HomeAssistant, vtherm_entity_id: str) -> None:
        """Initialize the climate data reader.

        Args:
            hass: Home Assistant instance.
            vtherm_entity_id: VTherm climate entity ID
                (e.g., ``"climate.living_room_vtherm"``).
        """
        self._hass = hass
        self._vtherm_entity_id = vtherm_entity_id

    # ------------------------------------------------------------------
    # IClimateDataReader implementation
    # ------------------------------------------------------------------

    def get_vtherm_entity_id(self) -> str:
        """Return the VTherm climate entity ID."""
        return self._vtherm_entity_id

    def get_current_slope(self) -> float | None:
        """Get current heating slope from VTherm.

        Returns:
            Current slope in °C/h, or ``None`` if not available.
        """
        vtherm_state = self._hass.states.get(self._vtherm_entity_id)
        if not vtherm_state:
            return None

        slope_raw = get_vtherm_attribute(vtherm_state, "slope")
        if slope_raw is None:
            return None

        try:
            return float(slope_raw)
        except (ValueError, TypeError):
            return None

    def is_heating_active(self) -> bool:
        """Check if heating is currently active.

        Heating is active when:
        1. ``hvac_mode == "heat"``
        2. ``current_temperature < target_temperature``

        Returns:
            ``True`` when actively heating, ``False`` otherwise.
        """
        vtherm_state = self._hass.states.get(self._vtherm_entity_id)
        if not vtherm_state:
            return False

        hvac_mode = vtherm_state.state
        if hvac_mode != "heat":
            return False

        current_temp = get_vtherm_attribute(vtherm_state, "current_temperature")
        target_temp = get_vtherm_attribute(vtherm_state, "temperature")

        if current_temp is None or target_temp is None:
            return False

        try:
            return float(current_temp) < float(target_temp)
        except (ValueError, TypeError):
            return False
