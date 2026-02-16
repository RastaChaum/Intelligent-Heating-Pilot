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
def mock_hass() -> Mock:
    """Create a mock Home Assistant instance for integration tests."""
    hass = MagicMock(spec=HomeAssistant)
    hass.data = {}
    hass.states = MagicMock()
    hass.bus = MagicMock()
    hass.bus.async_fire = MagicMock()
    hass.services = MagicMock()
    hass.config = MagicMock()
    hass.config.config_dir = "/tmp"
    hass.config_entries = MagicMock()
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    hass.async_create_task = MagicMock()
    hass.loop = MagicMock()
    hass.loop.time = MagicMock(return_value=0.0)
    hass.loop.call_at = MagicMock(return_value=MagicMock())
    return hass


@pytest.fixture
def mock_config_entry() -> Mock:
    """Create a mock config entry with realistic data."""
    config_entry = MagicMock()
    config_entry.entry_id = "integration_test_entry"
    config_entry.data = {
        CONF_VTHERM_ENTITY: "climate.integration_vtherm",
        CONF_SCHEDULER_ENTITIES: ["switch.integration_schedule"],
    }
    config_entry.options = {
        CONF_LHS_RETENTION_DAYS: 45,
        CONF_DEAD_TIME_MINUTES: 12.0,
        CONF_AUTO_LEARNING: True,
        CONF_HUMIDITY_IN_ENTITY: "sensor.integration_humidity",
    }
    config_entry.add_update_listener = MagicMock(return_value=lambda: None)
    return config_entry


