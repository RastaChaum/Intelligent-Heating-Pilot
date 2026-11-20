"""Home Assistant device configuration reader adapter."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any

from ...const import (
    CONF_ANTICIPATION_RECALC_TOLERANCE_MINUTES,
    CONF_AUTO_LEARNING,
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
    CONF_VTHERM_ENTITY,
    CONF_WAKE_UP_SOURCES,
    DEFAULT_LHS_RETENTION_DAYS,
)
from ...domain.interfaces.central_config_reader_interface import ICentralConfigReader
from ...domain.interfaces.device_config_reader_interface import DeviceConfig, IDeviceConfigReader
from ...domain.services.settings_catalog import SettingsCatalog
from ...domain.services.settings_resolver import SettingsResolver
from ...domain.value_objects.resolved_setting import ResolvedSetting
from ...utils.config_helpers import as_bool
from .central_config_reader import HACentralConfigReader
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

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        central_reader: ICentralConfigReader | None = None,
    ) -> None:
        """Initialize the device config reader.

        Args:
            hass: Home Assistant instance
            config_entry: The config entry for this IHP integration instance
            central_reader: Where the values shared by every device come from; the central
                config entry by default
        """
        self._hass = hass
        self._config_entry = config_entry
        self._central_reader = central_reader or HACentralConfigReader(hass)
        self._catalog = SettingsCatalog()
        self._resolver = SettingsResolver()

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

        # A device stores its own values in data and options (options win); a key it does not
        # store is inherited from the central configuration, else the built-in default (#302).
        device_values: dict[str, Any] = {
            **self._config_entry.data,
            **self._config_entry.options,
        }
        # A device that only stores the legacy retention key still owns its retention (#186).
        if (
            CONF_LHS_RETENTION_DAYS not in device_values
            and device_values.get(CONF_DATA_RETENTION_DAYS) is not None
        ):
            device_values[CONF_LHS_RETENTION_DAYS] = device_values[CONF_DATA_RETENTION_DAYS]
        resolved = self._resolver.resolve(
            self._catalog, device_values, self._central_reader.read_central_values()
        )

        vtherm_entity = device_values.get(CONF_VTHERM_ENTITY)
        if not vtherm_entity:
            raise ValueError("Missing required vtherm_entity_id in configuration")

        scheduler_entities = device_values.get(CONF_SCHEDULER_ENTITIES) or []
        if isinstance(scheduler_entities, str):
            scheduler_entities = [scheduler_entities]
        scheduler_entities = list(scheduler_entities) if scheduler_entities else []

        # CONF_LHS_RETENTION_DAYS is the only key the config and options forms write, so it must
        # win; CONF_DATA_RETENTION_DAYS is only a fallback for legacy entries (#186)
        retention = self._number(resolved, CONF_LHS_RETENTION_DAYS, int, allow_default=False)
        if retention is None:
            legacy = device_values.get(CONF_DATA_RETENTION_DAYS)
            retention = int(legacy) if legacy is not None else DEFAULT_LHS_RETENTION_DAYS

        ihp_enabled = as_bool(device_values.get(CONF_IHP_ENABLED), default=True)
        native_drive = device_values.get(CONF_NATIVE_SCHEDULE_DRIVE)

        device_config = DeviceConfig(
            device_id=device_id,
            vtherm_entity_id=vtherm_entity,
            scheduler_entities=scheduler_entities,
            humidity_in_entity_id=device_values.get(CONF_HUMIDITY_IN_ENTITY),
            humidity_out_entity_id=self._entity(resolved, CONF_HUMIDITY_OUT_ENTITY),
            temperature_out_entity_id=self._entity(resolved, CONF_TEMPERATURE_OUT_ENTITY),
            cloud_cover_entity_id=self._entity(resolved, CONF_CLOUD_COVER_ENTITY),
            lhs_retention_days=retention,
            dead_time_minutes=self._number(resolved, CONF_DEAD_TIME_MINUTES, float),
            auto_learning=bool(self._value(resolved, CONF_AUTO_LEARNING)),
            temp_delta_threshold=self._number(resolved, CONF_TEMP_DELTA_THRESHOLD, float),
            cycle_split_duration_minutes=self._number(
                resolved, CONF_CYCLE_SPLIT_DURATION_MINUTES, int
            ),
            min_cycle_duration_minutes=self._number(resolved, CONF_MIN_CYCLE_DURATION_MINUTES, int),
            max_cycle_duration_minutes=self._number(resolved, CONF_MAX_CYCLE_DURATION_MINUTES, int),
            ihp_enabled=ihp_enabled,
            task_range_days=self._number(resolved, CONF_TASK_RANGE_DAYS, int),
            anticipation_recalc_tolerance_minutes=self._number(
                resolved, CONF_ANTICIPATION_RECALC_TOLERANCE_MINUTES, int
            ),
            safety_shutoff_grace_minutes=self._number(
                resolved, CONF_SAFETY_SHUTOFF_GRACE_MINUTES, int
            ),
            native_schedule_drive=bool(native_drive) if native_drive is not None else False,
            native_schedule_preset_key=self._text(resolved, CONF_NATIVE_SCHEDULE_PRESET_KEY),
            native_schedule_temperature_key=self._text(
                resolved, CONF_NATIVE_SCHEDULE_TEMPERATURE_KEY
            ),
            native_schedule_fallback_preset=self._text(
                resolved, CONF_NATIVE_SCHEDULE_FALLBACK_PRESET
            ),
            wake_up_sources=parse_wake_up_sources(
                device_values.get(CONF_WAKE_UP_SOURCES),
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

    def _value(self, resolved: Mapping[str, ResolvedSetting], key: str) -> Any:
        """Return a resolved value, or the catalog default when it is ``None``.

        ``None`` in an entry has always meant "use the default" for a plain setting; only the
        optional sensors keep ``None`` as a value of their own.
        """
        value = resolved[key].value
        return self._catalog.get(key).default if value is None else value

    def _number(
        self,
        resolved: Mapping[str, ResolvedSetting],
        key: str,
        cast: Callable[[Any], Any],
        allow_default: bool = True,
    ) -> Any:
        """Return a resolved number cast to its type; ``None`` falls back to the default."""
        value = resolved[key].value
        if value is None:
            return cast(self._catalog.get(key).default) if allow_default else None
        return cast(value)

    @staticmethod
    def _entity(resolved: Mapping[str, ResolvedSetting], key: str) -> str | None:
        """Return an optional sensor: an entity id, or ``None`` for none."""
        value = resolved[key].value
        return str(value) if value else None

    def _text(self, resolved: Mapping[str, ResolvedSetting], key: str) -> str:
        """Return a resolved text, trimmed; a blank value gives the default.

        A free text field can be saved empty, which would otherwise make the whole device
        configuration invalid and the integration fail to load.
        """
        value = resolved[key].value
        text = value.strip() if isinstance(value, str) else ""
        return text or str(self._catalog.get(key).default)
