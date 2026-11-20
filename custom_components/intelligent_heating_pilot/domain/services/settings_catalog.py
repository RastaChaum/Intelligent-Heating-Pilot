"""The catalog of configurable settings (#302)."""

from __future__ import annotations

from ..constants import (
    CONF_ANTICIPATION_RECALC_TOLERANCE_MINUTES,
    CONF_AUTO_LEARNING,
    CONF_CLOUD_COVER_ENTITY,
    CONF_CYCLE_SPLIT_DURATION_MINUTES,
    CONF_DEAD_TIME_MINUTES,
    CONF_HUMIDITY_IN_ENTITY,
    CONF_HUMIDITY_OUT_ENTITY,
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
    DEFAULT_ANTICIPATION_RECALC_TOLERANCE_MINUTES,
    DEFAULT_AUTO_LEARNING,
    DEFAULT_CYCLE_SPLIT_DURATION_MINUTES,
    DEFAULT_DEAD_TIME_MINUTES,
    DEFAULT_LHS_RETENTION_DAYS,
    DEFAULT_MAX_CYCLE_DURATION_MINUTES,
    DEFAULT_MIN_CYCLE_DURATION_MINUTES,
    DEFAULT_NATIVE_SCHEDULE_DRIVE,
    DEFAULT_NATIVE_SCHEDULE_FALLBACK_PRESET,
    DEFAULT_NATIVE_SCHEDULE_PRESET_KEY,
    DEFAULT_NATIVE_SCHEDULE_TEMPERATURE_KEY,
    DEFAULT_SAFETY_SHUTOFF_GRACE_MINUTES,
    DEFAULT_TASK_RANGE_DAYS,
    DEFAULT_TEMP_DELTA_THRESHOLD,
)
from ..value_objects.setting_definition import SettingDefinition, SettingScope, SettingTheme

_DEVICE = SettingScope.DEVICE
_SHAREABLE = SettingScope.SHAREABLE

