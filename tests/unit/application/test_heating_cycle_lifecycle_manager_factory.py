"""Unit tests for HeatingCycleLifecycleManagerFactory singleton pattern.

RED tests: These tests should validate the singleton behavior and factory
creation logic for the HeatingCycleLifecycleManager.

Author: QA Engineer
Purpose: Ensure factory correctly implements singleton pattern per device_id
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from custom_components.intelligent_heating_pilot.application.heating_cycle_lifecycle_manager_factory import (
    HeatingCycleLifecycleManagerFactory,
)
from custom_components.intelligent_heating_pilot.domain.interfaces.device_config_reader_interface import (
    DeviceConfig,
)


class TestHeatingCycleLifecycleManagerFactory:
    """Test suite for factory singleton pattern."""

    @pytest.fixture
    def device_config_1(self) -> DeviceConfig:
        """First device configuration."""
        return DeviceConfig(
            device_id="climate.vtherm_1",
            vtherm_entity_id="climate.vtherm_1",
            scheduler_entities=["schedule.heating_1"],
            lhs_retention_days=30,
        )

    @pytest.fixture
    def device_config_2(self) -> DeviceConfig:
        """Second device configuration with different device_id."""
        return DeviceConfig(
            device_id="climate.vtherm_2",
            vtherm_entity_id="climate.vtherm_2",
            scheduler_entities=["schedule.heating_2"],
            lhs_retention_days=30,
        )

    @pytest.fixture
    def mock_hass(self) -> Mock:
        """Mock Home Assistant instance."""
        mock = Mock()
        mock.data = {}
        return mock

    @pytest.fixture
    def mock_dependencies(self) -> dict:
        """Common mock dependencies."""
        return {
            "heating_cycle_service": Mock(),
            "cycle_cache": Mock(),
            "timer_scheduler": Mock(),
            "model_storage": Mock(),
            "lhs_lifecycle_manager": None,
        }

    def test_factory_singleton_same_device_returns_same_instance(
        self,
        mock_hass: Mock,
        device_config_1: DeviceConfig,
        mock_dependencies: dict,
    ) -> None:
        """Test factory returns same instance for same device_id.

        GIVEN: Factory with clean registry
        WHEN: Create manager for device_id twice with same config
        THEN: Same instance returned both times (singleton behavior)
        """
        # Create first manager
        manager1 = HeatingCycleLifecycleManagerFactory.create(
            hass=mock_hass,
            device_config=device_config_1,
            heating_cycle_service=mock_dependencies["heating_cycle_service"],
            cycle_cache=mock_dependencies["cycle_cache"],
            timer_scheduler=mock_dependencies["timer_scheduler"],
            model_storage=mock_dependencies["model_storage"],
            lhs_lifecycle_manager=mock_dependencies["lhs_lifecycle_manager"],
        )

        # Create same manager again
        manager2 = HeatingCycleLifecycleManagerFactory.create(
            hass=mock_hass,
            device_config=device_config_1,
            heating_cycle_service=mock_dependencies["heating_cycle_service"],
            cycle_cache=mock_dependencies["cycle_cache"],
            timer_scheduler=mock_dependencies["timer_scheduler"],
            model_storage=mock_dependencies["model_storage"],
            lhs_lifecycle_manager=mock_dependencies["lhs_lifecycle_manager"],
        )

        # THEN: Same instance
        assert manager1 is manager2

    def test_factory_different_devices_different_instances(
        self,
        mock_hass: Mock,
        device_config_1: DeviceConfig,
        device_config_2: DeviceConfig,
        mock_dependencies: dict,
    ) -> None:
        """Test factory creates different instances for different device_ids.

        GIVEN: Factory with clean registry
        WHEN: Create managers for two different device_ids
        THEN: Different instances created for each device
        """
        # Create manager for device 1
        manager1 = HeatingCycleLifecycleManagerFactory.create(
            hass=mock_hass,
            device_config=device_config_1,
            heating_cycle_service=mock_dependencies["heating_cycle_service"],
            cycle_cache=mock_dependencies["cycle_cache"],
            timer_scheduler=mock_dependencies["timer_scheduler"],
            model_storage=mock_dependencies["model_storage"],
            lhs_lifecycle_manager=mock_dependencies["lhs_lifecycle_manager"],
        )

        # Create manager for device 2
        manager2 = HeatingCycleLifecycleManagerFactory.create(
            hass=mock_hass,
            device_config=device_config_2,
            heating_cycle_service=mock_dependencies["heating_cycle_service"],
            cycle_cache=mock_dependencies["cycle_cache"],
            timer_scheduler=mock_dependencies["timer_scheduler"],
            model_storage=mock_dependencies["model_storage"],
            lhs_lifecycle_manager=mock_dependencies["lhs_lifecycle_manager"],
        )

        # THEN: Different instances
        assert manager1 is not manager2
        assert manager1._device_config.device_id != manager2._device_config.device_id

    def test_factory_registry_tracks_instances(
        self,
        mock_hass: Mock,
        device_config_1: DeviceConfig,
        mock_dependencies: dict,
    ) -> None:
        """Test factory registry maintains mapping of device_id to instance.

        GIVEN: Factory with clean registry
        WHEN: Create manager for device_id
        THEN: Instance is tracked in registry
        """
        # Create manager
        manager = HeatingCycleLifecycleManagerFactory.create(
            hass=mock_hass,
            device_config=device_config_1,
            heating_cycle_service=mock_dependencies["heating_cycle_service"],
            cycle_cache=mock_dependencies["cycle_cache"],
            timer_scheduler=mock_dependencies["timer_scheduler"],
            model_storage=mock_dependencies["model_storage"],
            lhs_lifecycle_manager=mock_dependencies["lhs_lifecycle_manager"],
        )

        # THEN: Instance is in registry
        assert device_config_1.device_id in HeatingCycleLifecycleManagerFactory._instances
        assert HeatingCycleLifecycleManagerFactory._instances[device_config_1.device_id] is manager

    def test_factory_reset_instances_clears_registry(
        self,
        mock_hass: Mock,
        device_config_1: DeviceConfig,
        mock_dependencies: dict,
    ) -> None:
        """Test reset_instances clears all tracked instances.

        GIVEN: Factory with instances in registry
        WHEN: reset_instances() called
        THEN: Registry cleared, ready for new tests
        """
        # Create some instances
        manager1 = HeatingCycleLifecycleManagerFactory.create(
            hass=mock_hass,
            device_config=device_config_1,
            heating_cycle_service=mock_dependencies["heating_cycle_service"],
            cycle_cache=mock_dependencies["cycle_cache"],
            timer_scheduler=mock_dependencies["timer_scheduler"],
            model_storage=mock_dependencies["model_storage"],
            lhs_lifecycle_manager=mock_dependencies["lhs_lifecycle_manager"],
        )

        # Registry should have instance
        assert len(HeatingCycleLifecycleManagerFactory._instances) >= 1

        # Reset
        HeatingCycleLifecycleManagerFactory._instances.clear()

        # THEN: Registry empty
        assert len(HeatingCycleLifecycleManagerFactory._instances) == 0

        # And creating new manager creates different instance
        manager2 = HeatingCycleLifecycleManagerFactory.create(
            hass=mock_hass,
            device_config=device_config_1,
            heating_cycle_service=mock_dependencies["heating_cycle_service"],
            cycle_cache=mock_dependencies["cycle_cache"],
            timer_scheduler=mock_dependencies["timer_scheduler"],
            model_storage=mock_dependencies["model_storage"],
            lhs_lifecycle_manager=mock_dependencies["lhs_lifecycle_manager"],
        )

        # New manager is different instance from before reset
        assert manager2 is not manager1

    def test_factory_injects_all_dependencies(
        self,
        mock_hass: Mock,
        device_config_1: DeviceConfig,
    ) -> None:
        """Test factory correctly injects all dependencies into manager.

        GIVEN: Mock dependencies
        WHEN: Create manager via factory
        THEN: All dependencies wired correctly
        """
        # Create mocks
        heating_cycle_service = Mock()
        cycle_cache = Mock()
        timer_scheduler = Mock()
        model_storage = Mock()
        lhs_lifecycle_manager = Mock()

        # Create manager
        manager = HeatingCycleLifecycleManagerFactory.create(
            hass=mock_hass,
            device_config=device_config_1,
            heating_cycle_service=heating_cycle_service,
            cycle_cache=cycle_cache,
            timer_scheduler=timer_scheduler,
            model_storage=model_storage,
            lhs_lifecycle_manager=lhs_lifecycle_manager,
        )

        # THEN: All dependencies injected
        assert manager._device_config is device_config_1
        assert manager._heating_cycle_service is heating_cycle_service
        assert manager._heating_cycle_storage is cycle_cache
        assert manager._timer_scheduler is timer_scheduler
        assert manager._lhs_storage is model_storage
        assert manager._lhs_lifecycle_manager is lhs_lifecycle_manager

    def test_factory_optional_dependencies(
        self,
        mock_hass: Mock,
        device_config_1: DeviceConfig,
        mock_dependencies: dict,
    ) -> None:
        """Test factory works with optional dependencies as None.

        GIVEN: No optional dependencies provided
        WHEN: Create manager via factory
        THEN: Manager created successfully with None for optional deps
        """
        # Create manager with minimal required dependencies
        manager = HeatingCycleLifecycleManagerFactory.create(
            hass=mock_hass,
            device_config=device_config_1,
            heating_cycle_service=mock_dependencies["heating_cycle_service"],
            # Optional deps left as defaults (None)
        )

        # THEN: Manager created with None for optional deps
        assert manager._heating_cycle_storage is None
        assert manager._timer_scheduler is None
        assert manager._lhs_storage is None
        assert manager._lhs_lifecycle_manager is None

    def test_factory_config_device_id_used_as_singleton_key(
        self,
        mock_hass: Mock,
        device_config_1: DeviceConfig,
        mock_dependencies: dict,
    ) -> None:
        """Test factory uses device_config.device_id as singleton key.

        GIVEN: Device config
        WHEN: Create manager
        THEN: Singleton key based on device_id
        """
        # Create manager
        manager = HeatingCycleLifecycleManagerFactory.create(
            hass=mock_hass,
            device_config=device_config_1,
            heating_cycle_service=mock_dependencies["heating_cycle_service"],
        )

        # THEN: Registry key is device_id
        assert device_config_1.device_id in HeatingCycleLifecycleManagerFactory._instances
        registry_entry = HeatingCycleLifecycleManagerFactory._instances[device_config_1.device_id]
        assert registry_entry is manager