class TestAsyncSetupEntryCreatesDeviceConfigReader:
    """Test that async_setup_entry creates and uses HADeviceConfigReader.

    Phase TDD: RED (tests will FAIL until implementation)

    Objective: Validate that the setup entry point creates a HADeviceConfigReader
    instance to read configuration from config_entry.

    Success Criteria: HADeviceConfigReader is instantiated with hass and config_entry.
    """

    @pytest.mark.asyncio
    async def test_async_setup_entry_instantiates_device_config_reader(
        self, mock_hass: Mock, mock_config_entry: Mock
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
            # Setup mock to return a DeviceConfig
            mock_reader_instance = MagicMock()
            mock_reader_instance.get_device_config = AsyncMock(
                return_value=DeviceConfig(
                    device_id=mock_config_entry.entry_id,
                    vtherm_entity_id="climate.integration_vtherm",
                    scheduler_entities=["switch.integration_schedule"],
                )
            )
            mock_reader_class.return_value = mock_reader_instance

            # Mock Coordinator to avoid full initialization
            with patch(
                "custom_components.intelligent_heating_pilot.HeatingApplication"
            ) as mock_coordinator_class:
                mock_coordinator = MagicMock()
                mock_coordinator.async_load = AsyncMock()
                mock_coordinator_class.return_value = mock_coordinator

                # WHEN: Setting up entry
                result = await async_setup_entry(mock_hass, mock_config_entry)

                # THEN: HADeviceConfigReader should be instantiated
                mock_reader_class.assert_called_once_with(mock_hass, mock_config_entry)
                assert result is True

    @pytest.mark.asyncio
    async def test_async_setup_entry_calls_get_device_config(
        self, mock_hass: Mock, mock_config_entry: Mock
    ) -> None:
        """Test that async_setup_entry calls get_device_config().

        FAILS with current code: get_device_config is not called
        PASSES with fix: get_device_config is called with entry_id
        """
        from custom_components.intelligent_heating_pilot import async_setup_entry

        # Mock HADeviceConfigReader
        with patch(
            "custom_components.intelligent_heating_pilot.infrastructure.adapters.device_config_reader.HADeviceConfigReader"
        ) as mock_reader_class:
            mock_reader_instance = MagicMock()
            mock_reader_instance.get_device_config = AsyncMock(
                return_value=DeviceConfig(
                    device_id=mock_config_entry.entry_id,
                    vtherm_entity_id="climate.vtherm",
                    scheduler_entities=[],
                )
            )
            mock_reader_class.return_value = mock_reader_instance

            # Mock Coordinator
            with patch(
                "custom_components.intelligent_heating_pilot.HeatingApplication"
            ) as mock_coordinator_class:
                mock_coordinator = MagicMock()
                mock_coordinator.async_load = AsyncMock()
                mock_coordinator_class.return_value = mock_coordinator

                # WHEN: Setting up entry
                await async_setup_entry(mock_hass, mock_config_entry)

                # THEN: get_device_config should be called
                mock_reader_instance.get_device_config.assert_called_once_with(
                    mock_config_entry.entry_id
                )


class TestAsyncSetupEntryInjectsDeviceConfigIntoCoordinator:
    """Test that async_setup_entry injects DeviceConfig into Coordinator.

    Phase TDD: RED (tests will FAIL until implementation)

    Objective: Validate that the DeviceConfig returned by HADeviceConfigReader
    is passed to the Coordinator constructor.

    Success Criteria: Coordinator is instantiated with the DeviceConfig parameter.
    """

    @pytest.mark.asyncio
    async def test_async_setup_entry_passes_device_config_to_coordinator(
        self, mock_hass: Mock, mock_config_entry: Mock
    ) -> None:
        """Test that DeviceConfig is injected into Coordinator constructor.

        FAILS with current code: Coordinator is created without device_config parameter
        PASSES with fix: Coordinator receives device_config from HADeviceConfigReader
        """
        from custom_components.intelligent_heating_pilot import async_setup_entry

        # GIVEN: A specific DeviceConfig from reader
        expected_device_config = DeviceConfig(
            device_id=mock_config_entry.entry_id,
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
            mock_reader_instance = MagicMock()
            mock_reader_instance.get_device_config = AsyncMock(return_value=expected_device_config)
            mock_reader_class.return_value = mock_reader_instance

            # Mock Coordinator to track constructor calls
            with patch(
                "custom_components.intelligent_heating_pilot.HeatingApplication"
            ) as mock_coordinator_class:
                mock_coordinator = MagicMock()
                mock_coordinator.async_load = AsyncMock()
                mock_coordinator_class.return_value = mock_coordinator

                # WHEN: Setting up entry
                await async_setup_entry(mock_hass, mock_config_entry)

                # THEN: Coordinator should be called with DeviceConfig
                mock_coordinator_class.assert_called_once()
                call_args, call_kwargs = mock_coordinator_class.call_args
                device_config = call_kwargs.get("device_config")
                if device_config is None and len(call_args) > 1:
                    device_config = call_args[1]
                assert device_config == expected_device_config


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
        self, mock_hass: Mock, mock_config_entry: Mock
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
        mock_config_entry.data = {
            CONF_VTHERM_ENTITY: "climate.end_to_end_vtherm",
            CONF_SCHEDULER_ENTITIES: ["switch.end_to_end_schedule"],
        }
        mock_config_entry.options = {
            CONF_LHS_RETENTION_DAYS: 100,  # Override from options
            CONF_DEAD_TIME_MINUTES: 30.0,
            CONF_AUTO_LEARNING: False,  # Explicitly disabled
        }

        # WHEN: Setting up entry (using REAL HADeviceConfigReader)
        # We only mock the Coordinator to avoid full HA setup
        with patch(
            "custom_components.intelligent_heating_pilot.HeatingApplication"
        ) as mock_coordinator_class:
            mock_coordinator = MagicMock()
            mock_coordinator.async_load = AsyncMock()
            mock_coordinator_class.return_value = mock_coordinator

            await async_setup_entry(mock_hass, mock_config_entry)

            # THEN: Coordinator should receive DeviceConfig with correct values
            mock_coordinator_class.assert_called_once()
            call_args, call_kwargs = mock_coordinator_class.call_args

            # Verify DeviceConfig was passed
            device_config = call_kwargs.get("device_config")
            if device_config is None and len(call_args) > 1:
                device_config = call_args[1]
            assert device_config is not None

            # Verify all values are correct
            assert device_config.device_id == mock_config_entry.entry_id
            assert device_config.vtherm_entity_id == "climate.end_to_end_vtherm"
            assert device_config.scheduler_entities == ["switch.end_to_end_schedule"]
            assert device_config.lhs_retention_days == 100  # From options
            assert device_config.dead_time_minutes == 30.0
            assert device_config.auto_learning is False

    @pytest.mark.asyncio
    async def test_coordinator_uses_injected_config_in_async_load(
        self, mock_hass: Mock, mock_config_entry: Mock
    ) -> None:
        """Test that Coordinator uses DeviceConfig when creating adapters.

        FAILS with current code: Coordinator reads config_entry in async_load
        PASSES with fix: Coordinator uses self._device_config in async_load

        This validates that the injection is actually USED, not just accepted.
        """
        from custom_components.intelligent_heating_pilot import async_setup_entry

        # GIVEN: Config with specific values
        mock_config_entry.data = {
            CONF_VTHERM_ENTITY: "climate.adapter_test_vtherm",
            CONF_SCHEDULER_ENTITIES: ["switch.adapter_test"],
        }
        mock_config_entry.options = {
            CONF_LHS_RETENTION_DAYS: 55,
        }

        # WHEN: Setting up entry and loading coordinator
        # We'll partially mock to verify adapter creation
        with patch(
            "custom_components.intelligent_heating_pilot.heating_application.HALhsStorage"
        ) as mock_storage_class:
            mock_storage = MagicMock()
            mock_storage.get_learned_heating_slope = AsyncMock(return_value=2.0)
            mock_storage_class.return_value = mock_storage

            with patch(
                "custom_components.intelligent_heating_pilot.heating_application.HASchedulerReader"
            ) as mock_scheduler_class:
                mock_scheduler = MagicMock()
                mock_scheduler_class.return_value = mock_scheduler

                # Note: We need to mock other adapters and app service too
                with patch(
                    "custom_components.intelligent_heating_pilot.heating_application.HAHeatingCycleStorage"
                ), patch(
                    "custom_components.intelligent_heating_pilot.heating_application.HASchedulerCommander"
                ), patch(
                    "custom_components.intelligent_heating_pilot.heating_application.HAClimateCommander"
                ), patch(
                    "custom_components.intelligent_heating_pilot.heating_application.HAEnvironmentReader"
                ), patch(
                    "custom_components.intelligent_heating_pilot.heating_application.HATimerScheduler"
                ), patch(
                    "custom_components.intelligent_heating_pilot.heating_application.HAClimateDataReader"
                ), patch(
                    "custom_components.intelligent_heating_pilot.heating_application.HAContextReader"
                ), patch(
                    "custom_components.intelligent_heating_pilot.heating_application.HeatingApplicationService"
                ) as mock_app_service_class, patch(
                    "custom_components.intelligent_heating_pilot.heating_application.HAEventBridge"
                ), patch(
                    "custom_components.intelligent_heating_pilot.heating_application.HeatingCycleLifecycleManagerFactory"
                ), patch(
                    "custom_components.intelligent_heating_pilot.heating_application.LhsLifecycleManagerFactory"
                ) as mock_lhs_factory:
                    # Ensure LhsLifecycleManagerFactory returns a mock with async methods
                    mock_lhs_manager = MagicMock()
                    mock_lhs_manager.get_global_lhs = AsyncMock(return_value=None)
                    mock_lhs_factory.create.return_value = mock_lhs_manager

                    # Ensure HeatingApplicationService mock returns proper sub-services
                    mock_app_service = MagicMock()
                    mock_app_service.get_heating_cycle_service.return_value = MagicMock()
                    mock_app_service.get_global_lhs_calculator.return_value = MagicMock()
                    mock_app_service.get_contextual_lhs_calculator.return_value = MagicMock()
                    mock_app_service_class.return_value = mock_app_service
                    await async_setup_entry(mock_hass, mock_config_entry)

                    # Get the coordinator from hass.data
                    coordinator = mock_hass.data[DOMAIN][mock_config_entry.entry_id]

                    # Trigger async_load explicitly if not done by setup
                    if hasattr(coordinator, "async_load"):
                        await coordinator.async_load()

                    # THEN: Adapters should be created with values from DeviceConfig
                    # HALhsStorage should get retention_days=55 from DeviceConfig
                    mock_storage_class.assert_called()
                    storage_kwargs = mock_storage_class.call_args[1]
                    assert storage_kwargs["retention_days"] == 55

                    # HASchedulerReader should get entities from DeviceConfig
                    mock_scheduler_class.assert_called()
                    scheduler_args = mock_scheduler_class.call_args[0]
                    assert scheduler_args[1] == ["switch.adapter_test"]


class TestConfigurationUpdateFlow:
    """Test that configuration updates trigger proper reloading.

    Phase TDD: RED (optional advanced test)

    Objective: Validate that when config_entry.options change, the system
    re-reads configuration via HADeviceConfigReader and updates the Coordinator.

    Success Criteria: Options changes trigger entry reload with new DeviceConfig.
    """

    @pytest.mark.asyncio
    async def test_options_update_triggers_config_reload(
        self, mock_hass: Mock, mock_config_entry: Mock
    ) -> None:
        """Test that changing options triggers proper config reload.

        FAILS with current code: May not properly reload with new config
        PASSES with fix: HADeviceConfigReader re-reads config, new DeviceConfig injected

        This ensures the refactoring maintains Home Assistant's config flow behavior.
        """
        from custom_components.intelligent_heating_pilot import (
            async_setup_entry,
            async_unload_entry,
        )

        # GIVEN: Initial setup
        mock_config_entry.options = {CONF_LHS_RETENTION_DAYS: 30}

        with patch(
            "custom_components.intelligent_heating_pilot.HeatingApplication"
        ) as mock_coordinator_class:
            mock_coordinator = MagicMock()
            mock_coordinator.async_load = AsyncMock()
            mock_coordinator.async_cleanup = AsyncMock()
            mock_coordinator_class.return_value = mock_coordinator

            # Initial setup
            await async_setup_entry(mock_hass, mock_config_entry)
            call_args, call_kwargs = mock_coordinator_class.call_args
            initial_device_config = call_kwargs.get("device_config")
            if initial_device_config is None and len(call_args) > 1:
                initial_device_config = call_args[1]
            assert initial_device_config.lhs_retention_days == 30

            # WHEN: User changes options
            mock_config_entry.options = {CONF_LHS_RETENTION_DAYS: 90}  # Changed!

            # Simulate HA reload (unload then setup again)
            await async_unload_entry(mock_hass, mock_config_entry)
            await async_setup_entry(mock_hass, mock_config_entry)

            # THEN: New DeviceConfig should reflect updated options
            call_args, call_kwargs = mock_coordinator_class.call_args
            updated_device_config = call_kwargs.get("device_config")
            if updated_device_config is None and len(call_args) > 1:
                updated_device_config = call_args[1]
            assert updated_device_config.lhs_retention_days == 90
