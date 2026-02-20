"""Integration tests for async_setup_entry DeviceConfig injection.

Phase: TDD RED - These tests are written BEFORE implementation and should FAIL.

Objective: Validate the end-to-end flow of configuration injection:
1. async_setup_entry() creates HADeviceConfigReader
2. HADeviceConfigReader reads config and creates DeviceConfig
3. DeviceConfig is injected into Coordinator
4. Coordinator uses DeviceConfig throughout its lifecycle

This ensures the complete refactoring works as a cohesive system.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.intelligent_heating_pilot.const import (
    CONF_AUTO_LEARNING,
    CONF_DEAD_TIME_MINUTES,
    CONF_HUMIDITY_IN_ENTITY,
    CONF_LHS_RETENTION_DAYS,
    CONF_SCHEDULER_ENTITIES,
    CONF_VTHERM_ENTITY,
    DOMAIN,
)
from custom_components.intelligent_heating_pilot.domain.interfaces.device_config_reader_interface import (
    DeviceConfig,
)


@pytest.fixture
def config_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Create a config entry with realistic data."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="integration_test_entry",
        data={
            CONF_VTHERM_ENTITY: "climate.integration_vtherm",
            CONF_SCHEDULER_ENTITIES: ["switch.integration_schedule"],
        },
        options={
            CONF_LHS_RETENTION_DAYS: 45,
            CONF_DEAD_TIME_MINUTES: 12.0,
            CONF_AUTO_LEARNING: True,
            CONF_HUMIDITY_IN_ENTITY: "sensor.integration_humidity",
        },
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def suppress_platform_setup(hass: HomeAssistant) -> None:
    """Avoid loader lookups for platform setup during integration tests."""
    hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=True)
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)


@pytest.fixture
def suppress_full_lifecycle(suppress_platform_setup: None) -> None:  # type: ignore
    """Suppress full HeatingApplication lifecycle (for basic config injection tests).

    Includes suppress_platform_setup automatically.

    Mocks:
    - async_load: Prevents actual coordinator initialization
    - setup_listeners: Skips event listener registration
    - async_update: Prevents first update cycle

    Use this when testing configuration reading and injection,
    not when testing actual adapter creation.
    """
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
        yield  # type: ignore


class TestAsyncSetupEntryCreatesDeviceConfigReader:
    """Test that async_setup_entry creates and uses HADeviceConfigReader.

    Phase TDD: RED (tests will FAIL until implementation)

    Objective: Validate that the setup entry point creates a HADeviceConfigReader
    instance to read configuration from config_entry.

    Success Criteria: HADeviceConfigReader is instantiated with hass and config_entry.
    """

    @pytest.mark.asyncio
    async def test_async_setup_entry_instantiates_device_config_reader(
        self,
        hass: HomeAssistant,
        config_entry: MockConfigEntry,
        suppress_full_lifecycle: None,
    ) -> None:
        """Test that async_setup_entry creates HADeviceConfigReader.

        FAILS with current code: HADeviceConfigReader is not used in async_setup_entry
        PASSES with fix: HADeviceConfigReader is instantiated before Coordinator
        """
        from custom_components.intelligent_heating_pilot import async_setup_entry

        # Mock HADeviceConfigReader to track instantiation
        with patch(
            "custom_components.intelligent_heating_pilot.infrastructure.adapters.device_config_reader.HADeviceConfigReader"
        ) as mock_reader_class:
            # Setup mock to return a DeviceConfig with spec_set for strict interface
            mock_reader_instance = MagicMock(spec_set=["get_device_config"])
            mock_reader_instance.get_device_config = AsyncMock(
                return_value=DeviceConfig(
                    device_id=config_entry.entry_id,
                    vtherm_entity_id="climate.integration_vtherm",
                    scheduler_entities=["switch.integration_schedule"],
                )
            )
            mock_reader_class.return_value = mock_reader_instance

            # WHEN: Setting up entry
            result = await async_setup_entry(hass, config_entry)

            # THEN: HADeviceConfigReader should be instantiated
            mock_reader_class.assert_called_once_with(hass, config_entry)
            assert result is True
            # Verify coordinator is in hass.data with config injected
            assert config_entry.entry_id in hass.data[DOMAIN]

    @pytest.mark.asyncio
    async def test_async_setup_entry_calls_get_device_config(
        self,
        hass: HomeAssistant,
        config_entry: MockConfigEntry,
        suppress_full_lifecycle: None,
    ) -> None:
        """Test that async_setup_entry calls get_device_config().

        FAILS with current code: get_device_config is not called
        PASSES with fix: get_device_config is called with entry_id
        """
        from custom_components.intelligent_heating_pilot import async_setup_entry

        # Mock HADeviceConfigReader with strict interface
        with patch(
            "custom_components.intelligent_heating_pilot.infrastructure.adapters.device_config_reader.HADeviceConfigReader"
        ) as mock_reader_class:
            mock_reader_instance = MagicMock(spec_set=["get_device_config"])
            mock_reader_instance.get_device_config = AsyncMock(
                return_value=DeviceConfig(
                    device_id=config_entry.entry_id,
                    vtherm_entity_id="climate.vtherm",
                    scheduler_entities=[],
                )
            )
            mock_reader_class.return_value = mock_reader_instance

            # WHEN: Setting up entry
            await async_setup_entry(hass, config_entry)

            # THEN: get_device_config should be called
            mock_reader_instance.get_device_config.assert_called_once_with(config_entry.entry_id)


class TestAsyncSetupEntryInjectsDeviceConfigIntoCoordinator:
    """Test that async_setup_entry injects DeviceConfig into Coordinator.

    Phase TDD: RED (tests will FAIL until implementation)

    Objective: Validate that the DeviceConfig returned by HADeviceConfigReader
    is passed to the Coordinator constructor.

    Success Criteria: Coordinator is instantiated with the DeviceConfig parameter.
    """

    @pytest.mark.asyncio
    async def test_async_setup_entry_passes_device_config_to_coordinator(
        self,
        hass: HomeAssistant,
        config_entry: MockConfigEntry,
        suppress_full_lifecycle: None,
    ) -> None:
        """Test that DeviceConfig is injected into Coordinator constructor.

        FAILS with current code: Coordinator is created without device_config parameter
        PASSES with fix: Coordinator receives device_config from HADeviceConfigReader
        """
        from custom_components.intelligent_heating_pilot import async_setup_entry

        # GIVEN: A specific DeviceConfig from reader
        expected_device_config = DeviceConfig(
            device_id=config_entry.entry_id,
            vtherm_entity_id="climate.injected_vtherm",
            scheduler_entities=["switch.injected_schedule"],
            humidity_in_entity_id="sensor.injected_humidity",
            lhs_retention_days=80,
            dead_time_minutes=18.5,
            auto_learning=False,
        )

        # Mock HADeviceConfigReader to return this config
        with patch(
            "custom_components.intelligent_heating_pilot.infrastructure.adapters.device_config_reader.HADeviceConfigReader"
        ) as mock_reader_class:
            mock_reader_instance = MagicMock(spec_set=["get_device_config"])
            mock_reader_instance.get_device_config = AsyncMock(return_value=expected_device_config)
            mock_reader_class.return_value = mock_reader_instance

            # WHEN: Setting up entry
            await async_setup_entry(hass, config_entry)

            # THEN: Coordinator should hold the injected DeviceConfig
            coordinator = hass.data[DOMAIN][config_entry.entry_id]
            assert coordinator._device_config == expected_device_config


class TestEndToEndConfigInjectionFlow:
    """Test the complete end-to-end configuration injection flow.

    Phase TDD: RED (tests will FAIL until implementation)

    Objective: Validate the entire chain:
    config_entry → HADeviceConfigReader → DeviceConfig → Coordinator → Adapters

    Success Criteria: Configuration values flow correctly from config_entry
    through the entire system without duplication or loss.
    """

    @pytest.mark.asyncio
    async def test_end_to_end_config_flows_from_entry_to_coordinator(
        self,
        hass: HomeAssistant,
        config_entry: MockConfigEntry,
        suppress_full_lifecycle: None,
    ) -> None:
        """Test that config values flow end-to-end through the system.

        FAILS with current code: Config is read multiple times, duplicated logic
        PASSES with fix: Config read once by HADeviceConfigReader, injected everywhere

        This test validates the complete refactoring objective:
        - Single source of truth (HADeviceConfigReader)
        - No duplication (_get_config_value removed)
        - Clean dependency injection
        """
        from custom_components.intelligent_heating_pilot import async_setup_entry

        # GIVEN: Config entry with specific values
        hass.config_entries.async_update_entry(
            config_entry,
            data={
                CONF_VTHERM_ENTITY: "climate.end_to_end_vtherm",
                CONF_SCHEDULER_ENTITIES: ["switch.end_to_end_schedule"],
            },
            options={
                CONF_LHS_RETENTION_DAYS: 100,  # Override from options
                CONF_DEAD_TIME_MINUTES: 30.0,
                CONF_AUTO_LEARNING: False,  # Explicitly disabled
            },
        )

        # WHEN: Setting up entry (using REAL HADeviceConfigReader)
        await async_setup_entry(hass, config_entry)

        # THEN: Coordinator should receive DeviceConfig with correct values
        coordinator = hass.data[DOMAIN][config_entry.entry_id]
        device_config = coordinator._device_config

        assert device_config.device_id == config_entry.entry_id
        assert device_config.vtherm_entity_id == "climate.end_to_end_vtherm"
        assert device_config.scheduler_entities == ["switch.end_to_end_schedule"]
        assert device_config.lhs_retention_days == 100  # From options
        assert device_config.dead_time_minutes == 30.0
        assert device_config.auto_learning is False

    @pytest.mark.asyncio
    async def test_coordinator_uses_injected_config_for_adapters(
        self,
        hass: HomeAssistant,
        config_entry: MockConfigEntry,
        suppress_full_lifecycle: None,
    ) -> None:
        """Test that Coordinator receives and stores injected DeviceConfig.

        Phase TDD: Integration test validating config injection through real reader.

        VALIDATES: Injected DeviceConfig values are accessible in Coordinator
        and would be used during async_load (adapter creation).

        This test uses suppress_full_lifecycle to skip the actual adapter creation
        and focuses on verifying the config was correctly read and injected.
        """
        from custom_components.intelligent_heating_pilot import async_setup_entry

        # GIVEN: Config entry with specific device values
        hass.config_entries.async_update_entry(
            config_entry,
            data={
                CONF_VTHERM_ENTITY: "climate.test_vtherm",
                CONF_SCHEDULER_ENTITIES: ["switch.test_schedule"],
            },
            options={
                CONF_LHS_RETENTION_DAYS: 60,
            },
        )

        # WHEN: Setting up entry (async_load is mocked by suppress_full_lifecycle)
        await async_setup_entry(hass, config_entry)

        # THEN: Coordinator should have DeviceConfig with values from config_entry
        coordinator = hass.data[DOMAIN][config_entry.entry_id]
        device_config = coordinator._device_config

        # These values come from config_entry, read by HADeviceConfigReader
        assert device_config.vtherm_entity_id == "climate.test_vtherm"
        assert device_config.scheduler_entities == ["switch.test_schedule"]
        assert device_config.lhs_retention_days == 60  # From DeviceConfig, used by adapters


class TestConfigurationUpdateFlow:
    """Test that configuration updates trigger proper reloading.

    Phase TDD: RED (optional advanced test)

    Objective: Validate that when config_entry.options change, the system
    re-reads configuration via HADeviceConfigReader and updates the Coordinator.

    Success Criteria: Options changes trigger entry reload with new DeviceConfig.
    """

    @pytest.mark.asyncio
    async def test_options_update_triggers_config_reload(
        self,
        hass: HomeAssistant,
        config_entry: MockConfigEntry,
        suppress_full_lifecycle: None,
    ) -> None:
        """Test that changing options triggers proper config reload.

        Uses suppress_full_lifecycle to mock lifecycle methods.

        FAILS with current code: May not properly reload with new config
        PASSES with fix: HADeviceConfigReader re-reads config, new DeviceConfig injected

        This ensures the refactoring maintains Home Assistant's config flow behavior.
        """
        from custom_components.intelligent_heating_pilot import (
            async_setup_entry,
            async_unload_entry,
        )

        # GIVEN: Initial setup
        hass.config_entries.async_update_entry(
            config_entry,
            options={CONF_LHS_RETENTION_DAYS: 30},
        )

        # Initial setup
        await async_setup_entry(hass, config_entry)
        coordinator = hass.data[DOMAIN][config_entry.entry_id]
        assert coordinator._device_config.lhs_retention_days == 30

        # WHEN: User changes options
        hass.config_entries.async_update_entry(
            config_entry,
            options={CONF_LHS_RETENTION_DAYS: 90},
        )

        # Simulate HA reload (unload then setup again)
        await async_unload_entry(hass, config_entry)
        await async_setup_entry(hass, config_entry)

        # THEN: New DeviceConfig should reflect updated options
        coordinator = hass.data[DOMAIN][config_entry.entry_id]
        assert coordinator._device_config.lhs_retention_days == 90
