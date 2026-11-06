"""Config and options flows: stale schedulers and one device per VTherm (#192)."""

from __future__ import annotations

from typing import Any

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import selector
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.intelligent_heating_pilot.const import (
    CONF_NAME,
    CONF_SCHEDULER_ENTITIES,
    CONF_VTHERM_ENTITY,
    DEFAULT_NAME,
    DOMAIN,
)

pytestmark = pytest.mark.usefixtures("flow_environment")

EXISTING_SCHEDULER = "switch.schedule_kitchen"
MISSING_SCHEDULER = "switch.schedule_gone"
BEDROOM = "climate.bedroom"
OFFICE = "climate.office"
STUDY = "climate.study"


def _add_device(
    hass: HomeAssistant,
    entry_id: str,
    vtherm: str,
    *,
    schedulers: list[str] | None = None,
    options: dict[str, Any] | None = None,
    unique_id: str = DEFAULT_NAME,
) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id=entry_id,
        unique_id=unique_id,
        title=DEFAULT_NAME,
        data={
            CONF_NAME: DEFAULT_NAME,
            CONF_VTHERM_ENTITY: vtherm,
            CONF_SCHEDULER_ENTITIES: schedulers or [],
        },
        options=options or {},
    )
    entry.add_to_hass(hass)
    return entry


def _scheduler_option_labels(form: Any) -> dict[str, str]:
    for key, field_selector in form["data_schema"].schema.items():
        if str(key) == CONF_SCHEDULER_ENTITIES:
            assert isinstance(field_selector, selector.SelectSelector)
            return {option["value"]: option["label"] for option in field_selector.config["options"]}
    raise AssertionError("scheduler field not found")


async def _set_up_device(hass: HomeAssistant, name: str, vtherm: str) -> Any:
    form = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    return await hass.config_entries.flow.async_configure(
        form["flow_id"], {CONF_NAME: name, CONF_VTHERM_ENTITY: vtherm}
    )


async def _submit_options(
    hass: HomeAssistant, entry: MockConfigEntry, user_input: dict[str, Any]
) -> Any:
    form = await hass.config_entries.options.async_init(entry.entry_id)
    return await hass.config_entries.options.async_configure(form["flow_id"], user_input)


class TestOptionsWithAMissingScheduler:
    """A removed or renamed scheduler no longer blocks the options form."""

    @pytest.fixture
    def entry(self, hass: HomeAssistant) -> MockConfigEntry:
        hass.states.async_set(EXISTING_SCHEDULER, "on", {"friendly_name": "Kitchen"})
        return _add_device(
            hass, "entry_stale", BEDROOM, schedulers=[EXISTING_SCHEDULER, MISSING_SCHEDULER]
        )

    @pytest.mark.asyncio
    async def test_missing_scheduler_is_listed_as_not_found(
        self, hass: HomeAssistant, entry: MockConfigEntry
    ) -> None:
        form = await hass.config_entries.options.async_init(entry.entry_id)

        labels = _scheduler_option_labels(form)

        assert labels[MISSING_SCHEDULER] == f"{MISSING_SCHEDULER} (not found)"
        assert labels[EXISTING_SCHEDULER] == f"Kitchen ({EXISTING_SCHEDULER})"

    @pytest.mark.asyncio
    async def test_options_are_saved_unchanged(
        self, hass: HomeAssistant, entry: MockConfigEntry
    ) -> None:
        schedulers = [EXISTING_SCHEDULER, MISSING_SCHEDULER]

        result = await _submit_options(
            hass, entry, {CONF_VTHERM_ENTITY: BEDROOM, CONF_SCHEDULER_ENTITIES: schedulers}
        )

        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert entry.options[CONF_SCHEDULER_ENTITIES] == schedulers

    @pytest.mark.asyncio
    async def test_missing_scheduler_can_be_removed(
        self, hass: HomeAssistant, entry: MockConfigEntry
    ) -> None:
        result = await _submit_options(
            hass,
            entry,
            {CONF_VTHERM_ENTITY: BEDROOM, CONF_SCHEDULER_ENTITIES: [EXISTING_SCHEDULER]},
        )

        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert entry.options[CONF_SCHEDULER_ENTITIES] == [EXISTING_SCHEDULER]

    @pytest.mark.asyncio
    async def test_scheduler_stored_as_a_string_is_listed(
        self, hass: HomeAssistant, entry: MockConfigEntry
    ) -> None:
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_SCHEDULER_ENTITIES: MISSING_SCHEDULER}
        )

        form = await hass.config_entries.options.async_init(entry.entry_id)

        assert MISSING_SCHEDULER in _scheduler_option_labels(form)


class TestOneDevicePerVTherm:
    """Devices are identified by their VTherm, not by their name."""

    @pytest.mark.asyncio
    async def test_two_devices_may_share_a_name(self, hass: HomeAssistant) -> None:
        _add_device(hass, "entry_bedroom", BEDROOM)

        result = await _set_up_device(hass, DEFAULT_NAME, OFFICE)

        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["result"].unique_id == OFFICE

    @pytest.mark.asyncio
    async def test_vtherm_of_another_device_is_refused(self, hass: HomeAssistant) -> None:
        _add_device(hass, "entry_bedroom", BEDROOM)

        result = await _set_up_device(hass, "Another name", BEDROOM)

        assert result["type"] is FlowResultType.ABORT
        assert result["reason"] == "already_configured"

    @pytest.mark.asyncio
    async def test_vtherm_set_in_the_options_of_another_device_is_refused(
        self, hass: HomeAssistant
    ) -> None:
        _add_device(hass, "entry_moved", STUDY, options={CONF_VTHERM_ENTITY: BEDROOM})

        result = await _set_up_device(hass, "Bedroom", BEDROOM)

        assert result["type"] is FlowResultType.ABORT
        assert result["reason"] == "already_configured"

    @pytest.mark.asyncio
    async def test_vtherm_left_by_another_device_is_accepted(self, hass: HomeAssistant) -> None:
        _add_device(hass, "entry_moved", BEDROOM, options={CONF_VTHERM_ENTITY: STUDY})

        result = await _set_up_device(hass, "Bedroom", BEDROOM)

        assert result["type"] is FlowResultType.CREATE_ENTRY

    @pytest.mark.asyncio
    async def test_options_refuse_the_vtherm_of_another_device(self, hass: HomeAssistant) -> None:
        _add_device(hass, "entry_bedroom", BEDROOM, unique_id=BEDROOM)
        office = _add_device(hass, "entry_office", OFFICE, unique_id=OFFICE)

        result = await _submit_options(hass, office, {CONF_VTHERM_ENTITY: BEDROOM})

        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {CONF_VTHERM_ENTITY: "vtherm_already_configured"}
        assert office.options == {}

    @pytest.mark.asyncio
    async def test_options_keep_the_own_vtherm(self, hass: HomeAssistant) -> None:
        office = _add_device(hass, "entry_office", OFFICE, unique_id=OFFICE)

        result = await _submit_options(hass, office, {CONF_VTHERM_ENTITY: OFFICE})

        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert office.unique_id == OFFICE

    @pytest.mark.asyncio
    async def test_unique_id_follows_a_vtherm_change(self, hass: HomeAssistant) -> None:
        office = _add_device(hass, "entry_office", OFFICE, unique_id=OFFICE)

        await _submit_options(hass, office, {CONF_VTHERM_ENTITY: STUDY})

        assert office.unique_id == STUDY
