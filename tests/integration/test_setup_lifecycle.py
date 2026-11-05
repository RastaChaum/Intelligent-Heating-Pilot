"""Setup and unload leave nothing behind (#192).

These tests go through ``hass.config_entries`` so that ``entry.async_on_unload`` callbacks run
as they do in Home Assistant. The coordinator's own work is mocked out.
"""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.components.recorder import Recorder
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState, HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.intelligent_heating_pilot import async_setup_entry, async_unload_entry
from custom_components.intelligent_heating_pilot.const import (
    CONF_VTHERM_ENTITY,
    DOMAIN,
    SERVICE_CALCULATE_ANTICIPATED_START_TIME,
)
from custom_components.intelligent_heating_pilot.heating_application import HeatingApplication

APP = "custom_components.intelligent_heating_pilot.HeatingApplication"
TRACK_POINT_IN_TIME = "custom_components.intelligent_heating_pilot.async_track_point_in_time"
SERVICES = ("reset_learning", SERVICE_CALCULATE_ANTICIPATED_START_TIME)
# Timers armed by the startup work: the first update and the cycle extraction.
STARTUP_TIMERS = 2
# Timer armed at every setup for the late attribute population.
LATE_UPDATE_TIMERS = 1
SENSOR_ENTITY_ID = "sensor.ihp_bedroom_anticipated_start_time"


@pytest.fixture
def entry(hass: HomeAssistant) -> MockConfigEntry:
    """A device on the bedroom VTherm."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="entry_lifecycle",
        unique_id="climate.bedroom",
        data={CONF_VTHERM_ENTITY: "climate.bedroom"},
    )
    config_entry.add_to_hass(hass)
    return config_entry


@pytest.fixture
def cleanup(hass: HomeAssistant) -> Generator[AsyncMock]:
    """Mock the coordinator's work and the platforms; yield the coordinator cleanup mock."""
    hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=True)
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    with (
        patch(f"{APP}.async_load", new=AsyncMock()),
        patch(f"{APP}.setup_listeners", new=Mock()),
        patch(f"{APP}.async_update", new=AsyncMock()),
        patch(f"{APP}.async_initialize_cycle_extraction", new=AsyncMock()),
        patch(f"{APP}.async_cleanup", new=AsyncMock()) as cleanup_mock,
    ):
        yield cleanup_mock


@pytest.fixture
def timers() -> Generator[Mock]:
    """Record the timers armed by the setup."""
    with patch(TRACK_POINT_IN_TIME, return_value=Mock()) as track:
        yield track


@pytest.fixture
def starting(hass: HomeAssistant) -> Generator[None]:
    """Home Assistant is still starting while the device is set up."""
    hass.set_state(CoreState.starting)
    yield
    hass.set_state(CoreState.running)


@pytest.mark.usefixtures("recorder_mock", "enable_custom_integrations", "cleanup")
class TestStartupWork:
    """The startup work is tied to the entry that asked for it."""

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("starting")
    async def test_no_startup_work_after_unload(
        self, hass: HomeAssistant, entry: MockConfigEntry, timers: Mock
    ) -> None:
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.config_entries.async_unload(entry.entry_id)
        armed_before_start = timers.call_count

        hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
        await hass.async_block_till_done()

        assert timers.call_count == armed_before_start

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("starting")
    async def test_startup_work_waits_for_the_start(
        self, hass: HomeAssistant, entry: MockConfigEntry, timers: Mock
    ) -> None:
        assert await hass.config_entries.async_setup(entry.entry_id)
        armed_before_start = timers.call_count

        hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
        hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
        await hass.async_block_till_done()

        assert timers.call_count == armed_before_start + STARTUP_TIMERS
        await hass.config_entries.async_unload(entry.entry_id)

    @pytest.mark.asyncio
    async def test_startup_work_is_immediate_once_started(
        self, hass: HomeAssistant, entry: MockConfigEntry, timers: Mock
    ) -> None:
        assert await hass.config_entries.async_setup(entry.entry_id)

        assert timers.call_count == STARTUP_TIMERS + LATE_UPDATE_TIMERS
        await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.usefixtures("enable_custom_integrations")
class TestUnload:
    """The coordinator is cleaned up only once its platforms are gone."""

    @pytest.mark.asyncio
    async def test_failed_platform_unload_keeps_the_coordinator(
        self, hass: HomeAssistant, entry: MockConfigEntry, cleanup: AsyncMock
    ) -> None:
        await async_setup_entry(hass, entry)
        hass.config_entries.async_unload_platforms = AsyncMock(return_value=False)

        assert await async_unload_entry(hass, entry) is False

        cleanup.assert_not_awaited()
        assert isinstance(hass.data[DOMAIN][entry.entry_id], HeatingApplication)

    @pytest.mark.asyncio
    async def test_platforms_unload_before_the_cleanup(
        self, hass: HomeAssistant, entry: MockConfigEntry, cleanup: AsyncMock
    ) -> None:
        await async_setup_entry(hass, entry)
        order: list[str] = []
        hass.config_entries.async_unload_platforms = AsyncMock(
            side_effect=lambda *_: order.append("platforms") or True
        )
        cleanup.side_effect = lambda: order.append("cleanup")

        assert await async_unload_entry(hass, entry) is True

        assert order == ["platforms", "cleanup"]
        assert entry.entry_id not in hass.data[DOMAIN]


@pytest.mark.usefixtures("recorder_mock", "enable_custom_integrations")
class TestServices:
    """Services belong to the integration, not to its first device."""

    @pytest.mark.asyncio
    async def test_services_exist_without_device(self, hass: HomeAssistant) -> None:
        assert await async_setup_component(hass, DOMAIN, {})

        for service in SERVICES:
            assert hass.services.has_service(DOMAIN, service), service

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("cleanup")
    async def test_service_for_an_unloaded_device_is_refused(
        self, hass: HomeAssistant, entry: MockConfigEntry
    ) -> None:
        assert await hass.config_entries.async_setup(entry.entry_id)
        er.async_get(hass).async_get_or_create(
            "sensor",
            DOMAIN,
            f"{entry.entry_id}_anticipated_start_time",
            config_entry=entry,
            suggested_object_id="ihp_bedroom_anticipated_start_time",
        )
        await hass.config_entries.async_unload(entry.entry_id)
        assert entry.state is ConfigEntryState.NOT_LOADED

        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(
                DOMAIN, "reset_learning", {"entity_id": SENSOR_ENTITY_ID}, blocking=True
            )
