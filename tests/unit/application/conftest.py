"""Centralized pytest fixtures for application layer tests.

DRY Principle: All test fixtures reused across test modules are defined here.
Prevents code duplication and ensures consistency across test suites.

Fixtures are organized by domain:
- Mock infrastructure adapters (storage, cache, schedulers, etc.)
- Test data builders (heating cycles, configurations, etc.)
- Manager factories and instances
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.intelligent_heating_pilot.application.heating_cycle_lifecycle_manager import (
    HeatingCycleLifecycleManager,
)
from custom_components.intelligent_heating_pilot.application.lhs_lifecycle_manager import (
    LhsLifecycleManager,
)
from custom_components.intelligent_heating_pilot.domain.interfaces.device_config_reader_interface import (
    DeviceConfig,
)
from custom_components.intelligent_heating_pilot.domain.value_objects.heating import (
    HeatingCycle,
)

# ===== Base Test Data =====


@pytest.fixture
def base_datetime() -> datetime:
    """Provide consistent base datetime for all tests."""
    return datetime(2025, 2, 10, 12, 0, 0)


@pytest.fixture
def device_config() -> DeviceConfig:
    """Create default device configuration for testing."""
    return DeviceConfig(
        device_id="climate.test_vtherm",
        vtherm_entity_id="climate.test_vtherm",
        scheduler_entities=["schedule.heating"],
        lhs_retention_days=30,
    )


@pytest.fixture
def device_config_short_retention() -> DeviceConfig:
    """Create device config with reduced retention for edge case tests."""
    return DeviceConfig(
        device_id="climate.test_vtherm_short",
        vtherm_entity_id="climate.test_vtherm_short",
        scheduler_entities=["schedule.heating"],
        lhs_retention_days=7,
    )


# ===== Mock Infrastructure Adapters =====


@pytest.fixture
def mock_heating_cycle_service() -> Mock:
    """Create mock IHeatingCycleService.

    Provides extract_heating_cycles() that can return test cycles.
    """
    service = Mock()
    service.extract_heating_cycles = AsyncMock(return_value=[])
    return service


@pytest.fixture
def mock_historical_adapter() -> Mock:
    """Create mock IHistoricalDataAdapter.

    Provides fetch_historical_data() for fetching historical sensor data.
    """
    from custom_components.intelligent_heating_pilot.domain.value_objects.historical_data import (
        HistoricalDataKey,
        HistoricalDataSet,
    )

    adapter = Mock()
    # Return empty HistoricalDataSet with all keys initialized
    adapter.fetch_historical_data = AsyncMock(
        return_value=HistoricalDataSet(data={key: [] for key in HistoricalDataKey})
    )
    return adapter


@pytest.fixture
def mock_cycle_cache() -> Mock:
    """Create mock IHeatingCycleStorage (formerly IHeatingCycleStorage).

    Provides persistent cache operations:
    - get_cache_data()
    - append_cycles()
    - prune_old_cycles()
    - clear_cache()
    - get_last_search_time()
    """
    cache = Mock()
    cache.get_cache_data = AsyncMock(return_value=None)
    cache.append_cycles = AsyncMock()
    cache.prune_old_cycles = AsyncMock()
    cache.clear_cache = AsyncMock()
    cache.get_last_search_time = AsyncMock(return_value=None)
    return cache


@pytest.fixture
def mock_timer_scheduler() -> Mock:
    """Create mock ITimerScheduler.

    Provides schedule_timer() which returns a cancel function.
    """
    scheduler = Mock()
    cancel_func = Mock()
    scheduler.schedule_timer = Mock(return_value=cancel_func)
    return scheduler


@pytest.fixture
def mock_model_storage() -> Mock:
    """Create mock ILhsStorage (formerly ILhsStorage).

    Provides operations for storing and retrieving individual cycles,
    global LHS, and contextual LHS values.
    """
    storage = Mock()
    # Heating cycle operations
    storage.save_heating_cycle = AsyncMock()
    storage.get_heating_cycles = AsyncMock(return_value=[])
    storage.delete_heating_cycles_before = AsyncMock()
    # Global LHS operations
    storage.get_cached_global_lhs = AsyncMock(return_value=None)
    storage.set_cached_global_lhs = AsyncMock()
    # Contextual LHS operations (per hour)
    storage.get_cached_contextual_lhs = AsyncMock(return_value=None)
    storage.set_cached_contextual_lhs = AsyncMock()
    # Cache operations
    storage.set_heating_cycle = AsyncMock()
    storage.set_cache_global_lhs = AsyncMock()
    storage.set_cache_contextual_lhs = AsyncMock()
    return storage


@pytest.fixture
def mock_global_lhs_calculator() -> Mock:
    """Create mock GlobalLHSCalculatorService.

    Provides calculate() to compute global LHS from cycles.
    """
    calculator = Mock()
    calculator.calculate = Mock(return_value=2.5)
    calculator.calculate_global_lhs = Mock(return_value=2.5)
    return calculator


@pytest.fixture
def mock_contextual_lhs_calculator() -> Mock:
    """Create mock ContextualLHSCalculatorService.

    Provides calculate() to compute contextual LHS by hour from cycles.
    """
    calculator = Mock()
    calculator.calculate = Mock(return_value={0: 2.0, 6: 2.5, 12: 3.0})
    calculator.calculate_contextual_lhs = Mock(return_value={0: 2.0, 6: 2.5, 12: 3.0})
    return calculator


# ===== Test Data Builders =====


@pytest.fixture
def heating_cycle_builder(base_datetime: datetime):
    """Provide builder function for creating test heating cycles."""

    def _create_heating_cycle(
        start_time: datetime | None = None,
        duration_hours: float = 1.0,
        temp_increase: float = 2.0,
        device_id: str = "climate.test_vtherm",
    ) -> HeatingCycle:
        """Build a heating cycle with sensible defaults."""
        if start_time is None:
            start_time = base_datetime

        end_time = start_time + timedelta(hours=duration_hours)
        start_temp = 18.0
        end_temp = start_temp + temp_increase
        target_temp = end_temp + 0.5

        return HeatingCycle(
            device_id=device_id,
            start_time=start_time,
            end_time=end_time,
            target_temp=target_temp,
            end_temp=end_temp,
            start_temp=start_temp,
            tariff_details=None,
        )

    return _create_heating_cycle


@pytest.fixture
def sample_heating_cycles(
    base_datetime: datetime, heating_cycle_builder: Any
) -> list[HeatingCycle]:
    """Provide set of realistic test heating cycles spanning multiple days."""
    cycles = [
        heating_cycle_builder(
            base_datetime - timedelta(days=5), duration_hours=2, temp_increase=3.0
        ),
        heating_cycle_builder(
            base_datetime - timedelta(days=5, hours=2), duration_hours=1.5, temp_increase=2.5
        ),
        heating_cycle_builder(
            base_datetime - timedelta(days=3), duration_hours=2.5, temp_increase=3.5
        ),
        heating_cycle_builder(
            base_datetime - timedelta(days=1), duration_hours=1.0, temp_increase=2.0
        ),
        heating_cycle_builder(
            base_datetime - timedelta(hours=12), duration_hours=1.2, temp_increase=2.1
        ),
    ]
    return cycles


# ===== HeatingCycleLifecycleManager Fixtures =====


@pytest.fixture
def heating_cycle_manager_minimal(
    device_config: DeviceConfig,
    mock_heating_cycle_service: Mock,
    mock_historical_adapter: Mock,
) -> HeatingCycleLifecycleManager:
    """Create HeatingCycleLifecycleManager with minimal dependencies (no optional services)."""
    return HeatingCycleLifecycleManager(
        device_config=device_config,
        heating_cycle_service=mock_heating_cycle_service,
        historical_adapters=[mock_historical_adapter],
        heating_cycle_storage=None,
        timer_scheduler=None,
        lhs_storage=None,
        lhs_lifecycle_manager=None,
    )


@pytest.fixture
def heating_cycle_manager_with_cache(
    device_config: DeviceConfig,
    mock_heating_cycle_service: Mock,
    mock_historical_adapter: Mock,
    mock_cycle_cache: Mock,
) -> HeatingCycleLifecycleManager:
    """Create HeatingCycleLifecycleManager with cache (but no timer/storage)."""
    return HeatingCycleLifecycleManager(
        device_config=device_config,
        heating_cycle_service=mock_heating_cycle_service,
        historical_adapters=[mock_historical_adapter],
        heating_cycle_storage=mock_cycle_cache,
        timer_scheduler=None,
        lhs_storage=None,
        lhs_lifecycle_manager=None,
    )


@pytest.fixture
def heating_cycle_manager_full(
    device_config: DeviceConfig,
    mock_heating_cycle_service: Mock,
    mock_historical_adapter: Mock,
    mock_cycle_cache: Mock,
    mock_timer_scheduler: Mock,
    mock_model_storage: Mock,
) -> HeatingCycleLifecycleManager:
    """Create fully-configured HeatingCycleLifecycleManager with all dependencies."""
    return HeatingCycleLifecycleManager(
        device_config=device_config,
        heating_cycle_service=mock_heating_cycle_service,
        historical_adapters=[mock_historical_adapter],
        heating_cycle_storage=mock_cycle_cache,
        timer_scheduler=mock_timer_scheduler,
        lhs_storage=mock_model_storage,
        lhs_lifecycle_manager=None,
    )


@pytest.fixture
def heating_cycle_manager_with_lhs_cascade(
    device_config: DeviceConfig,
    mock_heating_cycle_service: Mock,
    mock_historical_adapter: Mock,
    mock_cycle_cache: Mock,
    mock_timer_scheduler: Mock,
    mock_model_storage: Mock,
) -> tuple[HeatingCycleLifecycleManager, Mock]:
    """Create HeatingCycleLifecycleManager with mocked LhsLifecycleManager for cascade testing."""
    mock_lhs_manager = AsyncMock(spec=LhsLifecycleManager)
    mock_lhs_manager.update_global_lhs_from_cycles = AsyncMock(return_value=2.5)
    mock_lhs_manager.update_contextual_lhs_from_cycles = AsyncMock(return_value={0: 2.0, 12: 3.0})

    manager = HeatingCycleLifecycleManager(
        device_config=device_config,
        heating_cycle_service=mock_heating_cycle_service,
        historical_adapters=[mock_historical_adapter],
        heating_cycle_storage=mock_cycle_cache,
        timer_scheduler=mock_timer_scheduler,
        lhs_storage=mock_model_storage,
        lhs_lifecycle_manager=mock_lhs_manager,
    )

    return manager, mock_lhs_manager


# ===== LhsLifecycleManager Fixtures =====


@pytest.fixture
def lhs_manager_minimal(
    mock_model_storage: Mock,
    mock_global_lhs_calculator: Mock,
    mock_contextual_lhs_calculator: Mock,
) -> LhsLifecycleManager:
    """Create LhsLifecycleManager without timer scheduler."""
    return LhsLifecycleManager(
        model_storage=mock_model_storage,
        global_lhs_calculator=mock_global_lhs_calculator,
        contextual_lhs_calculator=mock_contextual_lhs_calculator,
        timer_scheduler=None,
    )


@pytest.fixture
def lhs_manager_with_timer(
    mock_model_storage: Mock,
    mock_global_lhs_calculator: Mock,
    mock_contextual_lhs_calculator: Mock,
    mock_timer_scheduler: Mock,
) -> LhsLifecycleManager:
    """Create fully-configured LhsLifecycleManager with timer scheduler."""
    return LhsLifecycleManager(
        model_storage=mock_model_storage,
        global_lhs_calculator=mock_global_lhs_calculator,
        contextual_lhs_calculator=mock_contextual_lhs_calculator,
        timer_scheduler=mock_timer_scheduler,
    )


# ===== Factory Reset Utilities =====


@pytest.fixture(autouse=True)
def reset_lifecycle_manager_factories():
    """Auto-reset lifecycle manager factories before each test.

    Ensures each test starts with clean singleton registries.
    This fixture runs automatically (autouse=True) for all tests.
    """
    # Import factories inside fixture to avoid circular imports
    from custom_components.intelligent_heating_pilot.application.heating_cycle_lifecycle_manager_factory import (
        HeatingCycleLifecycleManagerFactory,
    )
    from custom_components.intelligent_heating_pilot.application.lhs_lifecycle_manager_factory import (
        LhsLifecycleManagerFactory,
    )

    # Reset registries before test
    HeatingCycleLifecycleManagerFactory._instances.clear()
    LhsLifecycleManagerFactory._instances.clear()

    yield

    # Reset registries after test
    HeatingCycleLifecycleManagerFactory._instances.clear()
    LhsLifecycleManagerFactory._instances.clear()
