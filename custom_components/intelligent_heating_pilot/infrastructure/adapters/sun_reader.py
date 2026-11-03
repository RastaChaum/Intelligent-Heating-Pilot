"""Home Assistant sun reader adapter.

Translates the sunrise and sunset times of the Home Assistant location into
domain DaylightPeriod value objects.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from homeassistant.const import SUN_EVENT_SUNRISE, SUN_EVENT_SUNSET
from homeassistant.core import HomeAssistant
from homeassistant.helpers.sun import get_astral_event_date
from homeassistant.util import dt as dt_util

from ...domain.interfaces import ISunReader
from ...domain.value_objects import DaylightPeriod

_LOGGER = logging.getLogger(__name__)


class HASunReader(ISunReader):
    """Reads sunrise and sunset from the Home Assistant location.

    Computed from the configured latitude and longitude, so it works even when
    the ``sun.sun`` entity is disabled. No business logic: the share of the
    heating phase in daylight is computed by the domain.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the sun reader.

        Args:
            hass: Home Assistant instance
        """
        self._hass = hass

    async def get_daylight_periods(self, start: datetime, end: datetime) -> list[DaylightPeriod]:
        """Return the daylight period of every local date between ``start`` and ``end``.

        Args:
            start: Start of the window (timezone-aware)
            end: End of the window (timezone-aware)

        Returns:
            One period per local date with both a sunrise and a sunset
        """
        periods: list[DaylightPeriod] = []
        day = dt_util.as_local(start).date()
        last_day = dt_util.as_local(end).date()
        while day <= last_day:
            sunrise = get_astral_event_date(self._hass, SUN_EVENT_SUNRISE, day)
            sunset = get_astral_event_date(self._hass, SUN_EVENT_SUNSET, day)
            if sunrise is not None and sunset is not None and sunset > sunrise:
                periods.append(DaylightPeriod(sunrise=sunrise, sunset=sunset))
            else:
                _LOGGER.debug("No sunrise or sunset on %s, no daylight period", day)
            day += timedelta(days=1)
        return periods
