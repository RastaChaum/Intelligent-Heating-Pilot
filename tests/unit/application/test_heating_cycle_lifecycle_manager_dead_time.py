"""Extension tests for HeatingCycleLifecycleManager dead time learning.

Tests for new behavior:
- calculate_average_dead_time() from cycles with dead_time_cycle_minutes
- persist_learned_dead_time() to ILhsStorage.set_learned_dead_time()

These tests are RED phase tests (should FAIL with current code).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.intelligent_heating_pilot.application.heating_cycle_lifecycle_manager import (
    HeatingCycleLifecycleManager,
)
from custom_components.intelligent_heating_pilot.domain.interfaces.device_config_reader_interface import (
    DeviceConfig,
)
from custom_components.intelligent_heating_pilot.domain.value_objects.heating import (
    HeatingCycle,
)


@pytest.fixture
def device_config_for_dead_time() -> DeviceConfig:
    """Create device config with auto_learning enabled."""
    return DeviceConfig(
        device_id="climate.test_vtherm",
        vtherm_entity_id="climate.test_vtherm",
        scheduler_entities=["schedule.heating"],
        lhs_retention_days=30,
        auto_learning=True,
        dead_time_minutes=5.0,
    )


@pytest.fixture
def device_config_dead_time_disabled() -> DeviceConfig:
    """Create device config with auto_learning disabled."""
    return DeviceConfig(
        device_id="climate.test_vtherm",
        vtherm_entity_id="climate.test_vtherm",
        scheduler_entities=["schedule.heating"],
        lhs_retention_days=30,
        auto_learning=False,
        dead_time_minutes=5.0,
    )


def create_heating_cycle_with_dead_time(
    start_time: datetime,
    dead_time_cycle_minutes: float | None,
    device_id: str = "climate.test_vtherm",
) -> HeatingCycle:
    """Create a heating cycle with specific dead_time_cycle_minutes."""
    end_time = start_time + timedelta(hours=1)
    return HeatingCycle(
        device_id=device_id,
        start_time=start_time,
        end_time=end_time,
        target_temp=21.0,
        end_temp=20.0,
        start_temp=18.0,
        tariff_details=None,
        dead_time_cycle_minutes=dead_time_cycle_minutes,
    )


@pytest.fixture
def mock_heating_cycle_service_dead_time() -> Mock:
    """Create mock IHeatingCycleService for dead_time tests."""
    service = Mock()
    service.extract_heating_cycles = AsyncMock(return_value=[])
    return service


@pytest.fixture
def mock_lhs_storage_dead_time() -> Mock:
    """Create mock ILhsStorage with dead_time methods."""
    storage = Mock()
    storage.get_learned_dead_time = AsyncMock(return_value=None)
    storage.set_learned_dead_time = AsyncMock()
    storage.get_learned_heating_slope = AsyncMock(return_value=2.5)
    storage.get_heating_cycles = AsyncMock(return_value=[])
    return storage


@pytest.fixture
def mock_historical_adapter_dead_time() -> Mock:
    """Create mock IHistoricalDataAdapter for dead_time tests."""
    from custom_components.intelligent_heating_pilot.domain.value_objects.historical_data import (
        HistoricalDataKey,
        HistoricalDataSet,
    )

    adapter = Mock()
    adapter.fetch_historical_data = AsyncMock(
        return_value=HistoricalDataSet(data={key: [] for key in HistoricalDataKey})
    )
    return adapter


@pytest.fixture
def lifecycle_manager_dead_time(
    device_config_for_dead_time: DeviceConfig,
    mock_heating_cycle_service_dead_time: Mock,
    mock_historical_adapter_dead_time: Mock,
    mock_lhs_storage_dead_time: Mock,
) -> HeatingCycleLifecycleManager:
    """Create HeatingCycleLifecycleManager configured for dead_time testing."""
    return HeatingCycleLifecycleManager(
        device_config=device_config_for_dead_time,
        heating_cycle_service=mock_heating_cycle_service_dead_time,
        historical_adapters=[mock_historical_adapter_dead_time],
        heating_cycle_storage=None,
        timer_scheduler=None,
        lhs_storage=mock_lhs_storage_dead_time,
        lhs_lifecycle_manager=None,
    )


class TestHeatingCycleLifecycleManagerDeadTimeCalculation:
    """Test suite for dead time calculation in HeatingCycleLifecycleManager.

    RED: These tests FAIL because dead_time calculation isn't integrated yet.
    """

    @pytest.mark.asyncio
    async def test_calculate_dead_time_from_cycles(
        self, lifecycle_manager_dead_time: HeatingCycleLifecycleManager
    ) -> None:
        """Test that dead_time is calculated from cycles with dead_time_cycle_minutes.

        RED: FAILS because update_cycles_for_window() doesn't call dead_time calculation yet.
        """
        base_time = datetime(2025, 2, 10, 12, 0, 0, tzinfo=timezone.utc)

        # Create cycles with dead_time values
        cycles_with_dead_time = [
            create_heating_cycle_with_dead_time(base_time, 8.0),
            create_heating_cycle_with_dead_time(base_time + timedelta(hours=1), 7.5),
            create_heating_cycle_with_dead_time(base_time + timedelta(hours=2), 9.0),
        ]

        lifecycle_manager_dead_time._heating_cycle_service.extract_heating_cycles = AsyncMock(
            return_value=cycles_with_dead_time
        )

        # Call update_cycles_for_window which should trigger dead_time calculation
        await lifecycle_manager_dead_time.update_cycles_for_window(
            base_time, datetime.now(timezone.utc)
        )

        # Verify that set_learned_dead_time was called with the average
        # Expected average: (8.0 + 7.5 + 9.0) / 3 = 8.166...
        lifecycle_manager_dead_time._lhs_storage.set_learned_dead_time.assert_called()

    @pytest.mark.asyncio
    async def test_calculate_dead_time_average_correctly(
        self,
        lifecycle_manager_dead_time: HeatingCycleLifecycleManager,
        mock_lhs_storage_dead_time: Mock,
    ) -> None:
        """Test that average dead_time is calculated correctly.

        RED: FAILS because calculation logic isn't implemented.
        """
        base_time = datetime(2025, 2, 10, 12, 0, 0, tzinfo=timezone.utc)

        cycles = [
            create_heating_cycle_with_dead_time(base_time, 5.0),
            create_heating_cycle_with_dead_time(base_time + timedelta(hours=1), 10.0),
        ]

        lifecycle_manager_dead_time._heating_cycle_service.extract_heating_cycles = AsyncMock(
            return_value=cycles
        )

        await lifecycle_manager_dead_time.update_cycles_for_window(
            base_time, datetime.now(timezone.utc)
        )

        # Should persist average: (5.0 + 10.0) / 2 = 7.5
        mock_lhs_storage_dead_time.set_learned_dead_time.assert_called_with(pytest.approx(7.5))

    @pytest.mark.asyncio
    async def test_no_dead_time_learning_when_no_valid_cycles(
        self,
        lifecycle_manager_dead_time: HeatingCycleLifecycleManager,
        mock_lhs_storage_dead_time: Mock,
    ) -> None:
        """Test that no learning happens when cycles have no valid dead_time_cycle_minutes.

        RED: FAILS - behavior depends on implementation choice.
        """
        base_time = datetime(2025, 2, 10, 12, 0, 0, tzinfo=timezone.utc)

        cycles = [
            create_heating_cycle_with_dead_time(base_time, None),
            create_heating_cycle_with_dead_time(base_time + timedelta(hours=1), 0.0),
        ]

        lifecycle_manager_dead_time._heating_cycle_service.extract_heating_cycles = AsyncMock(
            return_value=cycles
        )

        await lifecycle_manager_dead_time.update_cycles_for_window(
            base_time, datetime.now(timezone.utc)
        )

        # set_learned_dead_time should not be called with an average
        # (or called with None if that's the pattern)
        calls = mock_lhs_storage_dead_time.set_learned_dead_time.call_args_list
        if calls:
            # If called, should be with None
            last_call_arg = calls[-1][0][0]
            assert last_call_arg is None

    @pytest.mark.asyncio
    async def test_ignore_zero_and_negative_dead_times_in_calculation(
        self,
        lifecycle_manager_dead_time: HeatingCycleLifecycleManager,
        mock_lhs_storage_dead_time: Mock,
    ) -> None:
        """Test that zero and negative dead_time values are ignored.

        Only cycles with dead_time_cycle_minutes > 0 should be averaged.

        RED: FAILS if filtering logic isn't implemented.
        """
        base_time = datetime(2025, 2, 10, 12, 0, 0, tzinfo=timezone.utc)

        cycles = [
            create_heating_cycle_with_dead_time(base_time, 8.0),
            create_heating_cycle_with_dead_time(base_time + timedelta(hours=1), 0.0),
            create_heating_cycle_with_dead_time(base_time + timedelta(hours=2), 12.0),
            create_heating_cycle_with_dead_time(base_time + timedelta(hours=3), -5.0),
        ]

        lifecycle_manager_dead_time._heating_cycle_service.extract_heating_cycles = AsyncMock(
            return_value=cycles
        )

        await lifecycle_manager_dead_time.update_cycles_for_window(
            base_time, datetime.now(timezone.utc)
        )

        # Should average only 8.0 and 12.0: (8.0 + 12.0) / 2 = 10.0
        mock_lhs_storage_dead_time.set_learned_dead_time.assert_called_with(pytest.approx(10.0))

    @pytest.mark.asyncio
    async def test_single_cycle_dead_time(
        self,
        lifecycle_manager_dead_time: HeatingCycleLifecycleManager,
        mock_lhs_storage_dead_time: Mock,
    ) -> None:
        """Test dead_time calculation with single cycle."""
        base_time = datetime(2025, 2, 10, 12, 0, 0, tzinfo=timezone.utc)

        cycles = [create_heating_cycle_with_dead_time(base_time, 6.5)]

        lifecycle_manager_dead_time._heating_cycle_service.extract_heating_cycles = AsyncMock(
            return_value=cycles
        )

        await lifecycle_manager_dead_time.update_cycles_for_window(
            base_time, datetime.now(timezone.utc)
        )

        # Should persist the single value
        mock_lhs_storage_dead_time.set_learned_dead_time.assert_called_with(pytest.approx(6.5))

    @pytest.mark.asyncio
    async def test_no_dead_time_persistence_when_auto_learning_disabled(
        self,
        device_config_dead_time_disabled: DeviceConfig,
        mock_historical_adapter_dead_time: Mock,
        mock_heating_cycle_service_dead_time: Mock,
        mock_lhs_storage_dead_time: Mock,
    ) -> None:
        """Test that dead_time is not learned when auto_learning is disabled.

        RED: FAILS if auto_learning flag isn't checked before persistence.
        """
        manager = HeatingCycleLifecycleManager(
            device_config=device_config_dead_time_disabled,
            heating_cycle_service=mock_heating_cycle_service_dead_time,
            historical_adapters=[mock_historical_adapter_dead_time],
            heating_cycle_storage=None,
            timer_scheduler=None,
            lhs_storage=mock_lhs_storage_dead_time,
            lhs_lifecycle_manager=None,
        )

        base_time = datetime(2025, 2, 10, 12, 0, 0, tzinfo=timezone.utc)
        cycles = [create_heating_cycle_with_dead_time(base_time, 8.0)]

        manager._heating_cycle_service.extract_heating_cycles = AsyncMock(return_value=cycles)

        await manager.update_cycles_for_window(base_time, datetime.now(timezone.utc))

        # set_learned_dead_time should NOT be called
        mock_lhs_storage_dead_time.set_learned_dead_time.assert_not_called()
