"""Home Assistant device configuration reader adapter."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ...const import (
    CONF_ANTICIPATION_RECALC_TOLERANCE_MINUTES,
    CONF_AUTO_LEARNING,
    CONF_CLIMATE_ENTITY,
    CONF_CLOUD_COVER_ENTITY,
    CONF_CYCLE_SPLIT_DURATION_MINUTES,
    CONF_DATA_RETENTION_DAYS,
    CONF_DEAD_TIME_MINUTES,
    CONF_HUMIDITY_IN_ENTITY,
    CONF_HUMIDITY_OUT_ENTITY,
    CONF_IHP_ENABLED,
    CONF_LHS_RETENTION_DAYS,
    CONF_MAX_CYCLE_DURATION_MINUTES,
    CONF_MIN_CYCLE_DURATION_MINUTES,
    CONF_NATIVE_SCHEDULE_DRIVE,
    CONF_NATIVE_SCHEDULE_FALLBACK_PRESET,
    CONF_NATIVE_SCHEDULE_PRESET_KEY,
    CONF_NATIVE_SCHEDULE_TEMPERATURE_KEY,
    CONF_SAFETY_SHUTOFF_GRACE_MINUTES,
    CONF_SCHEDULER_ENTITIES,
    CONF_TASK_RANGE_DAYS,
    CONF_TEMP_DELTA_THRESHOLD,
    CONF_TEMPERATURE_OUT_ENTITY,
    CONF_WAKE_UP_SOURCES,
    DEFAULT_ANTICIPATION_RECALC_TOLERANCE_MINUTES,
    DEFAULT_AUTO_LEARNING,
    DEFAULT_CYCLE_SPLIT_DURATION_MINUTES,
    DEFAULT_DEAD_TIME_MINUTES,
    DEFAULT_LHS_RETENTION_DAYS,
    DEFAULT_MAX_CYCLE_DURATION_MINUTES,
    DEFAULT_MIN_CYCLE_DURATION_MINUTES,
    DEFAULT_NATIVE_SCHEDULE_FALLBACK_PRESET,
    DEFAULT_NATIVE_SCHEDULE_PRESET_KEY,
    DEFAULT_NATIVE_SCHEDULE_TEMPERATURE_KEY,
    DEFAULT_SAFETY_SHUTOFF_GRACE_MINUTES,
    DEFAULT_TASK_RANGE_DAYS,
    DEFAULT_TEMP_DELTA_THRESHOLD,
)
from ...domain.interfaces.device_config_reader_interface import DeviceConfig, IDeviceConfigReader
from ...utils.config_helpers import as_bool
from .wake_up_sources_config import parse_wake_up_sources

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class HADeviceConfigReader(IDeviceConfigReader):
    """Home Assistant implementation of device configuration reader.

    Reads configuration from Home Assistant config entries for IHP devices.
    Since IHP is a single-device integration per config entry, device_id
    corresponds to the config entry ID.
    """

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the device config reader.

        Args:
            hass: Home Assistant instance
            config_entry: The config entry for this IHP integration instance
        """
        self._hass = hass
        self._config_entry = config_entry

    async def get_device_config(self, device_id: str) -> DeviceConfig:
        """Retrieve configuration for a specific device.

        Args:
            device_id: The device identifier (corresponds to config entry ID)

        Returns:
            DeviceConfig with all necessary entity mappings and parameters

        Raises:
            ValueError: If device_id doesn't match or configuration is invalid
        """
        _LOGGER.debug("Retrieving device configuration for device_id=%s", device_id)

        # In the IHP architecture, device_id corresponds to the config entry ID
        if device_id != self._config_entry.entry_id:
            raise ValueError(
                f"Device ID {device_id} not found. "
                f"This integration instance manages device {self._config_entry.entry_id}"
            )

        # Extract configuration with options override support
        config = dict(self._config_entry.data)
        options = dict(self._config_entry.options or {})

        vtherm_entity = self._get_config_value(config, options, CONF_CLIMATE_ENTITY)
        if not vtherm_entity:
            raise ValueError("Missing required climate_entity_id in configuration")

        scheduler_entities = self._get_config_value(config, options, CONF_SCHEDULER_ENTITIES) or []
        if isinstance(scheduler_entities, str):
            scheduler_entities = [scheduler_entities]
        scheduler_entities = list(scheduler_entities) if scheduler_entities else []

        humidity_in = self._get_config_value(config, options, CONF_HUMIDITY_IN_ENTITY)
        humidity_out = self._get_config_value(config, options, CONF_HUMIDITY_OUT_ENTITY)
        temperature_out = self._get_config_value(config, options, CONF_TEMPERATURE_OUT_ENTITY)
        cloud_cover = self._get_config_value(config, options, CONF_CLOUD_COVER_ENTITY)

        # CONF_LHS_RETENTION_DAYS is the only key the config and options forms write, so it must
        # win; CONF_DATA_RETENTION_DAYS is only a fallback for legacy entries (#186)
        data_retention = self._get_config_value(config, options, CONF_LHS_RETENTION_DAYS)
        if data_retention is None:
            data_retention = self._get_config_value(config, options, CONF_DATA_RETENTION_DAYS)
        lhs_retention_days = int(
            data_retention if data_retention is not None else DEFAULT_LHS_RETENTION_DAYS
        )

        dead_time = self._get_config_value(config, options, CONF_DEAD_TIME_MINUTES)
        dead_time_minutes = float(dead_time if dead_time is not None else DEFAULT_DEAD_TIME_MINUTES)

        auto_learning_value = self._get_config_value(config, options, CONF_AUTO_LEARNING)
        auto_learning = bool(
            auto_learning_value if auto_learning_value is not None else DEFAULT_AUTO_LEARNING
        )

        # Heating cycle detection parameters
        temp_delta = self._get_config_value(config, options, CONF_TEMP_DELTA_THRESHOLD)
        temp_delta_threshold = float(
            temp_delta if temp_delta is not None else DEFAULT_TEMP_DELTA_THRESHOLD
        )

        cycle_split = self._get_config_value(config, options, CONF_CYCLE_SPLIT_DURATION_MINUTES)
        cycle_split_duration_minutes = int(
            cycle_split if cycle_split is not None else DEFAULT_CYCLE_SPLIT_DURATION_MINUTES
        )

        min_cycle = self._get_config_value(config, options, CONF_MIN_CYCLE_DURATION_MINUTES)
        min_cycle_duration_minutes = int(
            min_cycle if min_cycle is not None else DEFAULT_MIN_CYCLE_DURATION_MINUTES
        )

        max_cycle = self._get_config_value(config, options, CONF_MAX_CYCLE_DURATION_MINUTES)
        max_cycle_duration_minutes = int(
            max_cycle if max_cycle is not None else DEFAULT_MAX_CYCLE_DURATION_MINUTES
        )

        # IHP enabled state (default to True for backward compatibility)
        ihp_enabled_value = self._get_config_value(config, options, CONF_IHP_ENABLED)
        ihp_enabled = as_bool(ihp_enabled_value, default=True)

        task_range = self._get_config_value(config, options, CONF_TASK_RANGE_DAYS)
        task_range_days = int(task_range if task_range is not None else DEFAULT_TASK_RANGE_DAYS)

        recalc_tolerance = self._get_config_value(
            config,
            options,
            CONF_ANTICIPATION_RECALC_TOLERANCE_MINUTES,
        )
        anticipation_recalc_tolerance_minutes = int(
            recalc_tolerance
            if recalc_tolerance is not None
            else DEFAULT_ANTICIPATION_RECALC_TOLERANCE_MINUTES
        )

        safety_grace = self._get_config_value(config, options, CONF_SAFETY_SHUTOFF_GRACE_MINUTES)
        safety_shutoff_grace_minutes = int(
            safety_grace if safety_grace is not None else DEFAULT_SAFETY_SHUTOFF_GRACE_MINUTES
        )

        native_drive = self._get_config_value(config, options, CONF_NATIVE_SCHEDULE_DRIVE)
        native_preset_key = self._get_text(
            config, options, CONF_NATIVE_SCHEDULE_PRESET_KEY, DEFAULT_NATIVE_SCHEDULE_PRESET_KEY
        )
        native_temperature_key = self._get_text(
            config,
            options,
            CONF_NATIVE_SCHEDULE_TEMPERATURE_KEY,
            DEFAULT_NATIVE_SCHEDULE_TEMPERATURE_KEY,
        )
        native_fallback_preset = self._get_text(
            config,
            options,
            CONF_NATIVE_SCHEDULE_FALLBACK_PRESET,
            DEFAULT_NATIVE_SCHEDULE_FALLBACK_PRESET,
        )

        device_config = DeviceConfig(
            device_id=device_id,
            climate_entity_id=vtherm_entity,
            scheduler_entities=scheduler_entities,
            humidity_in_entity_id=humidity_in,
            humidity_out_entity_id=humidity_out,
            temperature_out_entity_id=temperature_out,
            cloud_cover_entity_id=cloud_cover,
            lhs_retention_days=lhs_retention_days,
            dead_time_minutes=dead_time_minutes,
            auto_learning=auto_learning,
            temp_delta_threshold=temp_delta_threshold,
            cycle_split_duration_minutes=cycle_split_duration_minutes,
            min_cycle_duration_minutes=min_cycle_duration_minutes,
            max_cycle_duration_minutes=max_cycle_duration_minutes,
            ihp_enabled=ihp_enabled,
            task_range_days=task_range_days,
            anticipation_recalc_tolerance_minutes=anticipation_recalc_tolerance_minutes,
            safety_shutoff_grace_minutes=safety_shutoff_grace_minutes,
            native_schedule_drive=bool(native_drive) if native_drive is not None else False,
            native_schedule_preset_key=native_preset_key,
            native_schedule_temperature_key=native_temperature_key,
            native_schedule_fallback_preset=native_fallback_preset,
            wake_up_sources=parse_wake_up_sources(
                self._get_config_value(config, options, CONF_WAKE_UP_SOURCES),
                has_scheduler=bool(scheduler_entities),
            ),
        )

        _LOGGER.debug("Retrieved device configuration: %s", device_config)
        return device_config

    async def get_all_device_ids(self) -> list[str]:
        """Retrieve list of all configured device IDs.

        In IHP architecture, there's typically one device per config entry,
        so this returns a single-element list.

        Returns:
            List containing the config entry ID
        """
        return [self._config_entry.entry_id]

    @staticmethod
    def _get_config_value(config: dict[str, Any], options: dict[str, Any], key: str) -> Any:
        """Get configuration value with options override support.

        Options take precedence over config data.
        """
        if key in options:
            return options.get(key)
        else:
            return config.get(key)

    @classmethod
    def _get_text(
        cls, config: dict[str, Any], options: dict[str, Any], key: str, default: str
    ) -> str:
        """Get a text option, trimmed; a blank value gives the default.

        A free text field can be saved empty, which would otherwise make the whole device
        configuration invalid and the integration fail to load.
        """
        value = cls._get_config_value(config, options, key)
        text = value.strip() if isinstance(value, str) else ""
        return text or default

    @staticmethod
    def _get_scheduler_entities(config: dict[str, Any], options: dict[str, Any]) -> list[str]:
        """Extract scheduler entities from configuration.

        Returns list of entity IDs, or empty list if not found.
        """
        scheduler_entities = (
            options.get(CONF_SCHEDULER_ENTITIES) or config.get(CONF_SCHEDULER_ENTITIES) or []
        )
        return list(scheduler_entities) if scheduler_entities else []
