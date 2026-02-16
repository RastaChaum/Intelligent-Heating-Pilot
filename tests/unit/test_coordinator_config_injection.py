"""Unit tests for HeatingApplication DeviceConfig injection refactoring.

Phase: TDD RED - These tests are written BEFORE implementation and should FAIL.

Objective: Validate that the refactored HeatingApplication correctly receives and uses
DeviceConfig via dependency injection instead of reading config_entry directly.

This eliminates code duplication (_get_config_value) and respects DDD principles
by keeping configuration reading in the infrastructure layer.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from unittest.mock import MagicMock, Mock

import pytest

from custom_components.intelligent_heating_pilot.const import (
    CONF_AUTO_LEARNING,
    CONF_CLOUD_COVER_ENTITY,
    CONF_HUMIDITY_IN_ENTITY,
    CONF_HUMIDITY_OUT_ENTITY,
    CONF_LHS_RETENTION_DAYS,
    CONF_SCHEDULER_ENTITIES,
    CONF_VTHERM_ENTITY,
)
from custom_components.intelligent_heating_pilot.domain.interfaces.device_config_reader_interface import (
    DeviceConfig,
)


@pytest.fixture
def mock_hass() -> Mock:
    """Create a mock Home Assistant instance."""
    hass = MagicMock()
    hass.data = {}
    hass.states = MagicMock()
    hass.bus = MagicMock()
    hass.bus.async_fire = MagicMock()
    return hass


@pytest.fixture
def mock_config_entry() -> Mock:
    """Create a mock config entry."""
    config_entry = MagicMock()
    config_entry.entry_id = "test_device_id"
    config_entry.data = {
        CONF_VTHERM_ENTITY: "climate.vtherm",
        CONF_SCHEDULER_ENTITIES: ["switch.schedule1"],
    }
    config_entry.options = {}
    return config_entry


@pytest.fixture
def sample_device_config() -> DeviceConfig:
    """Create a DeviceConfig with all fields populated.

    This represents the configuration that will be injected into the Coordinator.
    """
    return DeviceConfig(
        device_id="test_device_id",
        vtherm_entity_id="climate.vtherm",
        scheduler_entities=["switch.schedule1", "switch.schedule2"],
        humidity_in_entity_id="sensor.humidity_indoor",
        humidity_out_entity_id="sensor.humidity_outdoor",
        cloud_cover_entity_id="sensor.cloud_cover",
        lhs_retention_days=60,
        dead_time_minutes=15.5,
        auto_learning=False,
    )


class TestCoordinatorAcceptsDeviceConfig:
    """Test that Coordinator constructor accepts DeviceConfig parameter.

    Phase TDD: RED (tests will FAIL until implementation)

    Objective: Validate that the refactored Coordinator.__init__() signature includes
    a DeviceConfig parameter and stores it for use.

    Success Criteria: After implementation, Coordinator can be instantiated with
    DeviceConfig and stores it in self._device_config.
    """

    def test_coordinator_constructor_accepts_device_config(
        self, mock_hass: Mock, mock_config_entry: Mock, sample_device_config: DeviceConfig
    ) -> None:
        """Test that Coordinator accepts ONLY DeviceConfig in constructor.

        FAILS with current code: Coordinator requires config_entry parameter
        PASSES with fix: Coordinator only requires hass and device_config
        """
        from custom_components.intelligent_heating_pilot.heating_application import (
            HeatingApplication,
        )

        # WHEN: Creating coordinator with ONLY hass and device_config (NO config_entry!)
        coordinator = HeatingApplication(
            hass=mock_hass,
            device_config=sample_device_config,  # ONLY: Injected config
        )

        # THEN: Coordinator should be created successfully
        assert coordinator is not None
        assert hasattr(coordinator, "_device_config")
        assert coordinator._device_config == sample_device_config

    def test_coordinator_stores_device_config_immutably(
        self, mock_hass: Mock, mock_config_entry: Mock, sample_device_config: DeviceConfig
    ) -> None:
        """Test that Coordinator stores DeviceConfig as immutable reference.

        FAILS with current code: Coordinator doesn't have _device_config attribute
        PASSES with fix: Coordinator stores frozen DeviceConfig
        """
        from custom_components.intelligent_heating_pilot.heating_application import (
            HeatingApplication,
        )

        # WHEN: Creating coordinator with only hass and device_config
        coordinator = HeatingApplication(
            hass=mock_hass,
            device_config=sample_device_config,
        )

        # THEN: DeviceConfig should be stored and immutable
        assert coordinator._device_config is sample_device_config
        # DeviceConfig is a frozen dataclass, should raise FrozenInstanceError
        with pytest.raises(FrozenInstanceError):
            coordinator._device_config.lhs_retention_days = 999  # type: ignore


class TestCoordinatorUsesInjectedConfig:
    """Test that Coordinator uses DeviceConfig instead of reading config_entry.

    Phase TDD: RED (tests will FAIL until implementation)

    Objective: Validate that Coordinator extracts all configuration from the injected
    DeviceConfig value object, NOT from config_entry.data or config_entry.options.

    Success Criteria: Coordinator attributes are populated from DeviceConfig,
    _get_config_value() is not called during initialization.
    """

    def test_coordinator_extracts_vtherm_from_device_config(
        self, mock_hass: Mock, mock_config_entry: Mock, sample_device_config: DeviceConfig
    ) -> None:
        """Test that Coordinator uses DeviceConfig.vtherm_entity_id.

        FAILS with current code: Coordinator extracts from config_entry, not DeviceConfig
        PASSES with fix: self._vtherm_entity comes from device_config.vtherm_entity_id
        """
        from custom_components.intelligent_heating_pilot.heating_application import (
            HeatingApplication,
        )

        # GIVEN: DeviceConfig with specific vtherm entity
        device_config = DeviceConfig(
            device_id="test_id",
            vtherm_entity_id="climate.injected_vtherm",  # From DeviceConfig
            scheduler_entities=[],
        )

        # AND: config_entry has DIFFERENT value (should be IGNORED)
        mock_config_entry.data[CONF_VTHERM_ENTITY] = "climate.config_entry_vtherm"

        # WHEN: Creating coordinator with injected DeviceConfig (no config_entry needed)
        coordinator = HeatingApplication(
            hass=mock_hass,
            device_config=device_config,
        )

        # THEN: Coordinator should use value from DeviceConfig
        assert coordinator._vtherm_entity == "climate.injected_vtherm"

    def test_coordinator_extracts_scheduler_entities_from_device_config(
        self, mock_hass: Mock, mock_config_entry: Mock, sample_device_config: DeviceConfig
    ) -> None:
        """Test that Coordinator uses DeviceConfig.scheduler_entities.

        FAILS with current code: Coordinator calls _get_scheduler_entities()
        PASSES with fix: self._scheduler_entities comes from device_config.scheduler_entities
        """
        from custom_components.intelligent_heating_pilot.heating_application import (
            HeatingApplication,
        )

        # GIVEN: DeviceConfig with specific scheduler entities
        device_config = DeviceConfig(
            device_id="test_id",
            vtherm_entity_id="climate.vtherm",
            scheduler_entities=["switch.injected_1", "switch.injected_2"],
        )

        # AND: config_entry has DIFFERENT values (should be IGNORED)
        mock_config_entry.data[CONF_SCHEDULER_ENTITIES] = ["switch.config_entry_1"]

        # WHEN: Creating coordinator (only hass and device_config)
        coordinator = HeatingApplication(
            hass=mock_hass,
            device_config=device_config,
        )

        # THEN: Should use DeviceConfig values
        assert coordinator._scheduler_entities == ["switch.injected_1", "switch.injected_2"]

    def test_coordinator_extracts_all_optional_sensors_from_device_config(
        self, mock_hass: Mock, mock_config_entry: Mock
    ) -> None:
        """Test that Coordinator uses DeviceConfig for all optional sensor entities.

        FAILS with current code: Coordinator reads from config_entry
        PASSES with fix: All sensor IDs come from device_config
        """
        from custom_components.intelligent_heating_pilot.heating_application import (
            HeatingApplication,
        )

        # GIVEN: DeviceConfig with all optional sensors
        device_config = DeviceConfig(
            device_id="test_id",
            vtherm_entity_id="climate.vtherm",
            scheduler_entities=[],
            humidity_in_entity_id="sensor.injected_humidity_in",
            humidity_out_entity_id="sensor.injected_humidity_out",
            cloud_cover_entity_id="sensor.injected_cloud_cover",
        )

        # AND: config_entry has DIFFERENT values (should be IGNORED)
        mock_config_entry.data.update(
            {
                CONF_HUMIDITY_IN_ENTITY: "sensor.config_humidity_in",
                CONF_HUMIDITY_OUT_ENTITY: "sensor.config_humidity_out",
                CONF_CLOUD_COVER_ENTITY: "sensor.config_cloud_cover",
            }
        )

        # WHEN: Creating coordinator (clean DDD - no config_entry)
        coordinator = HeatingApplication(
            hass=mock_hass,
            device_config=device_config,
        )

        # THEN: Should use DeviceConfig values
        assert coordinator._humidity_in == "sensor.injected_humidity_in"
        assert coordinator._humidity_out == "sensor.injected_humidity_out"
        assert coordinator._cloud_cover == "sensor.injected_cloud_cover"


class TestCoordinatorUsesAllDeviceConfigParameters:
    """Test that all DeviceConfig parameters are correctly used.

    Phase TDD: RED (tests will FAIL until implementation)

    Objective: Validate that ALL configuration parameters from DeviceConfig
    are extracted and used by the Coordinator (lhs_retention_days, dead_time, etc.).

    Success Criteria: Every field in DeviceConfig is accessible via Coordinator
    private attributes (_lhs_retention_days, _dead_time_minutes, etc.).
    """

    def test_coordinator_uses_lhs_retention_days_from_device_config(
        self, mock_hass: Mock, mock_config_entry: Mock
    ) -> None:
        """Test that Coordinator uses DeviceConfig.lhs_retention_days.

        FAILS with current code: Reads from config_entry
        PASSES with fix: Uses device_config.lhs_retention_days
        """
        from custom_components.intelligent_heating_pilot.heating_application import (
            HeatingApplication,
        )

        # GIVEN: DeviceConfig with specific retention days
        device_config = DeviceConfig(
            device_id="test_id",
            vtherm_entity_id="climate.vtherm",
            scheduler_entities=[],
            lhs_retention_days=75,  # From DeviceConfig
        )

        # AND: config_entry has different value
        mock_config_entry.data[CONF_LHS_RETENTION_DAYS] = 30

        # WHEN: Creating coordinator
        coordinator = HeatingApplication(
            hass=mock_hass,
            device_config=device_config,
        )

        # THEN: Should use DeviceConfig value
        assert coordinator._data_retention_days == 75

    def test_coordinator_uses_dead_time_from_device_config(
        self, mock_hass: Mock, mock_config_entry: Mock
    ) -> None:
        """Test that Coordinator uses DeviceConfig.dead_time_minutes.

        FAILS with current code: Reads from config_entry
        PASSES with fix: Uses device_config.dead_time_minutes
        """
        from custom_components.intelligent_heating_pilot.heating_application import (
            HeatingApplication,
        )

        # GIVEN: DeviceConfig with specific dead time
        device_config = DeviceConfig(
            device_id="test_id",
            vtherm_entity_id="climate.vtherm",
            scheduler_entities=[],
            dead_time_minutes=20.5,
        )

        # WHEN: Creating coordinator
        coordinator = HeatingApplication(
            hass=mock_hass,
            device_config=device_config,
        )

        # THEN: Should use DeviceConfig value
        assert coordinator._dead_time_minutes == 20.5

    def test_coordinator_uses_auto_learning_from_device_config(
        self, mock_hass: Mock, mock_config_entry: Mock
    ) -> None:
        """Test that Coordinator uses DeviceConfig.auto_learning.

        FAILS with current code: Reads from config_entry
        PASSES with fix: Uses device_config.auto_learning
        """
        from custom_components.intelligent_heating_pilot.heating_application import (
            HeatingApplication,
        )

        # GIVEN: DeviceConfig with auto_learning disabled
        device_config = DeviceConfig(
            device_id="test_id",
            vtherm_entity_id="climate.vtherm",
            scheduler_entities=[],
            auto_learning=False,  # Explicitly disabled
        )

        # AND: config_entry has different value
        mock_config_entry.data[CONF_AUTO_LEARNING] = True

        # WHEN: Creating coordinator
        coordinator = HeatingApplication(
            hass=mock_hass,
            device_config=device_config,
        )

        # THEN: Should use DeviceConfig value
        assert coordinator._auto_learning is False


class TestCoordinatorDoesNotCallGetConfigValue:
    """Test that _get_config_value() is NOT called after refactoring.

    Phase TDD: RED (tests will FAIL until implementation)

    Objective: Validate that the Coordinator no longer calls _get_config_value()
    during initialization, since all config comes from DeviceConfig.

    Success Criteria: After refactoring, _get_config_value() is removed entirely
    because all configuration now comes from the injected DeviceConfig.

    This test validates that the method does not exist on the refactored Coordinator.
    """

    def test_coordinator_init_does_not_call_get_config_value(
        self, mock_hass: Mock, mock_config_entry: Mock, sample_device_config: DeviceConfig
    ) -> None:
        """Test that Coordinator does not have _get_config_value method.

        FAILS with current code: _get_config_value method exists and is called
        PASSES with fix: _get_config_value method is completely removed
        """
        from custom_components.intelligent_heating_pilot.heating_application import (
            HeatingApplication,
        )

        # WHEN: Creating coordinator with DeviceConfig
        coordinator = HeatingApplication(
            hass=mock_hass,
            device_config=sample_device_config,
        )

        # THEN: Coordinator should be created successfully
        assert coordinator is not None
        # AND: _get_config_value method should NOT exist (removed entirely)
        assert not hasattr(
            coordinator, "_get_config_value"
        ), "_get_config_value method should be removed from Coordinator"


class TestCoordinatorAsyncLoadUsesDeviceConfig:
    """Test that async_load() uses DeviceConfig values.

    Phase TDD: RED (tests will FAIL until implementation)

    Objective: Validate that when creating infrastructure adapters in async_load(),
    the Coordinator uses values from its stored DeviceConfig, not from config_entry.

    Success Criteria: Adapters are created with values from self._device_config.
    """

    def test_async_load_uses_device_config_values(
        self, mock_hass: Mock, mock_config_entry: Mock
    ) -> None:
        """Test that Coordinator stores DeviceConfig values for async_load to use.

        FAILS with current code: Coordinator reads from config_entry
        PASSES with fix: Coordinator stores all values from DeviceConfig

        Note: This test validates the coordinator initialization. The actual async_load
        execution is tested in integration tests. Here we verify that all parameters
        from DeviceConfig are stored as instance variables for async_load to use.
        """
        from custom_components.intelligent_heating_pilot.heating_application import (
            HeatingApplication,
        )

        # GIVEN: DeviceConfig with specific values
        device_config = DeviceConfig(
            device_id="test_id",
            vtherm_entity_id="climate.specific_vtherm",
            scheduler_entities=["switch.specific_schedule"],
            humidity_in_entity_id="sensor.specific_humidity_in",
            lhs_retention_days=90,
            dead_time_minutes=25.0,
            auto_learning=True,
        )

        # WHEN: Creating coordinator (only hass and device_config)
        coordinator = HeatingApplication(
            hass=mock_hass,
            device_config=device_config,
        )

        # THEN: Coordinator should store all DeviceConfig values as instance variables
        # which will be used by async_load to create adapters with correct parameters
        assert coordinator._vtherm_entity == "climate.specific_vtherm"
        assert coordinator._scheduler_entities == ["switch.specific_schedule"]
        assert coordinator._humidity_in == "sensor.specific_humidity_in"
        assert coordinator._data_retention_days == 90  # From lhs_retention_days
        assert coordinator._dead_time_minutes == 25.0
        assert coordinator._auto_learning is True


class TestCoordinatorBackwardCompatibility:
    """Test backward compatibility during migration.

    Phase TDD: RED (optional, may be skipped)

    Objective: If we want a gradual migration, validate that Coordinator can
    handle the case where DeviceConfig is NOT provided (fallback behavior).

    This may not be needed if we do a clean break. Include only if requested.

    Success Criteria: Coordinator raises clear error if DeviceConfig is missing,
    or falls back to reading config_entry (deprecated path).
    """

    def test_coordinator_raises_error_if_device_config_not_provided(
        self, mock_hass: Mock, mock_config_entry: Mock
    ) -> None:
        """Test that Coordinator fails gracefully if DeviceConfig not injected.

        FAILS with current code: Coordinator works without DeviceConfig
        PASSES with fix: Coordinator requires DeviceConfig parameter

        This test ensures DeviceConfig is mandatory (no fallback to config_entry).
        """
        from custom_components.intelligent_heating_pilot.heating_application import (
            HeatingApplication,
        )

        # WHEN: Creating coordinator WITHOUT DeviceConfig
        # THEN: Should raise TypeError (missing required argument)
        with pytest.raises(TypeError, match="device_config"):
            HeatingApplication(
                hass=mock_hass,
                # device_config NOT provided - this is required!
            )  # type: ignore
