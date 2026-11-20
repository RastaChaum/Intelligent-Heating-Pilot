"""Options flow steps that manage the wake-up sources of an IHP (#66).

Home Assistant has no widget for a list of objects, so the sources are managed through a menu
(add, edit, remove, done) opened from the options form. The steps are a mixin of the options
flow: they only collect and validate input, the stored list is read back by the device config
reader.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.core import HomeAssistant
from homeassistant.helpers import selector

from .const import (
    CONF_CLIMATE_ENTITY,
    CONF_SCHEDULER_ENTITIES,
    CONF_WAKE_UP_ENTITY,
    CONF_WAKE_UP_FROM_SCHEDULE,
    CONF_WAKE_UP_HOLD_MINUTES,
    CONF_WAKE_UP_HORIZON_HOURS,
    CONF_WAKE_UP_PRESET,
    CONF_WAKE_UP_SOURCES,
    CONF_WAKE_UP_TEMPERATURE,
    DEFAULT_WAKE_UP_HORIZON_HOURS,
    MAX_WAKE_UP_HOLD_MINUTES,
    MAX_WAKE_UP_HORIZON_HOURS,
    MIN_WAKE_UP_HORIZON_HOURS,
)
from .infrastructure.adapters.wake_up_sources_config import build_wake_up_source

SOURCE_FILTERS = [
    selector.EntityWithDeviceFilterSelectorConfig(domain="sensor", device_class="timestamp"),
    selector.EntityWithDeviceFilterSelectorConfig(domain="datetime"),
    selector.EntityWithDeviceFilterSelectorConfig(domain="input_datetime"),
]
MIN_TARGET_TEMPERATURE_C = 5.0
MAX_TARGET_TEMPERATURE_C = 35.0
HOLD_STEP_MINUTES = 5

ERROR_TARGET_REQUIRED = "wake_up_target_required"
ERROR_DUPLICATE = "wake_up_duplicate"


def _preset_field(hass: HomeAssistant, climate: str | None) -> Any:
    """Offer the presets the thermostat publishes, or free text when it publishes none."""
    state = hass.states.get(climate) if climate else None
    presets = state.attributes.get("preset_modes") if state is not None else None
    if isinstance(presets, list) and presets:
        return selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[str(preset) for preset in presets],
                custom_value=True,
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        )
    return selector.TextSelector()


def _suggested(key: str, defaults: dict[str, Any]) -> dict[str, Any]:
    value = defaults.get(key)
    return {"suggested_value": value} if value not in (None, "") else {}


def build_source_schema(
    hass: HomeAssistant, climate: str | None, has_scheduler: bool, defaults: dict[str, Any]
) -> vol.Schema:
    """Build the form of one wake-up source.

    Args:
        hass: Home Assistant instance.
        climate: The thermostat whose presets are offered.
        has_scheduler: Whether the IHP has a scheduler; "from the schedule" is only offered then.
        defaults: The values to pre-fill, when a source is edited.

    Returns:
        The form schema.
    """
    fields: dict[Any, Any] = {
        vol.Required(CONF_WAKE_UP_ENTITY, description=_suggested(CONF_WAKE_UP_ENTITY, defaults)): (
            selector.EntitySelector(selector.EntitySelectorConfig(filter=SOURCE_FILTERS))
        ),
        vol.Optional(
            CONF_WAKE_UP_PRESET, description=_suggested(CONF_WAKE_UP_PRESET, defaults)
        ): _preset_field(hass, climate),
        vol.Optional(
            CONF_WAKE_UP_TEMPERATURE, description=_suggested(CONF_WAKE_UP_TEMPERATURE, defaults)
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=MIN_TARGET_TEMPERATURE_C,
                max=MAX_TARGET_TEMPERATURE_C,
                step=0.5,
                unit_of_measurement="°C",
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
    }
    if has_scheduler:
        fields[
            vol.Optional(
                CONF_WAKE_UP_FROM_SCHEDULE,
                default=bool(defaults.get(CONF_WAKE_UP_FROM_SCHEDULE, False)),
            )
        ] = selector.BooleanSelector()
    fields[
        vol.Optional(
            CONF_WAKE_UP_HORIZON_HOURS,
            default=defaults.get(CONF_WAKE_UP_HORIZON_HOURS, DEFAULT_WAKE_UP_HORIZON_HOURS),
        )
    ] = selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=MIN_WAKE_UP_HORIZON_HOURS,
            max=MAX_WAKE_UP_HORIZON_HOURS,
            step=1,
            unit_of_measurement="hours",
            mode=selector.NumberSelectorMode.BOX,
        )
    )
    fields[
        vol.Optional(CONF_WAKE_UP_HOLD_MINUTES, default=defaults.get(CONF_WAKE_UP_HOLD_MINUTES, 0))
    ] = selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0,
            max=MAX_WAKE_UP_HOLD_MINUTES,
            step=HOLD_STEP_MINUTES,
            unit_of_measurement="minutes",
            mode=selector.NumberSelectorMode.BOX,
        )
    )
    return vol.Schema(fields)


def clean_source_input(user_input: dict[str, Any]) -> dict[str, Any]:
    """Drop the empty optional fields of a submitted source, so they are not stored."""
    cleaned = {key: value for key, value in user_input.items() if value not in (None, "")}
    cleaned[CONF_WAKE_UP_HOLD_MINUTES] = float(cleaned.get(CONF_WAKE_UP_HOLD_MINUTES, 0) or 0)
    return cleaned


def validate_source(
    raw: dict[str, Any], others: list[dict[str, Any]], has_scheduler: bool
) -> dict[str, str]:
    """Check a submitted source.

    Args:
        raw: The cleaned submitted values.
        others: The other sources of the IHP.
        has_scheduler: Whether the IHP has a scheduler.

    Returns:
        The form errors, empty when the source is usable.
    """
    if any(other.get(CONF_WAKE_UP_ENTITY) == raw.get(CONF_WAKE_UP_ENTITY) for other in others):
        return {"base": ERROR_DUPLICATE}
    try:
        build_wake_up_source(raw, has_scheduler)
    except (ValueError, TypeError):
        return {"base": ERROR_TARGET_REQUIRED}
    return {}


class WakeUpSourcesFlowMixin:
    """The menu and the forms that manage the wake-up sources, for the options flow.

    The host flow provides ``hass``, the pending options and ``_finish``.
    """

    hass: HomeAssistant
    _pending: dict[str, Any]
    _sources: list[dict[str, Any]]
    _editing: str | None

    if TYPE_CHECKING:
        # Provided by the host options flow; declared here for the type checker only, so that
        # these names never shadow the real methods of the base class.
        def _finish(self, options: dict[str, Any]) -> ConfigFlowResult: ...

        def async_show_menu(self, **kwargs: Any) -> ConfigFlowResult: ...

        def async_show_form(self, **kwargs: Any) -> ConfigFlowResult: ...

    def _begin_wake_up_management(self, options: dict[str, Any]) -> None:
        """Keep the options of the first form while the sources are managed."""
        self._pending = options
        stored = options.get(CONF_WAKE_UP_SOURCES)
        self._sources = [dict(entry) for entry in stored] if isinstance(stored, list) else []
        self._editing = None

    def _has_scheduler(self) -> bool:
        return bool(self._pending.get(CONF_SCHEDULER_ENTITIES))

    def _source_label(self, entity_id: str) -> str:
        state = self.hass.states.get(entity_id)
        name = state.attributes.get("friendly_name") if state is not None else None
        return f"{name} ({entity_id})" if name else entity_id

    def _source_picker(self, multiple: bool) -> Any:
        options = [
            selector.SelectOptionDict(
                value=entry[CONF_WAKE_UP_ENTITY],
                label=self._source_label(entry[CONF_WAKE_UP_ENTITY]),
            )
            for entry in self._sources
        ]
        return selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=options, multiple=multiple, mode=selector.SelectSelectorMode.DROPDOWN
            )
        )

    async def async_step_wake_up_menu(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the sources already set and what can be done with them."""
        menu = ["wake_up_add"]
        if self._sources:
            menu += ["wake_up_edit", "wake_up_remove"]
        menu.append("wake_up_done")
        return self.async_show_menu(
            step_id="wake_up_menu",
            menu_options=menu,
            description_placeholders={
                "sources": ", ".join(entry[CONF_WAKE_UP_ENTITY] for entry in self._sources) or "-"
            },
        )

    async def async_step_wake_up_add(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a source."""
        self._editing = None
        return await self.async_step_wake_up_form()

    async def async_step_wake_up_edit(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick the source to edit."""
        if user_input is not None:
            self._editing = user_input[CONF_WAKE_UP_ENTITY]
            return await self.async_step_wake_up_form()
        return self.async_show_form(
            step_id="wake_up_edit",
            data_schema=vol.Schema(
                {vol.Required(CONF_WAKE_UP_ENTITY): self._source_picker(multiple=False)}
            ),
        )

    async def async_step_wake_up_form(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect one source, whether it is new or edited."""
        errors: dict[str, str] = {}
        others = [e for e in self._sources if e.get(CONF_WAKE_UP_ENTITY) != self._editing]
        if user_input is not None:
            raw = clean_source_input(user_input)
            errors = validate_source(raw, others, self._has_scheduler())
            if not errors:
                self._sources = [*others, raw]
                self._editing = None
                return await self.async_step_wake_up_menu()
        current = next(
            (e for e in self._sources if e.get(CONF_WAKE_UP_ENTITY) == self._editing), {}
        )
        defaults = {**current, **(user_input or {})}
        return self.async_show_form(
            step_id="wake_up_form",
            data_schema=build_source_schema(
                self.hass,
                self._pending.get(CONF_CLIMATE_ENTITY),
                self._has_scheduler(),
                defaults,
            ),
            errors=errors,
        )

    async def async_step_wake_up_remove(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Remove sources."""
        if user_input is not None:
            gone = set(user_input.get(CONF_WAKE_UP_ENTITY, []))
            self._sources = [e for e in self._sources if e.get(CONF_WAKE_UP_ENTITY) not in gone]
            return await self.async_step_wake_up_menu()
        return self.async_show_form(
            step_id="wake_up_remove",
            data_schema=vol.Schema(
                {vol.Required(CONF_WAKE_UP_ENTITY): self._source_picker(multiple=True)}
            ),
        )

    async def async_step_wake_up_done(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Save the options together with the sources."""
        self._pending[CONF_WAKE_UP_SOURCES] = self._sources
        return self._finish(self._pending)
