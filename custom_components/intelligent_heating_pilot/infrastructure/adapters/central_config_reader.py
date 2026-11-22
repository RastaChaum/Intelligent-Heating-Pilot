"""Home Assistant implementation of the central configuration reader (#302)."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from ...domain.interfaces.central_config_reader_interface import ICentralConfigReader
from .central_entry import central_values_of, find_central_entry

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class HACentralConfigReader(ICentralConfigReader):
    """Reads the central values from the central config entry.

    The entry is looked up in the registry on every read and its load state is not required, so
    a device never depends on the order in which entries are set up.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the reader.

        Args:
            hass: Home Assistant instance.
        """
        self._hass = hass

    def read_central_values(self) -> Mapping[str, Any]:
        """Return the stored central values, or an empty mapping when there is no central entry."""
        entry = find_central_entry(self._hass)
        values = central_values_of(entry) if entry is not None else {}
        _LOGGER.debug("Central values: %s", values)
        return values
