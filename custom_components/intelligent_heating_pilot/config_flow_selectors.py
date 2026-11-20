"""Selectors, bounds and form fields of the configurable settings (#302).

The options screens used to spell every selector twice (setup form and options form). Each
setting now maps to one selector here, keyed by the catalog key, and the forms are built from
the catalog, so a bound or a unit is defined once.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, NamedTuple

import voluptuous as vol
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import selector

from .domain.constants import (
    CONF_ANTICIPATION_RECALC_TOLERANCE_MINUTES,
    CONF_AUTO_LEARNING,
    CONF_CLIMATE_ENTITY,
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
)
from .domain.services.settings_catalog import SettingsCatalog
from .domain.value_objects.setting_definition import SettingDefinition, SettingTheme

SCHEDULER_DOMAINS = ("switch", "schedule")
MISSING_SCHEDULER_LABEL = "{entity_id} (not found)"
UNIT_DAYS = "days"
UNIT_MINUTES = "minutes"
UNIT_CELSIUS = "°C"


class NumberBounds(NamedTuple):
    """Bounds of a numeric setting, as the forms enforce them."""

    minimum: float
    maximum: float
    step: float
    unit: str


NUMBER_BOUNDS: dict[str, NumberBounds] = {
    CONF_LHS_RETENTION_DAYS: NumberBounds(7, 90, 1, UNIT_DAYS),
    CONF_DEAD_TIME_MINUTES: NumberBounds(0.0, 60.0, 1.0, UNIT_MINUTES),
    CONF_TEMP_DELTA_THRESHOLD: NumberBounds(0.1, 1.0, 0.1, UNIT_CELSIUS),
    CONF_CYCLE_SPLIT_DURATION_MINUTES: NumberBounds(0, 120, 5, UNIT_MINUTES),
    CONF_MIN_CYCLE_DURATION_MINUTES: NumberBounds(1, 30, 1, UNIT_MINUTES),
    CONF_MAX_CYCLE_DURATION_MINUTES: NumberBounds(15, 360, 5, UNIT_MINUTES),
    CONF_TASK_RANGE_DAYS: NumberBounds(1, 30, 1, UNIT_DAYS),
    CONF_ANTICIPATION_RECALC_TOLERANCE_MINUTES: NumberBounds(1, 60, 1, UNIT_MINUTES),
    CONF_SAFETY_SHUTOFF_GRACE_MINUTES: NumberBounds(0, 30, 1, UNIT_MINUTES),
}
BOOLEAN_KEYS = frozenset({CONF_AUTO_LEARNING, CONF_NATIVE_SCHEDULE_DRIVE})
TEXT_KEYS = frozenset(
    {
        CONF_NATIVE_SCHEDULE_PRESET_KEY,
        CONF_NATIVE_SCHEDULE_TEMPERATURE_KEY,
        CONF_NATIVE_SCHEDULE_FALLBACK_PRESET,
    }
)


def outdoor_source_selector(device_class: str | None = None) -> selector.EntitySelector:
    """Build a selector accepting a sensor or a weather entity.

    Weather entities expose temperature, humidity and cloud coverage as attributes,
    so they are valid outdoor sources alongside dedicated sensors.

    The filters are dict literals rather than a named selector config TypedDict:
    the filter item type was renamed across Home Assistant releases, and literals
    type-check against whichever one the installed release declares.
    """
    return selector.EntitySelector(
        selector.EntitySelectorConfig(
            filter=[
                {"domain": "sensor", "device_class": device_class},
                {"domain": "weather"},
            ]
            if device_class
            else [{"domain": "sensor"}, {"domain": "weather"}]
        )
    )


def as_list(value: Any) -> list[str]:
    """Return a scheduler value as a list: older entries may store a single entity id."""
    if isinstance(value, list):
        return value
    return [value] if value else []


def _scheduler_label(hass: HomeAssistant, entity_id: str) -> str:
    """Label a scheduler with its friendly name, or flag it as not found."""
    state = hass.states.get(entity_id)
    if state is None:
        return MISSING_SCHEDULER_LABEL.format(entity_id=entity_id)
    friendly_name = state.attributes.get("friendly_name", entity_id)
    return f"{friendly_name} ({entity_id})"


def _is_scheduler(state: State) -> bool:
    """Tell whether a state looks like a scheduler (scheduler-component switch or schedule)."""
    return state.domain in SCHEDULER_DOMAINS and bool(
        "schedule" in state.entity_id.lower()
        or state.attributes.get("next_trigger")
        or state.attributes.get("next_event")
    )


def scheduler_selector(hass: HomeAssistant, configured: Iterable[str]) -> Any:
    """Build the scheduler field: a dropdown of the schedulers found, or an entity picker.

    The dropdown also lists every configured scheduler. One that was removed or renamed must
    stay among the choices: the selector rejects any value outside them, so the form could
    not be saved, and the user could not see which entry to remove (#192). When no scheduler
    is found, the entity picker accepts any switch or schedule entity, configured or not.
    """
    found = {state.entity_id for state in hass.states.async_all() if _is_scheduler(state)}
    if not found:
        return selector.EntitySelector(
            selector.EntitySelectorConfig(domain=list(SCHEDULER_DOMAINS), multiple=True)
        )
    options = [
        selector.SelectOptionDict(value=entity_id, label=_scheduler_label(hass, entity_id))
        for entity_id in found.union(configured)
    ]
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=sorted(options, key=lambda option: option["label"]),
            multiple=True,
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )


def _number_selector(bounds: NumberBounds) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=bounds.minimum,
            max=bounds.maximum,
            step=bounds.step,
            unit_of_measurement=bounds.unit,
            mode=selector.NumberSelectorMode.BOX,
        )
    )


def selector_for(
    key: str, hass: HomeAssistant | None = None, configured: Iterable[str] = ()
) -> Any:
    """Return the selector of a setting.

    Args:
        key: A catalog key.
        hass: Needed for the scheduler list only.
        configured: The schedulers already set, kept among the choices.

    Raises:
        KeyError: If the key has no selector.
    """
    if key in NUMBER_BOUNDS:
        return _number_selector(NUMBER_BOUNDS[key])
    if key in BOOLEAN_KEYS:
        return selector.BooleanSelector()
    if key in TEXT_KEYS:
        return selector.TextSelector()
    simple: dict[str, Any] = {
        # Versatile Thermostat is recommended, never required (#252)
        CONF_CLIMATE_ENTITY: lambda: selector.EntitySelector(
            selector.EntitySelectorConfig(domain="climate")
        ),
        CONF_HUMIDITY_IN_ENTITY: lambda: selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor", device_class="humidity")
        ),
        CONF_HUMIDITY_OUT_ENTITY: lambda: outdoor_source_selector("humidity"),
        CONF_TEMPERATURE_OUT_ENTITY: lambda: outdoor_source_selector("temperature"),
        CONF_CLOUD_COVER_ENTITY: outdoor_source_selector,
    }
    if key == CONF_SCHEDULER_ENTITIES:
        if hass is None:
            raise ValueError("The scheduler selector needs hass")
        return scheduler_selector(hass, configured)
    return simple[key]()


def _is_blank(value: Any) -> bool:
    return value is None or value == "" or (isinstance(value, str) and not value.strip())


def _field_marker(definition: SettingDefinition, current: Mapping[str, Any]) -> Any:
    """Build the schema marker of a setting from its current value.

    Optional entities use a suggested value, so that the user can clear them; the thermostat is
    required; the others default to their current value, else their built-in default.
    """
    key = definition.key
    value = current.get(key)
    if key == CONF_CLIMATE_ENTITY:
        return vol.Required(key, default=value) if not _is_blank(value) else vol.Required(key)
    if key == CONF_SCHEDULER_ENTITIES:
        schedulers = as_list(value)
        return vol.Optional(key, default=schedulers) if schedulers else vol.Optional(key)
    if definition.optional:
        return vol.Optional(key, description={} if _is_blank(value) else {"suggested_value": value})
    return vol.Optional(key, default=definition.default if value is None else value)


def build_theme_schema(
    hass: HomeAssistant,
    definitions: Iterable[SettingDefinition],
    current: Mapping[str, Any],
) -> vol.Schema:
    """Build the form of some settings, pre-filled from their current values."""
    configured = as_list(current.get(CONF_SCHEDULER_ENTITIES))
    return vol.Schema(
        {
            _field_marker(definition, current): selector_for(definition.key, hass, configured)
            for definition in definitions
        }
    )


def theme_definitions(theme: SettingTheme) -> tuple[SettingDefinition, ...]:
    """Return the settings shown in the form of a theme."""
    return SettingsCatalog().of_theme(theme)


# Themes with their own flow instead of a plain form
FLOW_THEMES = (SettingTheme.WAKE_UP_SOURCES, SettingTheme.PRESET_TEMPERATURES)


def form_definitions() -> tuple[SettingDefinition, ...]:
    """Return every plain form field in the order of the setup form (wake-up sources excluded).

    The native schedule settings come last, as they always did in the setup form.
    """
    fields = [d for d in SettingsCatalog().all() if d.theme not in FLOW_THEMES]
    return tuple(sorted(fields, key=lambda d: d.theme is SettingTheme.NATIVE_SCHEDULE))
