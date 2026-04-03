"""Regression tests for the reset_learning service.

Bug history:
- Original: reset_all_learning_data() called without device_id → TypeError crash
- Second: handler captured single coordinator via closure → only last-registered
  device could ever be reset with multiple config entries

These tests would have caught both bugs and prevent regression.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.intelligent_heating_pilot.const import (
    CONF_SCHEDULER_ENTITIES,
    CONF_VTHERM_ENTITY,
    DOMAIN,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def suppress_platform_setup(hass: HomeAssistant) -> None:
    """Prevent platform loader lookups during integration tests."""
    hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=True)
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)


@pytest.fixture
def suppress_full_lifecycle(suppress_platform_setup: None):  # type: ignore[return]
    """Suppress HeatingApplication side-effects during setup."""
    with patch(
        "custom_components.intelligent_heating_pilot.HeatingApplication.async_load",
        new=AsyncMock(),
    ), patch(
        "custom_components.intelligent_heating_pilot.HeatingApplication.setup_listeners",
        new=Mock(),
    ), patch(
        "custom_components.intelligent_heating_pilot.HeatingApplication.async_update",
        new=AsyncMock(),
    ):
        yield


@pytest.fixture
def config_entry_a(hass: HomeAssistant) -> MockConfigEntry:
    """Config entry for device A."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="entry_device_a",
        data={
            CONF_VTHERM_ENTITY: "climate.vtherm_a",
            CONF_SCHEDULER_ENTITIES: ["switch.schedule_a"],
        },
        options={},
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def config_entry_b(hass: HomeAssistant) -> MockConfigEntry:
    """Config entry for device B."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="entry_device_b",
        data={
            CONF_VTHERM_ENTITY: "climate.vtherm_b",
            CONF_SCHEDULER_ENTITIES: ["switch.schedule_b"],
        },
        options={},
    )
    entry.add_to_hass(hass)
    return entry


def _register_entity(hass: HomeAssistant, entry_id: str, entity_id: str) -> None:
    """Register a sensor entity in the entity registry owned by *entry_id*."""
    registry = er.async_get(hass)
    domain, _, object_id = entity_id.partition(".")
    registry.async_get_or_create(
        domain=domain,
        platform=DOMAIN,
        unique_id=f"{entry_id}_{object_id}",
        config_entry=hass.config_entries.async_get_entry(entry_id),
        suggested_object_id=object_id,
    )


# ---------------------------------------------------------------------------
# Tests: TypeError regression (device_id was missing)
# ---------------------------------------------------------------------------


class TestResetLearningTypeErrorRegression:
    """Ensure reset_all_learning_data() receives a device_id (TypeError regression)."""

    @pytest.mark.asyncio
    async def test_reset_learning_passes_device_id_to_orchestrator(
        self,
        hass: HomeAssistant,
        config_entry_a: MockConfigEntry,
        suppress_full_lifecycle: None,
    ) -> None:
        """reset_all_learning_data must be called with the correct device_id.

        FAILS with buggy code (no device_id argument → TypeError).
        PASSES with fix (device_id=coordinator.get_device_id() passed).
        """
        from custom_components.intelligent_heating_pilot import async_setup_entry

        await async_setup_entry(hass, config_entry_a)

        # Register a sensor entity for this config entry
        entity_id = f"sensor.{DOMAIN}_anticipated_start_time_a"
        _register_entity(hass, "entry_device_a", entity_id)

        coordinator = hass.data[DOMAIN]["entry_device_a"]
        mock_orchestrator = AsyncMock()
        coordinator._orchestrator = mock_orchestrator

        # Call the service
        await hass.services.async_call(
            DOMAIN,
            "reset_learning",
            {"entity_id": entity_id},
            blocking=True,
        )

        # Verify reset_all_learning_data was called WITH a device_id argument
        mock_orchestrator.reset_all_learning_data.assert_awaited_once()
        call_kwargs = mock_orchestrator.reset_all_learning_data.call_args
        assert "device_id" in (call_kwargs.kwargs or {}), (
            "reset_all_learning_data must receive device_id keyword argument"
        )
        assert call_kwargs.kwargs["device_id"] == "entry_device_a"


# ---------------------------------------------------------------------------
# Tests: Multi-device routing
# ---------------------------------------------------------------------------


class TestResetLearningMultiDeviceRouting:
    """Ensure the service targets the correct device when multiple entries exist."""

    @pytest.mark.asyncio
    async def test_service_resets_only_targeted_device(
        self,
        hass: HomeAssistant,
        config_entry_a: MockConfigEntry,
        config_entry_b: MockConfigEntry,
        suppress_full_lifecycle: None,
    ) -> None:
        """With two IHP devices, only the targeted coordinator should be reset.

        FAILS with original closure-based bug (only last-registered device was reset).
        PASSES with fix (entity_id dispatches to correct coordinator).
        """
        from custom_components.intelligent_heating_pilot import async_setup_entry

        await async_setup_entry(hass, config_entry_a)
        await async_setup_entry(hass, config_entry_b)

        entity_id_a = f"sensor.{DOMAIN}_anticipated_start_time_a"
        entity_id_b = f"sensor.{DOMAIN}_anticipated_start_time_b"
        _register_entity(hass, "entry_device_a", entity_id_a)
        _register_entity(hass, "entry_device_b", entity_id_b)

        coordinator_a = hass.data[DOMAIN]["entry_device_a"]
        coordinator_b = hass.data[DOMAIN]["entry_device_b"]
        mock_orch_a = AsyncMock()
        mock_orch_b = AsyncMock()
        coordinator_a._orchestrator = mock_orch_a
        coordinator_b._orchestrator = mock_orch_b

        # Target device A only
        await hass.services.async_call(
            DOMAIN,
            "reset_learning",
            {"entity_id": entity_id_a},
            blocking=True,
        )

        mock_orch_a.reset_all_learning_data.assert_awaited_once()
        mock_orch_b.reset_all_learning_data.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_service_resets_device_b_when_targeted(
        self,
        hass: HomeAssistant,
        config_entry_a: MockConfigEntry,
        config_entry_b: MockConfigEntry,
        suppress_full_lifecycle: None,
    ) -> None:
        """Targeting device B must reset B and leave A untouched."""
        from custom_components.intelligent_heating_pilot import async_setup_entry

        await async_setup_entry(hass, config_entry_a)
        await async_setup_entry(hass, config_entry_b)

        entity_id_a = f"sensor.{DOMAIN}_anticipated_start_time_a"
        entity_id_b = f"sensor.{DOMAIN}_anticipated_start_time_b"
        _register_entity(hass, "entry_device_a", entity_id_a)
        _register_entity(hass, "entry_device_b", entity_id_b)

        coordinator_a = hass.data[DOMAIN]["entry_device_a"]
        coordinator_b = hass.data[DOMAIN]["entry_device_b"]
        mock_orch_a = AsyncMock()
        mock_orch_b = AsyncMock()
        coordinator_a._orchestrator = mock_orch_a
        coordinator_b._orchestrator = mock_orch_b

        # Target device B
        await hass.services.async_call(
            DOMAIN,
            "reset_learning",
            {"entity_id": entity_id_b},
            blocking=True,
        )

        mock_orch_b.reset_all_learning_data.assert_awaited_once()
        mock_orch_a.reset_all_learning_data.assert_not_awaited()


# ---------------------------------------------------------------------------
# Tests: Validation errors surface to caller
# ---------------------------------------------------------------------------


class TestResetLearningValidationErrors:
    """Ensure invalid entity_id raises ServiceValidationError immediately."""

    @pytest.mark.asyncio
    async def test_unknown_entity_raises_service_validation_error(
        self,
        hass: HomeAssistant,
        config_entry_a: MockConfigEntry,
        suppress_full_lifecycle: None,
    ) -> None:
        """Calling the service with an unknown entity_id must raise ServiceValidationError.

        FAILS with original silent-return behaviour (service appeared to succeed).
        PASSES with fix (ServiceValidationError raised → caller gets feedback).
        """
        from custom_components.intelligent_heating_pilot import async_setup_entry

        await async_setup_entry(hass, config_entry_a)

        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(
                DOMAIN,
                "reset_learning",
                {"entity_id": "sensor.does_not_exist"},
                blocking=True,
            )
