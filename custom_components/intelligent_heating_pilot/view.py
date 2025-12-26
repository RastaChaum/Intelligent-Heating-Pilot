"""HTTP views registration for the Intelligent Heating Pilot integration."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


async def async_register_http_views(hass: HomeAssistant) -> None:
    """Register HTTP handlers for the integration (called once at integration setup).
    
    Args:
        hass: Home Assistant instance
    """
    from .infrastructure.rest_api import (
        extract_heating_cycles_handler,
        health_check_handler,
        debug_heating_state_handler,
    )

    _LOGGER.debug("Registering HTTP handlers for Intelligent Heating Pilot")

    # Register handlers directly with aiohttp router
    hass.http.app.router.add_post(
        "/api/intelligent_heating_pilot/extract_cycles/{device_id}",
        extract_heating_cycles_handler,
    )
    
    hass.http.app.router.add_get(
        "/api/intelligent_heating_pilot/health",
        health_check_handler,
    )
    
    # Debug endpoint to inspect heating state history
    hass.http.app.router.add_get(
        "/api/intelligent_heating_pilot/debug/heating_state/{device_id}",
        debug_heating_state_handler,
    )

    _LOGGER.debug("Successfully registered HTTP handlers for Intelligent Heating Pilot")
