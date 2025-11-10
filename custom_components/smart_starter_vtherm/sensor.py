"""Sensor platform for Smart Starter VTherm."""
from __future__ import annotations

from datetime import datetime
import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTR_CURRENT_TEMP,
    ATTR_OUTDOOR_TEMP,
    ATTR_PREHEAT_DURATION,
    ATTR_START_TIME,
    ATTR_TARGET_TEMP,
    ATTR_TARGET_TIME,
    CONF_NAME,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Smart Starter VTherm sensors."""
    name = config_entry.data.get(CONF_NAME, "Smart Starter VTherm")

    sensors = [
        SmartStarterVThermPreheatDurationSensor(config_entry, name),
        SmartStarterVThermStartTimeSensor(config_entry, name),
    ]

    async_add_entities(sensors, True)


class SmartStarterVThermSensorBase(SensorEntity):
    """Base class for Smart Starter VTherm sensors."""

    _attr_has_entity_name = True

    def __init__(self, config_entry: ConfigEntry, name: str) -> None:
        """Initialize the sensor."""
        self._config_entry = config_entry
        self._attr_device_info = {
            "identifiers": {(DOMAIN, config_entry.entry_id)},
            "name": name,
            "manufacturer": "Smart Starter VTherm",
            "model": "Preheating Calculator",
        }

    async def async_added_to_hass(self) -> None:
        """Register callbacks when entity is added."""
        await super().async_added_to_hass()

        @callback
        def handle_calculation_event(event):
            """Handle calculation complete event."""
            self._handle_calculation_result(event.data)
            self.async_write_ha_state()

        self.async_on_remove(
            self.hass.bus.async_listen(
                f"{DOMAIN}_calculation_complete", handle_calculation_event
            )
        )

    def _handle_calculation_result(self, data: dict) -> None:
        """Handle new calculation result. Override in subclasses."""
        pass


class SmartStarterVThermPreheatDurationSensor(SmartStarterVThermSensorBase):
    """Sensor for preheating duration in minutes."""

    _attr_name = "Preheat Duration"
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:clock-outline"

    def __init__(self, config_entry: ConfigEntry, name: str) -> None:
        """Initialize the sensor."""
        super().__init__(config_entry, name)
        self._attr_unique_id = f"{config_entry.entry_id}_preheat_duration"
        self._preheat_duration = None
        self._attributes = {}

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        return self._preheat_duration

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional attributes."""
        return self._attributes

    def _handle_calculation_result(self, data: dict) -> None:
        """Handle new calculation result."""
        self._preheat_duration = data.get(ATTR_PREHEAT_DURATION)
        self._attributes = {
            ATTR_CURRENT_TEMP: data.get(ATTR_CURRENT_TEMP),
            ATTR_TARGET_TEMP: data.get(ATTR_TARGET_TEMP),
            ATTR_OUTDOOR_TEMP: data.get(ATTR_OUTDOOR_TEMP),
            ATTR_TARGET_TIME: data.get(ATTR_TARGET_TIME),
        }


class SmartStarterVThermStartTimeSensor(SmartStarterVThermSensorBase):
    """Sensor for optimal start time."""

    _attr_name = "Start Time"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:clock-start"

    def __init__(self, config_entry: ConfigEntry, name: str) -> None:
        """Initialize the sensor."""
        super().__init__(config_entry, name)
        self._attr_unique_id = f"{config_entry.entry_id}_start_time"
        self._start_time = None
        self._attributes = {}

    @property
    def native_value(self) -> datetime | None:
        """Return the state of the sensor."""
        return self._start_time

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional attributes."""
        return self._attributes

    def _handle_calculation_result(self, data: dict) -> None:
        """Handle new calculation result."""
        start_time_str = data.get(ATTR_START_TIME)
        if start_time_str:
            self._start_time = datetime.fromisoformat(start_time_str)
        self._attributes = {
            ATTR_PREHEAT_DURATION: data.get(ATTR_PREHEAT_DURATION),
            "should_start_now": data.get("should_start_now"),
            ATTR_TARGET_TIME: data.get(ATTR_TARGET_TIME),
        }
