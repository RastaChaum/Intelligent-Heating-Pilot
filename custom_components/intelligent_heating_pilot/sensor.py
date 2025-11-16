"""Sensor platform for Intelligent Heating Pilot."""
from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_ANTICIPATED_START_TIME,
    ATTR_LEARNED_HEATING_SLOPE,
    ATTR_NEXT_SCHEDULE_TIME,
    ATTR_NEXT_TARGET_TEMP,
    CONF_NAME,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Intelligent Heating Pilot sensors."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    name = config_entry.data.get(CONF_NAME, "Intelligent Heating Pilot")

    sensors = [
        IntelligentHeatingPilotAnticipationTimeSensor(coordinator, config_entry, name),
        IntelligentHeatingPilotLearnedSlopeSensor(coordinator, config_entry, name),
        IntelligentHeatingPilotNextScheduleSensor(coordinator, config_entry, name),
        IntelligentHeatingPilotPredictionConfidenceSensor(coordinator, config_entry, name),  # Phase 4: New
    ]

    async_add_entities(sensors, True)


class IntelligentHeatingPilotSensorBase(SensorEntity):
    """Base class for Intelligent Heating Pilot sensors."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: Any, config_entry: ConfigEntry, name: str) -> None:
        """Initialize the sensor."""
        self.coordinator = coordinator
        self._config_entry = config_entry
        self._attr_device_info = {
            "identifiers": {(DOMAIN, config_entry.entry_id)},
            "name": name,
            "manufacturer": "Intelligent Heating Pilot",
            "model": "Intelligent Preheating with ML",
        }

    async def async_added_to_hass(self) -> None:
        """Register callbacks when entity is added."""
        await super().async_added_to_hass()

        @callback
        def handle_anticipation_event(event):
            """Handle anticipation calculated event."""
            data = event.data or {}
            # Filter events to only those coming from our own config entry
            if data.get("entry_id") != self._config_entry.entry_id:
                return
            self._handle_anticipation_result(data)
            self.async_write_ha_state()

        self.async_on_remove(
            self.hass.bus.async_listen(
                f"{DOMAIN}_anticipation_calculated", handle_anticipation_event
            )
        )

    def _handle_anticipation_result(self, data: dict) -> None:
        """Handle new anticipation result. Override in subclasses."""
        pass


class IntelligentHeatingPilotAnticipationTimeSensor(IntelligentHeatingPilotSensorBase):
    """Sensor for anticipated start time."""

    _attr_name = "Anticipated Start Time"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:clock-start"

    def __init__(self, coordinator: Any, config_entry: ConfigEntry, name: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, config_entry, name)
        self._attr_unique_id = f"{config_entry.entry_id}_anticipated_start_time"
        self._anticipated_start = None
        self._attributes = {}

    @property
    def native_value(self) -> datetime | None:
        """Return the state of the sensor."""
        return self._anticipated_start

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return True

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional attributes."""
        return self._attributes

    def _handle_anticipation_result(self, data: dict) -> None:
        """Handle new anticipation result."""
        anticipated_start = data.get(ATTR_ANTICIPATED_START_TIME)
        if anticipated_start:
            # Event carries ISO string; accept datetime too
            if isinstance(anticipated_start, str):
                # Parse with HA helper to preserve timezone correctly
                parsed = dt_util.parse_datetime(anticipated_start)
                if parsed is None:
                    try:
                        parsed = datetime.fromisoformat(anticipated_start)
                    except ValueError:
                        parsed = None
                self._anticipated_start = parsed
            else:
                self._anticipated_start = anticipated_start
            # Store attributes - keep next_schedule_time as ISO string for proper serialization
            next_sched = data.get(ATTR_NEXT_SCHEDULE_TIME)
            if isinstance(next_sched, str):
                next_sched_attr = next_sched  # Already ISO string
            elif isinstance(next_sched, datetime):
                next_sched_attr = next_sched.isoformat()
            else:
                next_sched_attr = None
            
            self._attributes = {
                ATTR_NEXT_SCHEDULE_TIME: next_sched_attr,
                ATTR_NEXT_TARGET_TEMP: data.get(ATTR_NEXT_TARGET_TEMP),
                "anticipation_minutes": data.get("anticipation_minutes"),
                "current_temp": data.get("current_temp"),
                "scheduler_entity": data.get("scheduler_entity"),
                ATTR_LEARNED_HEATING_SLOPE: data.get(ATTR_LEARNED_HEATING_SLOPE),
                "confidence_level": data.get("confidence_level"),  # Phase 4: New from domain
            }
            _LOGGER.info("Anticipated start time updated: %s (confidence: %.2f)", 
                        self._anticipated_start, data.get("confidence_level", 0.0))