_DEFINITIONS: tuple[SettingDefinition, ...] = (
    SettingDefinition(CONF_VTHERM_ENTITY, SettingTheme.THERMOSTAT_SCHEDULERS, _DEVICE),
    SettingDefinition(CONF_SCHEDULER_ENTITIES, SettingTheme.THERMOSTAT_SCHEDULERS, _DEVICE),
    # The drive opt-in lets IHP act on the climate, so it stays a per-device decision (#281).
    SettingDefinition(
        CONF_NATIVE_SCHEDULE_DRIVE,
        SettingTheme.NATIVE_SCHEDULE,
        _DEVICE,
        DEFAULT_NATIVE_SCHEDULE_DRIVE,
    ),
    SettingDefinition(
        CONF_NATIVE_SCHEDULE_PRESET_KEY,
        SettingTheme.NATIVE_SCHEDULE,
        _SHAREABLE,
        DEFAULT_NATIVE_SCHEDULE_PRESET_KEY,
    ),
    SettingDefinition(
        CONF_NATIVE_SCHEDULE_TEMPERATURE_KEY,
        SettingTheme.NATIVE_SCHEDULE,
        _SHAREABLE,
        DEFAULT_NATIVE_SCHEDULE_TEMPERATURE_KEY,
    ),
    SettingDefinition(
        CONF_NATIVE_SCHEDULE_FALLBACK_PRESET,
        SettingTheme.NATIVE_SCHEDULE,
        _SHAREABLE,
        DEFAULT_NATIVE_SCHEDULE_FALLBACK_PRESET,
    ),
    SettingDefinition(CONF_WAKE_UP_SOURCES, SettingTheme.WAKE_UP_SOURCES, _DEVICE),
    # The indoor humidity sensor belongs to the room of one device: never inherited.
    SettingDefinition(CONF_HUMIDITY_IN_ENTITY, SettingTheme.ENVIRONMENT, _DEVICE, optional=True),
    SettingDefinition(
        CONF_TEMPERATURE_OUT_ENTITY, SettingTheme.ENVIRONMENT, _SHAREABLE, optional=True
    ),
    SettingDefinition(
        CONF_HUMIDITY_OUT_ENTITY, SettingTheme.ENVIRONMENT, _SHAREABLE, optional=True
    ),
    SettingDefinition(CONF_CLOUD_COVER_ENTITY, SettingTheme.ENVIRONMENT, _SHAREABLE, optional=True),
    SettingDefinition(CONF_AUTO_LEARNING, SettingTheme.LEARNING, _SHAREABLE, DEFAULT_AUTO_LEARNING),
    SettingDefinition(
        CONF_DEAD_TIME_MINUTES, SettingTheme.LEARNING, _SHAREABLE, DEFAULT_DEAD_TIME_MINUTES
    ),
    SettingDefinition(
        CONF_LHS_RETENTION_DAYS, SettingTheme.LEARNING, _SHAREABLE, DEFAULT_LHS_RETENTION_DAYS
    ),
    SettingDefinition(
        CONF_TASK_RANGE_DAYS, SettingTheme.LEARNING, _SHAREABLE, DEFAULT_TASK_RANGE_DAYS
    ),
    SettingDefinition(
        CONF_TEMP_DELTA_THRESHOLD,
        SettingTheme.CYCLE_DETECTION,
        _SHAREABLE,
        DEFAULT_TEMP_DELTA_THRESHOLD,
    ),
    SettingDefinition(
        CONF_CYCLE_SPLIT_DURATION_MINUTES,
        SettingTheme.CYCLE_DETECTION,
        _SHAREABLE,
        DEFAULT_CYCLE_SPLIT_DURATION_MINUTES,
    ),
    SettingDefinition(
        CONF_MIN_CYCLE_DURATION_MINUTES,
        SettingTheme.CYCLE_DETECTION,
        _SHAREABLE,
        DEFAULT_MIN_CYCLE_DURATION_MINUTES,
    ),
    SettingDefinition(
        CONF_MAX_CYCLE_DURATION_MINUTES,
        SettingTheme.CYCLE_DETECTION,
        _SHAREABLE,
        DEFAULT_MAX_CYCLE_DURATION_MINUTES,
    ),
    SettingDefinition(
        CONF_SAFETY_SHUTOFF_GRACE_MINUTES,
        SettingTheme.CYCLE_DETECTION,
        _SHAREABLE,
        DEFAULT_SAFETY_SHUTOFF_GRACE_MINUTES,
    ),
    SettingDefinition(
        CONF_ANTICIPATION_RECALC_TOLERANCE_MINUTES,
        SettingTheme.ANTICIPATION,
        _SHAREABLE,
        DEFAULT_ANTICIPATION_RECALC_TOLERANCE_MINUTES,
    ),
)


class SettingsCatalog:
    """The declared settings, stateless: a fixed tuple of definitions.

    Every form, every inheritance rule and every translation check derives from this list, so
    a setting that is not declared here cannot be shown, inherited or stored by the menus.
    """

    def __init__(self) -> None:
        """Index the definitions by key."""
        self._by_key = {definition.key: definition for definition in _DEFINITIONS}

    def all(self) -> tuple[SettingDefinition, ...]:
        """Return every declared setting, in display order."""
        return _DEFINITIONS

    def of_theme(self, theme: SettingTheme) -> tuple[SettingDefinition, ...]:
        """Return the settings of one theme, in display order."""
        return tuple(d for d in _DEFINITIONS if d.theme is theme)

    def shareable(self) -> tuple[SettingDefinition, ...]:
        """Return the settings a device can inherit from the central configuration."""
        return tuple(d for d in _DEFINITIONS if d.scope is SettingScope.SHAREABLE)

    def get(self, key: str) -> SettingDefinition:
        """Return the definition of a key.

        Raises:
            KeyError: If the key is not declared.
        """
        return self._by_key[key]
