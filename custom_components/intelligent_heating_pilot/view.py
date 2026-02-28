"""HTTP views registration for the Intelligent Heating Pilot integration.

NOTE: Views registration is not used in IHP v0.5.0+.
All functionality is exposed via Home Assistant services:
- service: intelligent_heating_pilot.calculate_anticipated_start_time
- service: intelligent_heating_pilot.reset_learning

See __init__.py for service implementations.

This file is kept for future HTTP extensions if needed.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


async def async_register_http_views(hass: HomeAssistant) -> None:
    """Register HTTP views (currently unused in IHP v0.5.0+).

    All functionality is provided via Home Assistant services.
    This function is kept for compatibility and future extensions.

    Args:
        hass: Home Assistant instance
    """
    _LOGGER.debug("HTTP views registration called (no endpoints registered in v0.5.0+)")