class IntelligentHeatingPilotLearnedSlopeSensor(IntelligentHeatingPilotSensorBase):
    """Sensor for learned heating slope (LHS)."""

    _attr_name = "Learned Heating Slope"
    _attr_native_unit_of_measurement = "°C/h"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:chart-line"

    def __init__(self, coordinator: Any, config_entry: ConfigEntry, name: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, config_entry, name)
        self._attr_unique_id = f"{config_entry.entry_id}_learned_heating_slope"
        self._slope = None

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        return self.coordinator.get_learned_heating_slope()

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return True

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional attributes."""
        slopes = self.coordinator.get_historical_slopes()
        if slopes:
            min_slope = min(slopes)
            max_slope = max(slopes)
            avg_slope = sum(slopes) / len(slopes)
        else:
            min_slope = max_slope = avg_slope = None
        
        return {
            "sample_count": len(slopes),
            "min_slope": min_slope,
            "max_slope": max_slope,
            "average_slope": avg_slope,
            "recent_slopes": slopes[-10:] if len(slopes) > 10 else slopes,
        }


class IntelligentHeatingPilotNextScheduleSensor(IntelligentHeatingPilotSensorBase):
    """Sensor for next schedule time."""

    _attr_name = "Next Schedule Time"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator: Any, config_entry: ConfigEntry, name: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, config_entry, name)
        self._attr_unique_id = f"{config_entry.entry_id}_next_schedule_time"
        self._next_schedule = None
        self._attributes = {}

    @property
    def native_value(self) -> datetime | None:
        """Return the state of the sensor."""
        return self._next_schedule

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return True

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional attributes."""
        return self._attributes

    def _handle_anticipation_result(self, data: dict) -> None:
        """Handle new anticipation result."""
        next_schedule = data.get(ATTR_NEXT_SCHEDULE_TIME)
        if next_schedule:
            # Event carries ISO string; accept datetime too
            if isinstance(next_schedule, str):
                # Parse with HA helper to preserve timezone correctly
                parsed = dt_util.parse_datetime(next_schedule)
                if parsed is None:
                    try:
                        parsed = datetime.fromisoformat(next_schedule)
                    except ValueError:
                        parsed = None
                self._next_schedule = parsed
            else:
                self._next_schedule = next_schedule
            self._attributes = {
                ATTR_NEXT_TARGET_TEMP: data.get(ATTR_NEXT_TARGET_TEMP),
                "scheduler_entity": data.get("scheduler_entity"),
            }
            _LOGGER.info("Next schedule time updated: %s", self._next_schedule)


class IntelligentHeatingPilotPredictionConfidenceSensor(IntelligentHeatingPilotSensorBase):
    """Sensor for prediction confidence level.
    
    Phase 4: New sensor to display domain prediction confidence (0.0-1.0).
    This reflects the quality of the prediction based on learned data and
    available environmental sensors.
    """

    _attr_name = "Prediction Confidence"
    _attr_icon = "mdi:percent"
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: Any, config_entry: ConfigEntry, name: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, config_entry, name)
        self._attr_unique_id = f"{config_entry.entry_id}_prediction_confidence"
        self._confidence = None
        self._attributes = {}

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor as percentage (0-100)."""
        if self._confidence is not None:
            return round(self._confidence * 100, 1)
        return None

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return True

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional attributes."""
        return self._attributes

    def _handle_anticipation_result(self, data: dict) -> None:
        """Handle new anticipation result."""
        confidence = data.get("confidence_level")
        if confidence is not None:
            self._confidence = float(confidence)
            self._attributes = {
                ATTR_LEARNED_HEATING_SLOPE: data.get(ATTR_LEARNED_HEATING_SLOPE),
                "anticipation_minutes": data.get("anticipation_minutes"),
                "environmental_data_available": {
                    "humidity": data.get("humidity") is not None,
                    "cloud_coverage": data.get("cloud_coverage") is not None,
                },
            }
            _LOGGER.info("Prediction confidence updated: %.1f%%", self._confidence * 100)
