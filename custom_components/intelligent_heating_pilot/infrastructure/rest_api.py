"""REST API handlers for the Intelligent Heating Pilot integration."""
from __future__ import annotations

import json
import logging
from datetime import datetime

from aiohttp import web
from aiohttp.web import Request, Response

_LOGGER = logging.getLogger(__name__)


async def extract_heating_cycles_handler(request: Request) -> Response:
    """Handle POST request to extract heating cycles.
    
    Endpoint: POST /api/intelligent_heating_pilot/extract_cycles/{device_id}
    
    Request body (JSON):
    {
        "start_time": "2024-12-17T10:00:00+00:00",
        "end_time": "2024-12-17T20:00:00+00:00",
        "cycle_split_duration_minutes": 60  # Optional
    }
    
    Response (JSON):
    {
        "success": true,
        "device_id": "config_entry_id",
        "cycles": [...],
        "total_cycles": 5
    }
    """
    try:
        # Extract device_id from URL path
        device_id = request.match_info.get("device_id")
        if not device_id:
            return web.json_response(
                {"error": "Missing device_id in URL path"},
                status=400,
            )

        # Parse request body
        try:
            data = await request.json()
        except json.JSONDecodeError as exc:
            return web.json_response(
                {"error": "Invalid JSON in request body"},
                status=400,
            )

        # Extract and validate time parameters
        start_time_str = data.get("start_time")
        end_time_str = data.get("end_time")

        if not start_time_str or not end_time_str:
            return web.json_response(
                {"error": "Missing required fields: start_time and end_time"},
                status=400,
            )

        try:
            start_time = datetime.fromisoformat(start_time_str)
            end_time = datetime.fromisoformat(end_time_str)
        except ValueError as exc:
            return web.json_response(
                {"error": f"Invalid datetime format: {exc}"},
                status=400,
            )

        if start_time >= end_time:
            return web.json_response(
                {"error": "start_time must be before end_time"},
                status=400,
            )

        # Extract optional parameters
        cycle_split_duration_minutes = data.get("cycle_split_duration_minutes")

        # Get the coordinator from hass data
        from custom_components.intelligent_heating_pilot.const import DOMAIN
        from homeassistant.core import HomeAssistant
        
        hass: HomeAssistant = request.app["hass"]
        coordinators = hass.data.get(DOMAIN, {})
        
        # Find coordinator matching the device_id (entry_id)
        coordinator = coordinators.get(device_id)
        if not coordinator:
            _LOGGER.warning("Device %s not found", device_id)
            return web.json_response(
                {"error": f"Device {device_id} not configured"},
                status=404,
            )

        # Create use case dynamically for this request
        from custom_components.intelligent_heating_pilot.domain.interfaces.device_config_reader import IDeviceConfigReader
        from custom_components.intelligent_heating_pilot.infrastructure.adapters.device_config_reader import HADeviceConfigReader
        from custom_components.intelligent_heating_pilot.domain.services.heating_cycle_service import HeatingCycleService
        from custom_components.intelligent_heating_pilot.application.extract_heating_cycles_use_case import ExtractHeatingCyclesUseCase

        device_config_reader = HADeviceConfigReader(hass, coordinator.config)
        
        heating_cycle_service = HeatingCycleService(
            temp_delta_threshold=0.2,
            cycle_split_duration_minutes=None,
            min_cycle_duration_minutes=5,
            max_cycle_duration_minutes=300,
        )

        use_case = ExtractHeatingCyclesUseCase(
            device_config_reader=device_config_reader,
            heating_cycle_service=heating_cycle_service,
            hass=hass,
        )

        # Execute the use case
        _LOGGER.info(
            "Extracting cycles for device=%s, start=%s, end=%s",
            device_id,
            start_time,
            end_time,
        )

        cycles = await use_case.execute(
            device_id=device_id,
            start_time=start_time,
            end_time=end_time,
            cycle_split_duration_minutes=cycle_split_duration_minutes,
        )

        # Convert cycles to JSON-serializable format
        cycles_json = [
            {
                "device_id": cycle.device_id,
                "start_time": cycle.start_time.isoformat(),
                "end_time": cycle.end_time.isoformat(),
                "target_temp": cycle.target_temp,
                "start_temp": cycle.start_temp,
                "end_temp": cycle.end_temp,
                "tariff_details": [
                    {
                        "tariff_price_eur_per_kwh": detail.tariff_price_eur_per_kwh,
                        "energy_kwh": detail.energy_kwh,
                        "heating_duration_minutes": detail.heating_duration_minutes,
                        "cost_euro": detail.cost_euro,
                    }
                    for detail in (cycle.tariff_details or [])
                ],
            }
            for cycle in cycles
        ]

        return web.json_response(
            {
                "success": True,
                "device_id": device_id,
                "cycles": cycles_json,
                "total_cycles": len(cycles),
            }
        )

    except ValueError as exc:
        _LOGGER.warning("Validation error: %s", exc)
        return web.json_response(
            {"error": str(exc)},
            status=400,
        )
    except Exception as exc:
        _LOGGER.exception("Unexpected error while extracting cycles: %s", exc)
        return web.json_response(
            {"error": "Internal server error"},
            status=500,
        )


