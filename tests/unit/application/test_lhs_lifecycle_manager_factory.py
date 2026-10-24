"""Unit tests for LhsLifecycleManagerFactory singleton pattern.

RED tests: These tests should validate the singleton behavior and factory
creation logic for the LhsLifecycleManager.

Author: QA Engineer
Purpose: Ensure factory correctly implements singleton pattern per model_storage
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from custom_components.intelligent_heating_pilot.application.lhs_lifecycle_manager_factory import (
    LhsLifecycleManagerFactory,
)


class TestLhsLifecycleManagerFactory:
    """Test suite for LHS factory singleton pattern."""

    @pytest.fixture
    def mock_model_storage_1(self) -> Mock:
        """First mock model storage instance."""
        return Mock()

    @pytest.fixture
    def mock_model_storage_2(self) -> Mock:
        """Second mock model storage instance (different object)."""
        return Mock()

    @pytest.fixture
    def mock_global_lhs_calculator(self) -> Mock:
        """Mock GlobalLHSCalculatorService."""
        return Mock()

    @pytest.fixture
    def mock_contextual_lhs_calculator(self) -> Mock:
        """Mock ContextualLHSCalculatorService."""
        return Mock()

    @pytest.fixture
    def mock_timer_scheduler(self) -> Mock:
        """Mock ITimerScheduler."""
        scheduler = Mock()
        scheduler.schedule_timer = Mock(return_value=Mock())
        return scheduler

    def test_factory_singleton_same_storage_returns_same_instance(
        self,
        mock_model_storage_1: Mock,
        mock_global_lhs_calculator: Mock,
        mock_contextual_lhs_calculator: Mock,
    ) -> None:
        """Test factory returns same instance for same model_storage.

        GIVEN: Factory with clean registry
        WHEN: Create manager for storage twice
        THEN: Same instance returned both times (singleton behavior)
        """
        # Create first manager
        manager1 = LhsLifecycleManagerFactory.create(
            model_storage=mock_model_storage_1,
            global_lhs_calculator=mock_global_lhs_calculator,
            contextual_lhs_calculator=mock_contextual_lhs_calculator,
        )

        # Create same manager again (same storage)
        manager2 = LhsLifecycleManagerFactory.create(
            model_storage=mock_model_storage_1,
            global_lhs_calculator=mock_global_lhs_calculator,
            contextual_lhs_calculator=mock_contextual_lhs_calculator,
        )

        # THEN: Same instance
        assert manager1 is manager2

    def test_factory_different_storages_different_instances(
        self,
        mock_model_storage_1: Mock,
        mock_model_storage_2: Mock,
        mock_global_lhs_calculator: Mock,
        mock_contextual_lhs_calculator: Mock,
    ) -> None:
        """Test factory creates different instances for different storages.

        GIVEN: Factory with clean registry
        WHEN: Create managers with two different storage instances
        THEN: Different manager instances created for each storage
        """
        # Create manager for storage 1
        manager1 = LhsLifecycleManagerFactory.create(
            model_storage=mock_model_storage_1,
            global_lhs_calculator=mock_global_lhs_calculator,
            contextual_lhs_calculator=mock_contextual_lhs_calculator,
        )

        # Create manager for storage 2
        manager2 = LhsLifecycleManagerFactory.create(
            model_storage=mock_model_storage_2,
            global_lhs_calculator=mock_global_lhs_calculator,
            contextual_lhs_calculator=mock_contextual_lhs_calculator,
        )

        # THEN: Different instances
        assert manager1 is not manager2
        assert manager1._model_storage is not manager2._model_storage

    def test_factory_registry_tracks_instances_by_storage_id(
        self,
        mock_model_storage_1: Mock,
        mock_global_lhs_calculator: Mock,
        mock_contextual_lhs_calculator: Mock,
    ) -> None:
        """Test factory registry uses id(model_storage) as key.

        GIVEN: Mock storage instance
        WHEN: Create manager via factory
        THEN: Instance tracked in registry with id(storage) as key
        """
        # Create manager
        manager = LhsLifecycleManagerFactory.create(
            model_storage=mock_model_storage_1,
            global_lhs_calculator=mock_global_lhs_calculator,
            contextual_lhs_calculator=mock_contextual_lhs_calculator,
        )

        # THEN: Instance tracked by storage id
        storage_id = id(mock_model_storage_1)
        assert storage_id in LhsLifecycleManagerFactory._instances
        assert LhsLifecycleManagerFactory._instances[storage_id] is manager

    def test_factory_reset_instances_clears_registry(
        self,
        mock_model_storage_1: Mock,
        mock_global_lhs_calculator: Mock,
        mock_contextual_lhs_calculator: Mock,
    ) -> None:
        """Test reset_instances clears all tracked instances.

        GIVEN: Factory with instances in registry
        WHEN: _instances.clear() called
        THEN: Registry cleared
        """
        # Create instance
        manager1 = LhsLifecycleManagerFactory.create(
            model_storage=mock_model_storage_1,
            global_lhs_calculator=mock_global_lhs_calculator,
            contextual_lhs_calculator=mock_contextual_lhs_calculator,
        )

        # Registry should have instance
        assert len(LhsLifecycleManagerFactory._instances) >= 1

        # Reset
        LhsLifecycleManagerFactory._instances.clear()

        # THEN: Registry empty
        assert len(LhsLifecycleManagerFactory._instances) == 0

        # Create new manager after reset
        manager2 = LhsLifecycleManagerFactory.create(
            model_storage=mock_model_storage_1,
            global_lhs_calculator=mock_global_lhs_calculator,
            contextual_lhs_calculator=mock_contextual_lhs_calculator,
        )

        # THEN: Different instance than before reset
        assert manager2 is not manager1

    def test_factory_injects_all_dependencies(
        self,
        mock_model_storage_1: Mock,
        mock_global_lhs_calculator: Mock,
        mock_contextual_lhs_calculator: Mock,
        mock_timer_scheduler: Mock,
    ) -> None:
        """Test factory correctly injects all dependencies into manager.

        GIVEN: Mock dependencies
        WHEN: Create manager via factory
        THEN: All dependencies wired correctly
        """
        # Create manager with all dependencies
        manager = LhsLifecycleManagerFactory.create(
            model_storage=mock_model_storage_1,
            global_lhs_calculator=mock_global_lhs_calculator,
            contextual_lhs_calculator=mock_contextual_lhs_calculator,
            timer_scheduler=mock_timer_scheduler,
        )

        # THEN: All dependencies injected
        assert manager._model_storage is mock_model_storage_1
        assert manager._global_lhs_calculator is mock_global_lhs_calculator
        assert manager._contextual_lhs_calculator is mock_contextual_lhs_calculator
        assert manager._timer_scheduler is mock_timer_scheduler

    def test_factory_timer_scheduler_optional(
        self,
        mock_model_storage_1: Mock,
        mock_global_lhs_calculator: Mock,
        mock_contextual_lhs_calculator: Mock,
    ) -> None:
        """Test factory works without timer scheduler.

        GIVEN: No timer_scheduler provided
        WHEN: Create manager via factory
        THEN: Manager created successfully with None for timer
        """
        # Create manager without timer
        manager = LhsLifecycleManagerFactory.create(
            model_storage=mock_model_storage_1,
            global_lhs_calculator=mock_global_lhs_calculator,
            contextual_lhs_calculator=mock_contextual_lhs_calculator,
            # timer_scheduler defaults to None
        )

        # THEN: Manager created with None for timer
        assert manager._timer_scheduler is None

    def test_factory_multiple_devices_isolated_instances(
        self,
        mock_model_storage_1: Mock,
        mock_model_storage_2: Mock,
        mock_global_lhs_calculator: Mock,
        mock_contextual_lhs_calculator: Mock,
    ) -> None:
        """Test factory ensures isolation between different storages/devices.

        GIVEN: Two storage instances (representing different devices)
        WHEN: Create managers for each storage
        THEN: Managers are independent with separate registries
        """
        # Create managers for different storages
        manager1 = LhsLifecycleManagerFactory.create(
            model_storage=mock_model_storage_1,
            global_lhs_calculator=mock_global_lhs_calculator,
            contextual_lhs_calculator=mock_contextual_lhs_calculator,
        )

        manager2 = LhsLifecycleManagerFactory.create(
            model_storage=mock_model_storage_2,
            global_lhs_calculator=mock_global_lhs_calculator,
            contextual_lhs_calculator=mock_contextual_lhs_calculator,
        )

        # THEN: Different managers
        assert manager1 is not manager2

        # And each has correct storage
        assert manager1._model_storage is mock_model_storage_1
        assert manager2._model_storage is mock_model_storage_2

        # And both are in registry
        storage_id_1 = id(mock_model_storage_1)
        storage_id_2 = id(mock_model_storage_2)
        assert LhsLifecycleManagerFactory._instances[storage_id_1] is manager1
        assert LhsLifecycleManagerFactory._instances[storage_id_2] is manager2

    def test_factory_storage_id_as_singleton_key(
        self,
        mock_model_storage_1: Mock,
        mock_global_lhs_calculator: Mock,
        mock_contextual_lhs_calculator: Mock,
    ) -> None:
        """Test factory uses id(model_storage) as singleton key.

        GIVEN: Mock storage instance
        WHEN: Create manager
        THEN: Instance retrievable via storage id
        """
        # Create manager
        manager = LhsLifecycleManagerFactory.create(
            model_storage=mock_model_storage_1,
            global_lhs_calculator=mock_global_lhs_calculator,
            contextual_lhs_calculator=mock_contextual_lhs_calculator,
        )

        # THEN: Can retrieve via storage id
        storage_id = id(mock_model_storage_1)
        retrieved_manager = LhsLifecycleManagerFactory._instances.get(storage_id)
        assert retrieved_manager is manager

    def test_factory_dependency_variance_creates_new_instance(
        self,
        mock_model_storage_1: Mock,
        mock_global_lhs_calculator: Mock,
        mock_contextual_lhs_calculator: Mock,
        mock_timer_scheduler: Mock,
    ) -> None:
        """Test factory returns same instance even if calculator dependencies differ.

        GIVEN: Same storage, but different calculator objects
        WHEN: Create managers with varied dependencies
        THEN: Singleton based on storage only (not dependencies)

        Note: This tests the current behavior where singleton key is storage id.
        If dependencies change, they won't affect singleton retrieval.
        """
        # Create with one set of dependencies
        manager1 = LhsLifecycleManagerFactory.create(
            model_storage=mock_model_storage_1,
            global_lhs_calculator=mock_global_lhs_calculator,
            contextual_lhs_calculator=mock_contextual_lhs_calculator,
        )

        # Create different calculator mocks
        different_global_calc = Mock()
        different_contextual_calc = Mock()

        # Create with different dependencies but same storage
        manager2 = LhsLifecycleManagerFactory.create(
            model_storage=mock_model_storage_1,
            global_lhs_calculator=different_global_calc,
            contextual_lhs_calculator=different_contextual_calc,
        )

        # THEN: Same instance returned (singleton by storage)
        assert manager1 is manager2
        # So manager1's dependencies are kept, not overwritten
        assert manager1._global_lhs_calculator is mock_global_lhs_calculator
        assert manager1._global_lhs_calculator is not different_global_calc
