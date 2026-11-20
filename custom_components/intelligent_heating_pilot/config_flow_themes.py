"""Theme steps of the options flow: one form per group of settings (#302).

The options of a device open on a menu of themes. A theme form validates its fields and writes
the entry at once, without reloading the device; "Apply" on the menu reloads it, and is only
offered while the stored entry differs from what the device was loaded with.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState, ConfigFlowResult
from homeassistant.core import HomeAssistant
from homeassistant.helpers.translation import async_get_translations

from .config_flow_selectors import _is_blank, as_list, build_theme_schema, theme_definitions
from .const import DOMAIN
from .domain.constants import CONF_SCHEDULER_ENTITIES, CONF_VTHERM_ENTITY
from .domain.value_objects.setting_definition import SettingDefinition, SettingTheme
from .infrastructure.adapters.entry_changes import themes_of, unapplied_keys

_LOGGER = logging.getLogger(__name__)

ERROR_REQUIRED = "required"
ERROR_VTHERM_IN_USE = "vtherm_already_configured"
NO_PENDING_TEXT = "-"
STEP_APPLY = "apply"
# The wake-up sources have their own flow; the others are plain forms.
FORM_THEMES = (
    SettingTheme.THERMOSTAT_SCHEDULERS,
    SettingTheme.NATIVE_SCHEDULE,
    SettingTheme.ENVIRONMENT,
    SettingTheme.LEARNING,
    SettingTheme.CYCLE_DETECTION,
    SettingTheme.ANTICIPATION,
)
MENU_ORDER = (
    SettingTheme.THERMOSTAT_SCHEDULERS,
    SettingTheme.NATIVE_SCHEDULE,
    SettingTheme.WAKE_UP_SOURCES,
    SettingTheme.ENVIRONMENT,
    SettingTheme.LEARNING,
    SettingTheme.CYCLE_DETECTION,
    SettingTheme.ANTICIPATION,
)


def configured_vtherm(entry: config_entries.ConfigEntry) -> Any:
    """Return the VTherm a device drives: the options value when set, else the setup value."""
    if CONF_VTHERM_ENTITY in entry.options:
        return entry.options[CONF_VTHERM_ENTITY]
    return entry.data.get(CONF_VTHERM_ENTITY)


def vtherm_in_use(hass: HomeAssistant, vtherm: str, exclude_entry_id: str | None = None) -> bool:
    """Tell whether another device already drives this VTherm.

    Two devices on one VTherm would overwrite each other's setpoint, so a VTherm identifies a
    device. Entries are compared on the VTherm they use, not on their unique_id, because
    entries created before #192 are keyed on their name.
    """
    return any(
        configured_vtherm(entry) == vtherm
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.entry_id != exclude_entry_id
    )


def normalize_theme_input(
    definitions: tuple[SettingDefinition, ...], user_input: Mapping[str, Any]
) -> dict[str, Any]:
    """Turn a submitted form into the values to store.

    An optional entity that was cleared, or not submitted, is stored as ``None``: that is how
    the options override a value set at setup.
    """
    values = dict(user_input)
    for definition in definitions:
        key = definition.key
        if key == CONF_SCHEDULER_ENTITIES:
            values[key] = as_list(user_input.get(key))
        elif definition.optional and _is_blank(user_input.get(key)):
            values[key] = None
    return values


def drop_unchanged_defaults(
    definitions: tuple[SettingDefinition, ...],
    values: Mapping[str, Any],
    stored: Mapping[str, Any],
) -> dict[str, Any]:
    """Leave out the values that merely repeat a built-in default nobody stored.

    A form is pre-filled with defaults, so submitting it unchanged would pin every default of
    the theme into the entry: the menu would then offer "Apply" for nothing, and the entry would
    hold values the user never chose.
    """
    defaults = {d.key: d.default for d in definitions}
    return {
        key: value
        for key, value in values.items()
        if key in stored or key not in defaults or value != defaults[key]
    }


def applied_snapshot(
    hass: HomeAssistant, entry: config_entries.ConfigEntry
) -> Mapping[str, Any] | None:
    """Return what the running device was loaded with, or ``None`` when it is not running."""
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if coordinator is None or entry.state is not ConfigEntryState.LOADED:
        return None
    return getattr(coordinator, "_options_snapshot", None)


class ThemeStepsMixin:
    """The menu, the theme forms and "Apply" of the device options flow."""

    hass: HomeAssistant
    config_entry: config_entries.ConfigEntry

    if TYPE_CHECKING:

        def async_show_menu(self, **kwargs: Any) -> ConfigFlowResult: ...

        def async_show_form(self, **kwargs: Any) -> ConfigFlowResult: ...

        def async_create_entry(self, **kwargs: Any) -> ConfigFlowResult: ...

        async def async_step_init(
            self, user_input: dict[str, Any] | None = None
        ) -> ConfigFlowResult: ...

    def _is_applied(self) -> bool:
        """Tell whether the device runs with what is stored: nothing to apply."""
        snapshot = applied_snapshot(self.hass, self.config_entry)
        return snapshot is not None and not unapplied_keys(self.config_entry, snapshot)

    async def _pending_text(self) -> str:
        """Name the themes whose stored values the device has not applied yet."""
        snapshot = applied_snapshot(self.hass, self.config_entry)
        themes = themes_of(unapplied_keys(self.config_entry, snapshot))
        if not themes:
            return NO_PENDING_TEXT
        _LOGGER.debug("[%s] Themes with unapplied changes: %s", self.config_entry.title, themes)
        translations = await async_get_translations(
            self.hass, self.hass.config.language, "options", [DOMAIN]
        )
        prefix = f"component.{DOMAIN}.options.step."
        return ", ".join(
            translations.get(f"{prefix}{theme.value}.title", theme.value) for theme in themes
        )

    async def _show_menu(self) -> ConfigFlowResult:
        """Show the themes, and "Apply" only while something is stored and not applied."""
        menu = [theme.value for theme in MENU_ORDER]
        if not self._is_applied():
            menu.append(STEP_APPLY)
        return self.async_show_menu(
            step_id="init",
            menu_options=menu,
            description_placeholders={"pending": await self._pending_text()},
        )

    def _write_values(self, values: Mapping[str, Any]) -> None:
        """Merge values onto the entry as it is stored now, in one update, without reloading.

        The merge is done on the current entry, not on the one the dialog opened with, so that a
        change made elsewhere meanwhile is kept. A new VTherm also becomes the entry's unique id
        in the same update: updating the unique id alone would run the update listener with the
        previous options.
        """
        entry = self.config_entry
        options = {**entry.options, **values}
        _LOGGER.info("[%s] Saving settings: %s", entry.title, ", ".join(sorted(values)))
        vtherm = options.get(CONF_VTHERM_ENTITY)
        if vtherm and vtherm != configured_vtherm(entry):
            _LOGGER.info("[%s] VTherm changed to %s", entry.title, vtherm)
            self.hass.config_entries.async_update_entry(entry, unique_id=vtherm, options=options)
        else:
            self.hass.config_entries.async_update_entry(entry, options=options)

    def _validate_theme(self, theme: SettingTheme, values: Mapping[str, Any]) -> dict[str, str]:
        """Return the errors of a submitted theme, by field."""
        if theme is not SettingTheme.THERMOSTAT_SCHEDULERS:
            return {}
        vtherm = values.get(CONF_VTHERM_ENTITY)
        if _is_blank(vtherm):
            return {CONF_VTHERM_ENTITY: ERROR_REQUIRED}
        if vtherm_in_use(self.hass, str(vtherm), exclude_entry_id=self.config_entry.entry_id):
            return {CONF_VTHERM_ENTITY: ERROR_VTHERM_IN_USE}
        return {}

    async def _theme_step(
        self, theme: SettingTheme, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        """Show one theme form; a valid submission is stored and the menu is shown again."""
        definitions = theme_definitions(theme)
        errors: dict[str, str] = {}
        shown = {**self.config_entry.data, **self.config_entry.options}
        if user_input is not None:
            values = normalize_theme_input(definitions, user_input)
            errors = self._validate_theme(theme, values)
            if not errors:
                stored = {**self.config_entry.data, **self.config_entry.options}
                self._write_values(drop_unchanged_defaults(definitions, values, stored))
                return await self.async_step_init()
            shown.update(user_input)
        return self.async_show_form(
            step_id=theme.value,
            data_schema=build_theme_schema(self.hass, definitions, shown),  # type: ignore[arg-type, unused-ignore]
            errors=errors,
        )

    async def async_step_apply(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Reload the device with what is stored, then close the dialog."""
        entry = self.config_entry
        _LOGGER.info("[%s] Applying the saved settings", entry.title)
        self.hass.config_entries.async_schedule_reload(entry.entry_id)
        return self.async_create_entry(title="", data=dict(entry.options))

    async def async_step_thermostat_schedulers(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Thermostat and schedulers."""
        return await self._theme_step(SettingTheme.THERMOSTAT_SCHEDULERS, user_input)

    async def async_step_native_schedule(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Native schedules: drive opt-in and block data keys."""
        return await self._theme_step(SettingTheme.NATIVE_SCHEDULE, user_input)

    async def async_step_environment(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Environment sensors."""
        return await self._theme_step(SettingTheme.ENVIRONMENT, user_input)

    async def async_step_learning(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Learning parameters."""
        return await self._theme_step(SettingTheme.LEARNING, user_input)

    async def async_step_cycle_detection(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Heating cycle detection."""
        return await self._theme_step(SettingTheme.CYCLE_DETECTION, user_input)

    async def async_step_anticipation(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Anticipation behaviour."""
        return await self._theme_step(SettingTheme.ANTICIPATION, user_input)