async def health_check_handler(request: Request) -> Response:
    """Handle GET request for health check.
    
    Endpoint: GET /api/intelligent_heating_pilot/health
    """
    from custom_components.intelligent_heating_pilot.const import DOMAIN
    from homeassistant.core import HomeAssistant
    
    hass: HomeAssistant = request.app.get("hass")
    coordinators = hass.data.get(DOMAIN, {}) if hass else {}
    is_ready = len(coordinators) > 0

    return web.json_response(
        {
            "status": "ok" if is_ready else "initializing",
            "service": "intelligent_heating_pilot",
            "ready": is_ready,
            "device_count": len(coordinators),
        }
    )


async def debug_heating_state_handler(request: Request) -> Response:
    """Handle GET request to debug heating state history.
    
    Endpoint: GET /api/intelligent_heating_pilot/debug/heating_state/{device_id}?start_time=...&end_time=...
    
    Returns raw heating state data to help debug cycle splitting issues.
    """
    try:
        # Extract device_id from URL
        device_id = request.match_info.get("device_id")
        if not device_id:
            return web.json_response(
                {"error": "Missing device_id in URL path"},
                status=400,
            )
        
        # Extract query parameters
        query_params = request.rel_url.query
        start_time_str = query_params.get("start_time")
        end_time_str = query_params.get("end_time")
        
        if not start_time_str or not end_time_str:
            return web.json_response(
                {"error": "Missing required query parameters: start_time and end_time"},
                status=400,
            )
        
        try:
            from datetime import datetime
            start_time = datetime.fromisoformat(start_time_str)
            end_time = datetime.fromisoformat(end_time_str)
        except ValueError as exc:
            return web.json_response(
                {"error": f"Invalid datetime format: {exc}"},
                status=400,
            )
        
        # Get coordinator
        from custom_components.intelligent_heating_pilot.const import DOMAIN
        from homeassistant.core import HomeAssistant
        
        hass: HomeAssistant = request.app["hass"]
        coordinators = hass.data.get(DOMAIN, {})
        
        coordinator = coordinators.get(device_id)
        if not coordinator:
            return web.json_response(
                {"error": f"Device {device_id} not configured"},
                status=404,
            )
        
        # Fetch heating state data
        from custom_components.intelligent_heating_pilot.infrastructure.adapters.climate_data_adapter import ClimateDataAdapter
        from custom_components.intelligent_heating_pilot.domain.value_objects import HistoricalDataKey
        
        climate_adapter = ClimateDataAdapter(hass)
        heating_state_data = await climate_adapter.fetch_historical_data(
            coordinator.config.data.get("vtherm_entity_id"),
            HistoricalDataKey.HEATING_STATE,
            start_time,
            end_time,
        )
        
        heating_states = heating_state_data.data.get(HistoricalDataKey.HEATING_STATE, [])
        
        # Convert to JSON-serializable format
        states_json = [
            {
                "timestamp": measurement.timestamp.isoformat(),
                "value": measurement.value,
                "entity_id": measurement.entity_id,
            }
            for measurement in heating_states
        ]
        
        return web.json_response(
            {
                "success": True,
                "device_id": device_id,
                "vtherm_entity_id": coordinator.config.data.get("vtherm_entity_id"),
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "heating_state_count": len(states_json),
                "heating_states": states_json,
            }
        )
        
    except Exception as exc:
        _LOGGER.exception("Unexpected error in debug endpoint: %s", exc)
        return web.json_response(
            {"error": "Internal server error"},
            status=500,
        )
