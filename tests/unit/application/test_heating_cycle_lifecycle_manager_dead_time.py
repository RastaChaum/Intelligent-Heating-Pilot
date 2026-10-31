"""Extension tests for HeatingCycleLifecycleManager dead time learning.

Tests for new behavior:
- calculate_average_dead_time() from cycles with dead_time_cycle_minutes
- persist_learned_dead_time() to ILhsStorage.set_learned_dead_time()

These tests are RED phase tests (should FAIL with current code).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
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
        base_time = datetime(2025, 2, 10, 12, 0, 0, tzinfo=UTC)

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
            "climate.test_vtherm", base_time, datetime.now(UTC)
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
        base_time = datetime(2025, 2, 10, 12, 0, 0, tzinfo=UTC)

        cycles = [
            create_heating_cycle_with_dead_time(base_time, 5.0),
            create_heating_cycle_with_dead_time(base_time + timedelta(hours=1), 10.0),
        ]

        lifecycle_manager_dead_time._heating_cycle_service.extract_heating_cycles = AsyncMock(
            return_value=cycles
        )

        await lifecycle_manager_dead_time.update_cycles_for_window(
            "climate.test_vtherm", base_time, datetime.now(UTC)
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
        base_time = datetime(2025, 2, 10, 12, 0, 0, tzinfo=UTC)

        cycles = [
            create_heating_cycle_with_dead_time(base_time, None),
            create_heating_cycle_with_dead_time(base_time + timedelta(hours=1), 0.0),
        ]

        lifecycle_manager_dead_time._heating_cycle_service.extract_heating_cycles = AsyncMock(
            return_value=cycles
        )

        await lifecycle_manager_dead_time.update_cycles_for_window(
            "climate.test_vtherm", base_time, datetime.now(UTC)
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
        base_time = datetime(2025, 2, 10, 12, 0, 0, tzinfo=UTC)

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
            "climate.test_vtherm", base_time, datetime.now(UTC)
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
        base_time = datetime(2025, 2, 10, 12, 0, 0, tzinfo=UTC)

        cycles = [create_heating_cycle_with_dead_time(base_time, 6.5)]

        lifecycle_manager_dead_time._heating_cycle_service.extract_heating_cycles = AsyncMock(
            return_value=cycles
        )

        await lifecycle_manager_dead_time.update_cycles_for_window(
            "climate.test_vtherm", base_time, datetime.now(UTC)
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

        base_time = datetime(2025, 2, 10, 12, 0, 0, tzinfo=UTC)
        cycles = [create_heating_cycle_with_dead_time(base_time, 8.0)]

        manager._heating_cycle_service.extract_heating_cycles = AsyncMock(return_value=cycles)

        await manager.update_cycles_for_window("climate.test_vtherm", base_time, datetime.now(UTC))

        # set_learned_dead_time should NOT be called
        mock_lhs_storage_dead_time.set_learned_dead_time.assert_not_called()


STORED_DEAD_TIME = 7.5
CYCLES_AVERAGE_DEAD_TIME = 9.0


@pytest.fixture
def cycles_averaging_nine_minutes() -> list[HeatingCycle]:
    """Two cycles whose average dead time is 9.0 minutes."""
    base_time = datetime(2025, 2, 10, 12, 0, 0, tzinfo=UTC)
    return [
        create_heating_cycle_with_dead_time(base_time, 8.0),
        create_heating_cycle_with_dead_time(base_time + timedelta(hours=2), 10.0),
    ]


@pytest.fixture
def dead_time_callback() -> Mock:
    """Stand-in for the dead time update announcement."""
    return Mock()


@pytest.fixture
def unpruned_cycle_cache(cycles_averaging_nine_minutes: list[HeatingCycle]) -> Mock:
    """Cycle cache holding the cycles, with nothing to prune and nothing to extract."""
    from custom_components.intelligent_heating_pilot.domain.value_objects.heating_cycle_cache_data import (
        HeatingCycleCacheData,
    )

    today = datetime.now(UTC).date()
    cache = Mock()
    cache.prune_old_cycles = AsyncMock(return_value=False)
    cache.get_cache_data = AsyncMock(
        return_value=HeatingCycleCacheData(
            device_id="climate.test_vtherm",
            cycles=tuple(cycles_averaging_nine_minutes),
            last_search_time=datetime.now(UTC),
            retention_days=30,
            explored_dates=frozenset(today - timedelta(days=offset) for offset in range(-2, 40)),
        )
    )
    return cache


def _manager_with_cache(
    device_config: DeviceConfig,
    cycle_cache: Mock | None,
    lhs_storage: Mock,
    dead_time_callback: Mock,
) -> HeatingCycleLifecycleManager:
    return HeatingCycleLifecycleManager(
        device_config=device_config,
        heating_cycle_service=Mock(),
        historical_adapters=[Mock()],
        heating_cycle_storage=cycle_cache,
        timer_scheduler=None,
        lhs_storage=lhs_storage,
        lhs_lifecycle_manager=None,
        dead_time_updated_callback=dead_time_callback,
    )


class TestPersistLearnedDeadTimeSkipsUnchangedValue:
    """A learned dead time equal to the stored one is not rewritten (#224).

    Rewriting it logged "Learned dead time updated" and announced an update
    although nothing had been recalculated.
    """

    @pytest.mark.asyncio
    async def test_unchanged_value_not_rewritten_nor_announced(
        self,
        device_config_for_dead_time: DeviceConfig,
        mock_lhs_storage_dead_time: Mock,
        dead_time_callback: Mock,
        cycles_averaging_nine_minutes: list[HeatingCycle],
    ) -> None:
        """The stored value already is the cycles' average."""
        mock_lhs_storage_dead_time.get_learned_dead_time.return_value = CYCLES_AVERAGE_DEAD_TIME
        manager = _manager_with_cache(
            device_config_for_dead_time, None, mock_lhs_storage_dead_time, dead_time_callback
        )

        await manager._persist_learned_dead_time(cycles_averaging_nine_minutes)

        mock_lhs_storage_dead_time.set_learned_dead_time.assert_not_awaited()
        dead_time_callback.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("stored", [None, STORED_DEAD_TIME])
    async def test_new_value_stored_and_announced(
        self,
        device_config_for_dead_time: DeviceConfig,
        mock_lhs_storage_dead_time: Mock,
        dead_time_callback: Mock,
        cycles_averaging_nine_minutes: list[HeatingCycle],
        stored: float | None,
    ) -> None:
        """Nothing stored yet, or a different value: the average is stored."""
        mock_lhs_storage_dead_time.get_learned_dead_time.return_value = stored
        manager = _manager_with_cache(
            device_config_for_dead_time, None, mock_lhs_storage_dead_time, dead_time_callback
        )

        await manager._persist_learned_dead_time(cycles_averaging_nine_minutes)

        mock_lhs_storage_dead_time.set_learned_dead_time.assert_awaited_once_with(
            pytest.approx(CYCLES_AVERAGE_DEAD_TIME)
        )
        dead_time_callback.assert_called_once_with(pytest.approx(CYCLES_AVERAGE_DEAD_TIME))


class TestRefreshLearnsDeadTimeWithoutPruning:
    """The cache refresh learns the dead time from cached cycles even when none is pruned.

    The anticipation update no longer stores the dead time (#224): without this,
    cycles extracted while auto-learning was off were only learned from once new
    cycles were extracted, up to a day after auto-learning was turned back on.
    """

    @pytest.mark.asyncio
    async def test_cached_cycles_learned_when_nothing_stored(
        self,
        device_config_for_dead_time: DeviceConfig,
        mock_lhs_storage_dead_time: Mock,
        dead_time_callback: Mock,
        unpruned_cycle_cache: Mock,
    ) -> None:
        """Auto-learning just turned on: the cached cycles' average is stored."""
        manager = _manager_with_cache(
            device_config_for_dead_time,
            unpruned_cycle_cache,
            mock_lhs_storage_dead_time,
            dead_time_callback,
        )

        await manager.refresh_heating_cycle_cache()

        mock_lhs_storage_dead_time.set_learned_dead_time.assert_awaited_once_with(
            pytest.approx(CYCLES_AVERAGE_DEAD_TIME)
        )
        dead_time_callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_nothing_learned_when_auto_learning_disabled(
        self,
        device_config_dead_time_disabled: DeviceConfig,
        mock_lhs_storage_dead_time: Mock,
        dead_time_callback: Mock,
        unpruned_cycle_cache: Mock,
    ) -> None:
        """The configured dead time stays in use; nothing is stored as learned."""
        manager = _manager_with_cache(
            device_config_dead_time_disabled,
            unpruned_cycle_cache,
            mock_lhs_storage_dead_time,
            dead_time_callback,
        )

        await manager.refresh_heating_cycle_cache()

        mock_lhs_storage_dead_time.set_learned_dead_time.assert_not_awaited()
        dead_time_callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_nothing_learned_when_cache_unreadable(
        self,
        device_config_for_dead_time: DeviceConfig,
        mock_lhs_storage_dead_time: Mock,
        dead_time_callback: Mock,
        unpruned_cycle_cache: Mock,
    ) -> None:
        """A storage error leaves the stored dead time as it was."""
        # Only the read for the dead time fails; the missing-range lookup after it succeeds.
        unpruned_cycle_cache.get_cache_data.side_effect = [
            OSError("storage unavailable"),
            unpruned_cycle_cache.get_cache_data.return_value,
        ]
        manager = _manager_with_cache(
            device_config_for_dead_time,
            unpruned_cycle_cache,
            mock_lhs_storage_dead_time,
            dead_time_callback,
        )

        await manager.refresh_heating_cycle_cache()

        mock_lhs_storage_dead_time.set_learned_dead_time.assert_not_awaited()
        dead_time_callback.assert_not_called()
