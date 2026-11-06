"""Tests for HeatingCycleLifecycleManager dead time learning.

The learned dead time is stored by _persist_learned_dead_time() only, from every
cached cycle, after an extraction, a pruning or a cache refresh. How the average is
computed is tested on DeadTimeCalculationService (domain).
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
def mock_lhs_storage_dead_time() -> Mock:
    """Create mock ILhsStorage with dead_time methods."""
    storage = Mock()
    storage.get_learned_dead_time = AsyncMock(return_value=None)
    storage.set_learned_dead_time = AsyncMock()
    storage.get_learned_heating_slope = AsyncMock(return_value=2.5)
    storage.get_heating_cycles = AsyncMock(return_value=[])
    return storage


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


class TestPersistLearnedDeadTimeGuards:
    """Nothing is stored as learned without a measured dead time or with auto-learning off.

    Every live trigger (extraction, pruning, cache refresh) stores the dead time through
    _persist_learned_dead_time, so its guards are tested there (#218).
    """

    @pytest.mark.asyncio
    async def test_nothing_stored_when_no_cycle_has_a_dead_time(
        self,
        device_config_for_dead_time: DeviceConfig,
        mock_lhs_storage_dead_time: Mock,
        dead_time_callback: Mock,
    ) -> None:
        """Cycles without a dead time, or with a zero one, teach nothing."""
        base_time = datetime(2025, 2, 10, 12, 0, 0, tzinfo=UTC)
        cycles = [
            create_heating_cycle_with_dead_time(base_time, None),
            create_heating_cycle_with_dead_time(base_time + timedelta(hours=2), 0.0),
        ]
        manager = _manager_with_cache(
            device_config_for_dead_time, None, mock_lhs_storage_dead_time, dead_time_callback
        )

        await manager._persist_learned_dead_time(cycles)

        mock_lhs_storage_dead_time.set_learned_dead_time.assert_not_awaited()
        dead_time_callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_nothing_stored_when_auto_learning_disabled(
        self,
        device_config_dead_time_disabled: DeviceConfig,
        mock_lhs_storage_dead_time: Mock,
        dead_time_callback: Mock,
        cycles_averaging_nine_minutes: list[HeatingCycle],
    ) -> None:
        """The configured dead time stays in use, even with measured dead times."""
        manager = _manager_with_cache(
            device_config_dead_time_disabled, None, mock_lhs_storage_dead_time, dead_time_callback
        )

        await manager._persist_learned_dead_time(cycles_averaging_nine_minutes)

        mock_lhs_storage_dead_time.set_learned_dead_time.assert_not_awaited()
        dead_time_callback.assert_not_called()


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
