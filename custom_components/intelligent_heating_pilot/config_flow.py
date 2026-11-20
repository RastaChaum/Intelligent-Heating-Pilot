"""Config flow for Intelligent Heating Pilot integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.core import callback

from .config_flow_overrides import OverrideThemeStepsMixin
from .config_flow_selectors import as_list, build_theme_schema, theme_definitions
from .config_flow_themes import CENTRAL_MENU_ORDER, ThemeStepsMixin, vtherm_in_use
from .config_flow_wake_up import WakeUpSourcesFlowMixin
from .const import (
    CENTRAL_ENTRY_TITLE,
    CENTRAL_UNIQUE_ID,
    CONF_ENTRY_TYPE,
    CONF_NAME,
    CONF_SCHEDULER_ENTITIES,
    CONF_VTHERM_ENTITY,
    DEFAULT_NAME,
    DOMAIN,
    ENTRY_TYPE_CENTRAL,
)
from .domain.value_objects.setting_definition import SettingScope, SettingTheme
from .infrastructure.adapters.central_entry import (
    applied_central_values,
    apply_central_changes,
    changed_central_keys,
    is_central_entry,
)

_LOGGER = logging.getLogger(__name__)


class IntelligentHeatingPilotConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Intelligent Heating Pilot."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this entry: the central configuration has its own."""
        if is_central_entry(config_entry):
            return CentralOptionsFlow()
        return IntelligentHeatingPilotOptionsFlow()

    async def async_step_import(
        self, import_data: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create the central configuration, started automatically with the first device.

        The fixed unique id makes a second start abort, so asking for it twice is harmless.
        """
        await self.async_set_unique_id(CENTRAL_UNIQUE_ID)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=CENTRAL_ENTRY_TITLE, data={CONF_ENTRY_TYPE: ENTRY_TYPE_CENTRAL}
        )

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            processed: dict[str, Any] = {**user_input}

            _LOGGER.debug("Received user_input in async_step_user: %s", user_input)

            # Schedulers already a list from SelectSelector (multiple=True)
            # Just ensure it's always a list
            processed[CONF_SCHEDULER_ENTITIES] = as_list(processed.get(CONF_SCHEDULER_ENTITIES))

            # Note: EntitySelector optional fields are simply not present in user_input if not filled
            # No need to remove them as they won't exist in the dict

            _LOGGER.debug("Processed data before validation: %s", processed)

            # Required validations
            vtherm_val = processed.get(CONF_VTHERM_ENTITY)
            if not vtherm_val or (isinstance(vtherm_val, str) and vtherm_val.strip() == ""):
                errors[CONF_VTHERM_ENTITY] = "required"

            # Scheduler is now optional - no validation needed

            if not errors:
                vtherm: str = processed[CONF_VTHERM_ENTITY]
                if vtherm_in_use(self.hass, vtherm):
                    return self.async_abort(reason="already_configured")
                _LOGGER.info("Creating entry with data: %s", processed)
                await self.async_set_unique_id(vtherm)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=processed[CONF_NAME],
                    data=processed,
                )

        data_schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
                **build_theme_schema(
                    self.hass, theme_definitions(SettingTheme.THERMOSTAT_SCHEDULERS), {}
                ).schema,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,  # type: ignore[arg-type, unused-ignore]  # HA types schemas as probatio
            errors=errors,
        )


class IntelligentHeatingPilotOptionsFlow(
    OverrideThemeStepsMixin, WakeUpSourcesFlowMixin, config_entries.OptionsFlow
):
    """Options of a device: a menu of themes, each form stored at once, then "Apply"."""

    def __init__(self) -> None:
        """Initialize the state used while the wake-up sources are managed."""
        self._pending: dict[str, Any] = {}
        self._sources: list[dict[str, Any]] = []
        self._editing: str | None = None

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show the menu of themes."""
        return await self._show_menu()

    async def async_step_central_native_schedule(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Native schedule keys shared by every device."""
        return await self._theme_step(SettingTheme.NATIVE_SCHEDULE, user_input)

    async def async_step_central_environment(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Environment sensors shared by every device."""
        return await self._theme_step(SettingTheme.ENVIRONMENT, user_input)

    async def async_step_central_learning(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Learning settings shared by every device."""
        return await self._theme_step(SettingTheme.LEARNING, user_input)

    async def async_step_central_cycle_detection(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Cycle detection settings shared by every device."""
        return await self._theme_step(SettingTheme.CYCLE_DETECTION, user_input)

    async def async_step_central_anticipation(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Anticipation settings shared by every device."""
        return await self._theme_step(SettingTheme.ANTICIPATION, user_input)

    async def async_step_wake_up_sources(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Open the wake-up sources menu on what the entry stores now."""
        self._begin_wake_up_management({**self.config_entry.data, **self.config_entry.options})
        return await self.async_step_wake_up_menu()


class CentralOptionsFlow(ThemeStepsMixin, config_entries.OptionsFlow):
    """Options of the central configuration: the shareable themes, stored at once, then "Apply".

    Applying reloads, once and in the background, only the devices that inherit a changed value.
    """

    def _menu_themes(self) -> tuple[SettingTheme, ...]:
        return CENTRAL_MENU_ORDER

    def _step_id(self, theme: SettingTheme) -> str:
        return f"central_{theme.value}"

    def _form_definitions(self, theme: SettingTheme) -> Any:
        return tuple(d for d in theme_definitions(theme) if d.scope is SettingScope.SHAREABLE)

    def _shown_values(self) -> dict[str, Any]:
        return dict(self.config_entry.options)

    def _unapplied(self) -> tuple[bool, set[str]]:
        keys = changed_central_keys(self.config_entry, applied_central_values(self.hass))
        return bool(keys), keys

    def _apply(self) -> None:
        apply_central_changes(self.hass, self.config_entry)

    def _write_values(self, values: Any, remove: Any = ()) -> None:
        """Store the central values: a cleared sensor means "no central value", so its key goes."""
        entry = self.config_entry
        merged = {**entry.options, **values}
        options = {key: value for key, value in merged.items() if value is not None}
        _LOGGER.info("Saving central settings: %s", ", ".join(sorted(values)))
        self.hass.config_entries.async_update_entry(entry, options=options)

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show the menu of themes."""
        return await self._show_menu()

    async def async_step_central_native_schedule(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Native schedule keys shared by every device."""
        return await self._theme_step(SettingTheme.NATIVE_SCHEDULE, user_input)

    async def async_step_central_environment(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Environment sensors shared by every device."""
        return await self._theme_step(SettingTheme.ENVIRONMENT, user_input)

    async def async_step_central_learning(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Learning settings shared by every device."""
        return await self._theme_step(SettingTheme.LEARNING, user_input)

    async def async_step_central_cycle_detection(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Cycle detection settings shared by every device."""
        return await self._theme_step(SettingTheme.CYCLE_DETECTION, user_input)

    async def async_step_central_anticipation(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Anticipation settings shared by every device."""
        return await self._theme_step(SettingTheme.ANTICIPATION, user_input)
