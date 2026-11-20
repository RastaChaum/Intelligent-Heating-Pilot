"""Config flow for Intelligent Heating Pilot integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.core import callback

from .config_flow_selectors import as_list, build_theme_schema, form_definitions
from .config_flow_themes import ThemeStepsMixin, vtherm_in_use
from .config_flow_wake_up import WakeUpSourcesFlowMixin
from .const import CONF_NAME, CONF_SCHEDULER_ENTITIES, CONF_VTHERM_ENTITY, DEFAULT_NAME, DOMAIN

_LOGGER = logging.getLogger(__name__)


class IntelligentHeatingPilotConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Intelligent Heating Pilot."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> IntelligentHeatingPilotOptionsFlow:
        """Get the options flow for this handler."""
        return IntelligentHeatingPilotOptionsFlow()

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
                **build_theme_schema(self.hass, form_definitions(), {}).schema,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,  # type: ignore[arg-type, unused-ignore]  # HA types schemas as probatio
            errors=errors,
        )


class IntelligentHeatingPilotOptionsFlow(
    ThemeStepsMixin, WakeUpSourcesFlowMixin, config_entries.OptionsFlow
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

    async def async_step_wake_up_sources(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Open the wake-up sources menu on what the entry stores now."""
        self._begin_wake_up_management({**self.config_entry.data, **self.config_entry.options})
        return await self.async_step_wake_up_menu()
