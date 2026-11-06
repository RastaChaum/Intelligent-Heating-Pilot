"""Config flow for Intelligent Heating Pilot integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.core import HomeAssistant, State, callback
from homeassistant.helpers import selector

from .const import (
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
    CONF_NAME,
    CONF_SAFETY_SHUTOFF_GRACE_MINUTES,
    CONF_SCHEDULER_ENTITIES,
    CONF_TASK_RANGE_DAYS,
    CONF_TEMP_DELTA_THRESHOLD,
    CONF_TEMPERATURE_OUT_ENTITY,
    CONF_VTHERM_ENTITY,
    DEFAULT_ANTICIPATION_RECALC_TOLERANCE_MINUTES,
    DEFAULT_AUTO_LEARNING,
    DEFAULT_CYCLE_SPLIT_DURATION_MINUTES,
    DEFAULT_DEAD_TIME_MINUTES,
    DEFAULT_LHS_RETENTION_DAYS,
    DEFAULT_MAX_CYCLE_DURATION_MINUTES,
    DEFAULT_MIN_CYCLE_DURATION_MINUTES,
    DEFAULT_NAME,
    DEFAULT_SAFETY_SHUTOFF_GRACE_MINUTES,
    DEFAULT_TASK_RANGE_DAYS,
    DEFAULT_TEMP_DELTA_THRESHOLD,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

SCHEDULER_DOMAINS = ("switch", "schedule")
MISSING_SCHEDULER_LABEL = "{entity_id} (not found)"


def _outdoor_source_selector(device_class: str | None = None) -> selector.EntitySelector:
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


def _as_list(value: Any) -> list[str]:
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


def _scheduler_selector(hass: HomeAssistant, configured: list[str]) -> Any:
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


def _configured_vtherm(entry: config_entries.ConfigEntry) -> Any:
    """Return the VTherm a device drives: the options value when set, else the setup value."""
    if CONF_VTHERM_ENTITY in entry.options:
        return entry.options[CONF_VTHERM_ENTITY]
    return entry.data.get(CONF_VTHERM_ENTITY)


def _vtherm_in_use(hass: HomeAssistant, vtherm: str, exclude_entry_id: str | None = None) -> bool:
    """Tell whether another device already drives this VTherm.

    Two devices on one VTherm would overwrite each other's setpoint, so a VTherm identifies a
    device. Entries are compared on the VTherm they use, not on their unique_id, because
    entries created before #192 are keyed on their name.
    """
    return any(
        _configured_vtherm(entry) == vtherm
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.entry_id != exclude_entry_id
    )


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
            processed[CONF_SCHEDULER_ENTITIES] = _as_list(processed.get(CONF_SCHEDULER_ENTITIES))

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
                if _vtherm_in_use(self.hass, vtherm):
                    return self.async_abort(reason="already_configured")
                _LOGGER.info("Creating entry with data: %s", processed)
                await self.async_set_unique_id(vtherm)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=processed[CONF_NAME],
                    data=processed,
                )

        scheduler_selector = _scheduler_selector(self.hass, [])

        data_schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
                vol.Required(CONF_VTHERM_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="climate", integration="versatile_thermostat"
                    )
                ),
                vol.Optional(CONF_SCHEDULER_ENTITIES): scheduler_selector,
                vol.Optional(CONF_HUMIDITY_IN_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor", device_class="humidity")
                ),
                vol.Optional(CONF_HUMIDITY_OUT_ENTITY): _outdoor_source_selector("humidity"),
                vol.Optional(CONF_TEMPERATURE_OUT_ENTITY): _outdoor_source_selector("temperature"),
                vol.Optional(CONF_CLOUD_COVER_ENTITY): _outdoor_source_selector(),
                vol.Optional(
                    CONF_LHS_RETENTION_DAYS, default=DEFAULT_LHS_RETENTION_DAYS
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=7,
                        max=90,
                        step=1,
                        unit_of_measurement="days",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional(
                    CONF_DEAD_TIME_MINUTES, default=DEFAULT_DEAD_TIME_MINUTES
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0.0,
                        max=60.0,
                        step=1.0,
                        unit_of_measurement="minutes",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional(
                    CONF_AUTO_LEARNING, default=DEFAULT_AUTO_LEARNING
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_TEMP_DELTA_THRESHOLD, default=DEFAULT_TEMP_DELTA_THRESHOLD
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0.1,
                        max=1.0,
                        step=0.1,
                        unit_of_measurement="°C",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional(
                    CONF_CYCLE_SPLIT_DURATION_MINUTES, default=DEFAULT_CYCLE_SPLIT_DURATION_MINUTES
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0,
                        max=120,
                        step=5,
                        unit_of_measurement="minutes",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional(
                    CONF_MIN_CYCLE_DURATION_MINUTES, default=DEFAULT_MIN_CYCLE_DURATION_MINUTES
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=30,
                        step=1,
                        unit_of_measurement="minutes",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional(
                    CONF_MAX_CYCLE_DURATION_MINUTES, default=DEFAULT_MAX_CYCLE_DURATION_MINUTES
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=15,
                        max=360,
                        step=5,
                        unit_of_measurement="minutes",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional(
                    CONF_TASK_RANGE_DAYS, default=DEFAULT_TASK_RANGE_DAYS
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=30,
                        step=1,
                        unit_of_measurement="days",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional(
                    CONF_ANTICIPATION_RECALC_TOLERANCE_MINUTES,
                    default=DEFAULT_ANTICIPATION_RECALC_TOLERANCE_MINUTES,
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=60,
                        step=1,
                        unit_of_measurement="minutes",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional(
                    CONF_SAFETY_SHUTOFF_GRACE_MINUTES,
                    default=DEFAULT_SAFETY_SHUTOFF_GRACE_MINUTES,
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0,
                        max=30,
                        step=1,
                        unit_of_measurement="minutes",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,  # type: ignore[arg-type, unused-ignore]  # HA types schemas as probatio
            errors=errors,
        )


class IntelligentHeatingPilotOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Intelligent Heating Pilot."""

    def _follow_vtherm(self, vtherm: str, options: dict[str, Any]) -> None:
        """Key the entry on its new VTherm, so no two entries ever share a unique_id.

        The options are written in the same update: updating the unique_id alone would run
        the update listener, which reloads the device, with the previous options.
        """
        _LOGGER.info("[%s] VTherm changed to %s", self.config_entry.title, vtherm)
        self.hass.config_entries.async_update_entry(
            self.config_entry, unique_id=vtherm, options=options
        )

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}
        normalized_input: dict[str, Any] = {}

        if user_input is not None:
            # Start with user input
            normalized_input = {**user_input}
            # Schedulers already a list from SelectSelector (multiple=True)
            # Just ensure it's always a list
            normalized_input[CONF_SCHEDULER_ENTITIES] = _as_list(
                normalized_input.get(CONF_SCHEDULER_ENTITIES)
            )

            # For optional fields: if not in user_input OR empty, explicitly mark for deletion
            optional_entity_fields = [
                CONF_HUMIDITY_IN_ENTITY,
                CONF_HUMIDITY_OUT_ENTITY,
                CONF_TEMPERATURE_OUT_ENTITY,
                CONF_CLOUD_COVER_ENTITY,
            ]
            fields_to_delete = []
            for field in optional_entity_fields:
                if field not in user_input:
                    # Field not submitted = user cleared it
                    fields_to_delete.append(field)
                elif not user_input[field] or (
                    isinstance(user_input[field], str) and user_input[field].strip() == ""
                ):
                    # Field submitted but empty
                    fields_to_delete.append(field)

            # Validate required fields
            vtherm: str | None = normalized_input.get(CONF_VTHERM_ENTITY)
            if not vtherm:
                errors[CONF_VTHERM_ENTITY] = "required"
            elif _vtherm_in_use(self.hass, vtherm, exclude_entry_id=self.config_entry.entry_id):
                errors[CONF_VTHERM_ENTITY] = "vtherm_already_configured"

            # Scheduler is now optional - no validation needed

            if not errors:
                # Merge with existing options
                merged_options: dict[str, Any] = {**self.config_entry.options}
                merged_options.update(normalized_input)
                # For optional fields that were cleared: explicitly set to None to override data
                for field in fields_to_delete:
                    merged_options[field] = None
                if vtherm and vtherm != _configured_vtherm(self.config_entry):
                    self._follow_vtherm(vtherm, merged_options)
                return self.async_create_entry(title="", data=merged_options)

        # Prepare data sources for defaults
        current_options = getattr(self.config_entry, "options", {})
        if user_input is not None and errors:
            # Re-display user's attempted values on validation errors
            current_data = {**self.config_entry.data, **current_options, **normalized_input}
        else:
            current_data = {**self.config_entry.data, **current_options}

        def _opt_or_data(key: str, default: Any = None) -> Any:
            # First check options (overrides data)
            if key in current_options:
                val = current_options.get(key)
                # None means explicitly deleted, don't fallback to data
                if val is None:
                    return default
                return val
            # Fallback to data
            return current_data.get(key, default)

        # Compute defaults for entity selectors
        default_schedulers_list = _as_list(_opt_or_data(CONF_SCHEDULER_ENTITIES, []))
        vtherm_val = _opt_or_data(CONF_VTHERM_ENTITY)
        hum_in_val = _opt_or_data(CONF_HUMIDITY_IN_ENTITY)
        hum_out_val = _opt_or_data(CONF_HUMIDITY_OUT_ENTITY)
        temp_out_val = _opt_or_data(CONF_TEMPERATURE_OUT_ENTITY)
        cloud_val = _opt_or_data(CONF_CLOUD_COVER_ENTITY)

        # Build schema dynamically: only set default if value exists and is non-empty
        schema_dict: dict[Any, Any] = {}

        # Required: VTherm (only set default if exists and non-empty)
        vtherm_field = (
            vol.Required(CONF_VTHERM_ENTITY, default=vtherm_val)
            if vtherm_val and vtherm_val != ""
            else vol.Required(CONF_VTHERM_ENTITY)
        )
        schema_dict[vtherm_field] = selector.EntitySelector(
            selector.EntitySelectorConfig(domain="climate", integration="versatile_thermostat")
        )

        # Optional: Schedulers (multiple, only set default if non-empty list)
        scheduler_selector = _scheduler_selector(self.hass, default_schedulers_list)
        schedulers_field = (
            vol.Optional(CONF_SCHEDULER_ENTITIES, default=default_schedulers_list)
            if default_schedulers_list and len(default_schedulers_list) > 0
            else vol.Optional(CONF_SCHEDULER_ENTITIES)
        )
        schema_dict[schedulers_field] = scheduler_selector

        # Optional humidity/cloud fields: Use suggested_value to pre-fill while allowing clearing
        schema_dict[
            vol.Optional(
                CONF_HUMIDITY_IN_ENTITY,
                description={"suggested_value": hum_in_val}
                if hum_in_val and hum_in_val != ""
                else {},
            )
        ] = selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor", device_class="humidity")
        )

        schema_dict[
            vol.Optional(
                CONF_HUMIDITY_OUT_ENTITY,
                description={"suggested_value": hum_out_val}
                if hum_out_val and hum_out_val != ""
                else {},
            )
        ] = _outdoor_source_selector("humidity")

        schema_dict[
            vol.Optional(
                CONF_TEMPERATURE_OUT_ENTITY,
                description={"suggested_value": temp_out_val}
                if temp_out_val and temp_out_val != ""
                else {},
            )
        ] = _outdoor_source_selector("temperature")

        schema_dict[
            vol.Optional(
                CONF_CLOUD_COVER_ENTITY,
                description={"suggested_value": cloud_val} if cloud_val and cloud_val != "" else {},
            )
        ] = _outdoor_source_selector()

        # Numeric fields
        schema_dict[
            vol.Optional(
                CONF_LHS_RETENTION_DAYS,
                default=_opt_or_data(CONF_LHS_RETENTION_DAYS, DEFAULT_LHS_RETENTION_DAYS),
            )
        ] = selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=7,
                max=90,
                step=1,
                unit_of_measurement="days",
                mode=selector.NumberSelectorMode.BOX,
            )
        )
        schema_dict[
            vol.Optional(
                CONF_DEAD_TIME_MINUTES,
                default=_opt_or_data(CONF_DEAD_TIME_MINUTES, DEFAULT_DEAD_TIME_MINUTES),
            )
        ] = selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0.0,
                max=60.0,
                step=1.0,
                unit_of_measurement="minutes",
                mode=selector.NumberSelectorMode.BOX,
            )
        )
        schema_dict[
            vol.Optional(
                CONF_AUTO_LEARNING, default=_opt_or_data(CONF_AUTO_LEARNING, DEFAULT_AUTO_LEARNING)
            )
        ] = selector.BooleanSelector()
        schema_dict[
            vol.Optional(
                CONF_TEMP_DELTA_THRESHOLD,
                default=_opt_or_data(CONF_TEMP_DELTA_THRESHOLD, DEFAULT_TEMP_DELTA_THRESHOLD),
            )
        ] = selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0.1,
                max=1.0,
                step=0.1,
                unit_of_measurement="°C",
                mode=selector.NumberSelectorMode.BOX,
            )
        )
        schema_dict[
            vol.Optional(
                CONF_CYCLE_SPLIT_DURATION_MINUTES,
                default=_opt_or_data(
                    CONF_CYCLE_SPLIT_DURATION_MINUTES, DEFAULT_CYCLE_SPLIT_DURATION_MINUTES
                ),
            )
        ] = selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0,
                max=120,
                step=5,
                unit_of_measurement="minutes",
                mode=selector.NumberSelectorMode.BOX,
            )
        )
        schema_dict[
            vol.Optional(
                CONF_MIN_CYCLE_DURATION_MINUTES,
                default=_opt_or_data(
                    CONF_MIN_CYCLE_DURATION_MINUTES, DEFAULT_MIN_CYCLE_DURATION_MINUTES
                ),
            )
        ] = selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=1,
                max=30,
                step=1,
                unit_of_measurement="minutes",
                mode=selector.NumberSelectorMode.BOX,
            )
        )
        schema_dict[
            vol.Optional(
                CONF_MAX_CYCLE_DURATION_MINUTES,
                default=_opt_or_data(
                    CONF_MAX_CYCLE_DURATION_MINUTES, DEFAULT_MAX_CYCLE_DURATION_MINUTES
                ),
            )
        ] = selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=15,
                max=360,
                step=5,
                unit_of_measurement="minutes",
                mode=selector.NumberSelectorMode.BOX,
            )
        )
        schema_dict[
            vol.Optional(
                CONF_TASK_RANGE_DAYS,
                default=_opt_or_data(CONF_TASK_RANGE_DAYS, DEFAULT_TASK_RANGE_DAYS),
            )
        ] = selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=1,
                max=30,
                step=1,
                unit_of_measurement="days",
                mode=selector.NumberSelectorMode.BOX,
            )
        )
        schema_dict[
            vol.Optional(
                CONF_ANTICIPATION_RECALC_TOLERANCE_MINUTES,
                default=_opt_or_data(
                    CONF_ANTICIPATION_RECALC_TOLERANCE_MINUTES,
                    DEFAULT_ANTICIPATION_RECALC_TOLERANCE_MINUTES,
                ),
            )
        ] = selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=1,
                max=60,
                step=1,
                unit_of_measurement="minutes",
                mode=selector.NumberSelectorMode.BOX,
            )
        )
        schema_dict[
            vol.Optional(
                CONF_SAFETY_SHUTOFF_GRACE_MINUTES,
                default=_opt_or_data(
                    CONF_SAFETY_SHUTOFF_GRACE_MINUTES, DEFAULT_SAFETY_SHUTOFF_GRACE_MINUTES
                ),
            )
        ] = selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0,
                max=30,
                step=1,
                unit_of_measurement="minutes",
                mode=selector.NumberSelectorMode.BOX,
            )
        )

        data_schema = vol.Schema(schema_dict)

        return self.async_show_form(
            step_id="init",
            data_schema=data_schema,  # type: ignore[arg-type, unused-ignore]  # HA types schemas as probatio
            errors=errors,
        )
