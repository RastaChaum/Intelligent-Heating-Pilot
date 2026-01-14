"""Config flow for Intelligent Heating Pilot integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from typing import cast

from .const import (
    CONF_CLOUD_COVER_ENTITY,
    CONF_CYCLE_SPLIT_DURATION_MINUTES,
    CONF_HUMIDITY_IN_ENTITY,
    CONF_HUMIDITY_OUT_ENTITY,
    CONF_LHS_RETENTION_DAYS,
    CONF_MAX_CYCLE_DURATION_MINUTES,
    CONF_MIN_CYCLE_DURATION_MINUTES,
    CONF_NAME,
    CONF_SCHEDULER_ENTITIES,
    CONF_TEMP_DELTA_THRESHOLD,
    CONF_VTHERM_ENTITY,
    DEFAULT_CYCLE_SPLIT_DURATION_MINUTES,
    DEFAULT_LHS_RETENTION_DAYS,
    DEFAULT_MAX_CYCLE_DURATION_MINUTES,
    DEFAULT_MIN_CYCLE_DURATION_MINUTES,
    DEFAULT_NAME,
    DEFAULT_TEMP_DELTA_THRESHOLD,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class IntelligentHeatingPilotConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Intelligent Heating Pilot."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        """Get the options flow for this handler."""
        return IntelligentHeatingPilotOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            processed: dict[str, Any] = {**user_input}

            # Parse schedulers from multiline text into list
            sched_text = processed.get(CONF_SCHEDULER_ENTITIES, "") or ""
            if isinstance(sched_text, str):
                processed[CONF_SCHEDULER_ENTITIES] = [ln.strip() for ln in sched_text.splitlines() if ln.strip()]

            # Normalize optional entity fields: persist empty as ""
            for field in (CONF_HUMIDITY_IN_ENTITY, CONF_HUMIDITY_OUT_ENTITY, CONF_CLOUD_COVER_ENTITY):
                val = processed.get(field, "")
                if not val or (isinstance(val, str) and val.strip() == ""):
                    processed.pop(field, None)

            # Required validations
            vtherm_val = processed.get(CONF_VTHERM_ENTITY)
            if not vtherm_val or (isinstance(vtherm_val, str) and vtherm_val.strip() == ""):
                errors[CONF_VTHERM_ENTITY] = "required"
            if len(processed.get(CONF_SCHEDULER_ENTITIES, [])) == 0:
                errors[CONF_SCHEDULER_ENTITIES] = "required"

            if not errors:
                await self.async_set_unique_id(processed[CONF_NAME])
                self._abort_if_unique_id_configured()
                return cast(
                    FlowResult,
                    self.async_create_entry(
                        title=processed[CONF_NAME],
                        data=processed,
                    ),
                )

        # Get all scheduler entities with their friendly names
        scheduler_options = []
        for state in self.hass.states.async_all("switch"):
            # Filter for scheduler entities (they typically have "schedule_" prefix or scheduler attributes)
            if "schedule" in state.entity_id.lower() or state.attributes.get("next_trigger"):
                friendly_name = state.attributes.get("friendly_name", state.entity_id)
                scheduler_options.append({
                    "value": state.entity_id,
                    "label": f"{friendly_name} ({state.entity_id})"
                })

        # Sort by label for easier selection
        scheduler_options.sort(key=lambda x: x["label"])

        # Build the schema for the configuration form using TextSelectors
        data_schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
                vol.Required(CONF_VTHERM_ENTITY): selector.TextSelector(
                    selector.TextSelectorConfig(multiline=False)
                ),
                vol.Required(CONF_SCHEDULER_ENTITIES): selector.TextSelector(
                    selector.TextSelectorConfig(multiline=True)
                ),
                vol.Optional(CONF_HUMIDITY_IN_ENTITY): selector.TextSelector(
                    selector.TextSelectorConfig(multiline=False)
                ),
                vol.Optional(CONF_HUMIDITY_OUT_ENTITY): selector.TextSelector(
                    selector.TextSelectorConfig(multiline=False)
                ),
                vol.Optional(CONF_CLOUD_COVER_ENTITY): selector.TextSelector(
                    selector.TextSelectorConfig(multiline=False)
                ),
                vol.Optional(
                    CONF_LHS_RETENTION_DAYS,
                    default=DEFAULT_LHS_RETENTION_DAYS
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=7,
                        max=90,
                        step=1,
                        unit_of_measurement="days",
                        mode=selector.NumberSelectorMode.BOX
                    )
                ),
                vol.Optional(
                    CONF_TEMP_DELTA_THRESHOLD,
                    default=DEFAULT_TEMP_DELTA_THRESHOLD
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0.1,
                        max=1.0,
                        step=0.1,
                        unit_of_measurement="°C",
                        mode=selector.NumberSelectorMode.BOX
                    )
                ),
                vol.Optional(
                    CONF_CYCLE_SPLIT_DURATION_MINUTES,
                    default=DEFAULT_CYCLE_SPLIT_DURATION_MINUTES
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0,
                        max=120,
                        step=5,
                        unit_of_measurement="minutes",
                        mode=selector.NumberSelectorMode.BOX
                    )
                ),
                vol.Optional(
                    CONF_MIN_CYCLE_DURATION_MINUTES,
                    default=DEFAULT_MIN_CYCLE_DURATION_MINUTES
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=30,
                        step=1,
                        unit_of_measurement="minutes",
                        mode=selector.NumberSelectorMode.BOX
                    )
                ),
                vol.Optional(
                    CONF_MAX_CYCLE_DURATION_MINUTES,
                    default=DEFAULT_MAX_CYCLE_DURATION_MINUTES
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=15,
                        max=360,
                        step=5,
                        unit_of_measurement="minutes",
                        mode=selector.NumberSelectorMode.BOX
                    )
                ),
            }
        )

        return cast(
            FlowResult,
            self.async_show_form(
                step_id="user",
                data_schema=data_schema,
                errors=errors,
            ),
        )


class IntelligentHeatingPilotOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Intelligent Heating Pilot."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}
        normalized_input: dict[str, Any] = {}

        if user_input is not None:
            # Start with user input
            normalized_input = {**user_input}
            # Schedulers already a list from SelectSelector (multiple=True)
            # Just ensure it's always a list
            sched_in = normalized_input.get(CONF_SCHEDULER_ENTITIES, [])
            if not isinstance(sched_in, list):
                sched_in = [sched_in] if sched_in else []
            normalized_input[CONF_SCHEDULER_ENTITIES] = sched_in
            
            # For optional fields: if not in user_input OR empty, explicitly mark for deletion
            optional_entity_fields = [
                CONF_HUMIDITY_IN_ENTITY,
                CONF_HUMIDITY_OUT_ENTITY,
                CONF_CLOUD_COVER_ENTITY,
            ]
            fields_to_delete = []
            for field in optional_entity_fields:
                if field not in user_input:
                    # Field not submitted = user cleared it
                    fields_to_delete.append(field)
                elif not user_input[field] or (isinstance(user_input[field], str) and user_input[field].strip() == ""):
                    # Field submitted but empty
                    fields_to_delete.append(field)

            # Validate required fields
            if not normalized_input.get(CONF_VTHERM_ENTITY):
                errors[CONF_VTHERM_ENTITY] = "required"

            schedulers_val = normalized_input.get(CONF_SCHEDULER_ENTITIES)
            if not schedulers_val:
                errors[CONF_SCHEDULER_ENTITIES] = "required"

            if not errors:
                # Merge with existing options
                merged_options: dict[str, Any] = {**self.config_entry.options}
                merged_options.update(normalized_input)
                # Delete optional fields that were cleared
                for field in fields_to_delete:
                    if field in merged_options:
                        del merged_options[field]
                return cast(
                    FlowResult,
                    self.async_create_entry(title="", data=merged_options),
                )

        # Prepare data sources for defaults
        current_options = getattr(self.config_entry, "options", {})
        if user_input is not None and errors:
            # Re-display user's attempted values on validation errors
            current_data = {**self.config_entry.data, **current_options, **normalized_input}
        else:
            current_data = {**self.config_entry.data, **current_options}

        def _opt_or_data(key: str, default: Any = None) -> Any:
            if key in current_options:
                return current_options.get(key)
            return current_data.get(key, default)

        def _opt_optional_only(key: str) -> Any | None:
            # For optionals, do NOT fallback to data; if not present in options, treat as empty
            if key in current_options:
                return current_options.get(key)
            return None

        # Get all scheduler entities for SelectSelector
        scheduler_options = []
        for state in self.hass.states.async_all("switch"):
            if "schedule" in state.entity_id.lower() or state.attributes.get("next_trigger"):
                friendly_name = state.attributes.get("friendly_name", state.entity_id)
                scheduler_options.append({
                    "value": state.entity_id,
                    "label": f"{friendly_name} ({state.entity_id})"
                })
        scheduler_options.sort(key=lambda x: x["label"])

        # Compute defaults for entity selectors
        default_schedulers_list = _opt_or_data(CONF_SCHEDULER_ENTITIES, [])
        if isinstance(default_schedulers_list, str):
            default_schedulers_list = [default_schedulers_list]
        vtherm_val = _opt_or_data(CONF_VTHERM_ENTITY)
        hum_in_val = _opt_optional_only(CONF_HUMIDITY_IN_ENTITY)
        hum_out_val = _opt_optional_only(CONF_HUMIDITY_OUT_ENTITY)
        cloud_val = _opt_optional_only(CONF_CLOUD_COVER_ENTITY)

        # Build schema dynamically: only set default if value exists and is non-empty
        schema_dict: dict[Any, Any] = {}

        # Required: VTherm (only set default if exists and non-empty)
        vtherm_field = (
            vol.Required(CONF_VTHERM_ENTITY, default=vtherm_val)
            if vtherm_val and vtherm_val != ""
            else vol.Required(CONF_VTHERM_ENTITY)
        )
        schema_dict[vtherm_field] = selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain="climate",
                integration="versatile_thermostat"
            )
        )

        # Required: Schedulers (multiple, only set default if non-empty list)
        scheduler_selector = (
            selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=scheduler_options,
                    multiple=True,
                    mode=selector.SelectSelectorMode.DROPDOWN
                )
            )
            if scheduler_options
            else selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain="switch",
                    multiple=True
                )
            )
        )
        schedulers_field = (
            vol.Required(CONF_SCHEDULER_ENTITIES, default=default_schedulers_list)
            if default_schedulers_list and len(default_schedulers_list) > 0
            else vol.Required(CONF_SCHEDULER_ENTITIES)
        )
        schema_dict[schedulers_field] = scheduler_selector

        # Optional humidity/cloud fields: Use suggested_value to pre-fill while allowing clearing
        schema_dict[vol.Optional(
            CONF_HUMIDITY_IN_ENTITY, 
            description={"suggested_value": hum_in_val} if hum_in_val and hum_in_val != "" else {}
        )] = selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain="sensor",
                device_class="humidity"
            )
        )

        schema_dict[vol.Optional(
            CONF_HUMIDITY_OUT_ENTITY,
            description={"suggested_value": hum_out_val} if hum_out_val and hum_out_val != "" else {}
        )] = selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain="sensor",
                device_class="humidity"
            )
        )

        schema_dict[vol.Optional(
            CONF_CLOUD_COVER_ENTITY,
            description={"suggested_value": cloud_val} if cloud_val and cloud_val != "" else {}
        )] = selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain="sensor"
            )
        )

        # Numeric fields
        schema_dict[vol.Optional(
            CONF_LHS_RETENTION_DAYS,
            default=_opt_or_data(CONF_LHS_RETENTION_DAYS, DEFAULT_LHS_RETENTION_DAYS)
        )] = selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=7,
                max=90,
                step=1,
                unit_of_measurement="days",
                mode=selector.NumberSelectorMode.BOX
            )
        )
        schema_dict[vol.Optional(
            CONF_TEMP_DELTA_THRESHOLD,
            default=_opt_or_data(CONF_TEMP_DELTA_THRESHOLD, DEFAULT_TEMP_DELTA_THRESHOLD)
        )] = selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0.1,
                max=1.0,
                step=0.1,
                unit_of_measurement="°C",
                mode=selector.NumberSelectorMode.BOX
            )
        )
        schema_dict[vol.Optional(
            CONF_CYCLE_SPLIT_DURATION_MINUTES,
            default=_opt_or_data(CONF_CYCLE_SPLIT_DURATION_MINUTES, DEFAULT_CYCLE_SPLIT_DURATION_MINUTES)
        )] = selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0,
                max=120,
                step=5,
                unit_of_measurement="minutes",
                mode=selector.NumberSelectorMode.BOX
            )
        )
        schema_dict[vol.Optional(
            CONF_MIN_CYCLE_DURATION_MINUTES,
            default=_opt_or_data(CONF_MIN_CYCLE_DURATION_MINUTES, DEFAULT_MIN_CYCLE_DURATION_MINUTES)
        )] = selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=1,
                max=30,
                step=1,
                unit_of_measurement="minutes",
                mode=selector.NumberSelectorMode.BOX
            )
        )
        schema_dict[vol.Optional(
            CONF_MAX_CYCLE_DURATION_MINUTES,
            default=_opt_or_data(CONF_MAX_CYCLE_DURATION_MINUTES, DEFAULT_MAX_CYCLE_DURATION_MINUTES)
        )] = selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=15,
                max=360,
                step=5,
                unit_of_measurement="minutes",
                mode=selector.NumberSelectorMode.BOX
            )
        )

        data_schema = vol.Schema(schema_dict)

        return cast(
            FlowResult,
            self.async_show_form(
                step_id="init",
                data_schema=data_schema,
                errors=errors,
            ),
        )
