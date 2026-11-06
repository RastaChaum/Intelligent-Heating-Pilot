"""Tests for the daily retry of periods whose history read failed (#187).

A period whose history could not be read stays unexplored. The startup window only
covers the most recent days and the backfill only steps back from the oldest explored
day, so a gap between the two must be retried by the daily refresh.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.intelligent_heating_pilot.application.heating_cycle_lifecycle_manager import (
    HeatingCycleLifecycleManager,
)
from custom_components.intelligent_heating_pilot.domain.interfaces.device_config_reader_interface import (
    DeviceConfig,
)
from custom_components.intelligent_heating_pilot.domain.value_objects.heating_cycle_cache_data import (
    HeatingCycleCacheData,
)

DEVICE_ID = "climate.test_vtherm"
RETENTION_DAYS = 30
TASK_RANGE_DAYS = 7


def _days(start: date, end: date) -> set[date]:
    """Return every day from start to end, inclusive."""
    return {start + timedelta(days=offset) for offset in range((end - start).days + 1)}


@pytest.fixture
def storage() -> Mock:
    """Cycle storage whose explored days are set by each test."""
    cache = Mock()
    cache.get_cache_data = AsyncMock(return_value=None)
    cache.get_oldest_explored_date = AsyncMock(return_value=None)
    return cache


@pytest.fixture
def manager(storage: Mock) -> HeatingCycleLifecycleManager:
    """Cycle manager with a 30-day retention and 7-day extraction periods."""
    return HeatingCycleLifecycleManager(
        device_config=DeviceConfig(
            device_id=DEVICE_ID,
            vtherm_entity_id=DEVICE_ID,
            scheduler_entities=["schedule.heating"],
            lhs_retention_days=RETENTION_DAYS,
            task_range_days=TASK_RANGE_DAYS,
        ),
        heating_cycle_service=Mock(extract_heating_cycles=AsyncMock(return_value=[])),
        historical_adapters=[],
        heating_cycle_storage=storage,
        timer_scheduler=Mock(schedule_timer=Mock(return_value=Mock())),
        lhs_storage=Mock(),
        lhs_lifecycle_manager=Mock(),
    )


@pytest.fixture
def today(manager: HeatingCycleLifecycleManager) -> date:
    """Today, as seen by the manager's own extraction clock."""
    return manager._get_current_time_for_extraction(None).date()


def _explore(storage: Mock, explored: set[date]) -> None:
    """Make the storage report ``explored`` as the explored days."""
    storage.get_cache_data.return_value = HeatingCycleCacheData(
        device_id=DEVICE_ID,
        cycles=(),
        last_search_time=datetime.now(UTC),
        retention_days=RETENTION_DAYS,
        explored_dates=frozenset(explored),
    )
    storage.get_oldest_explored_date.return_value = min(explored) if explored else None


class TestCalculateRetryWindow:
    """_calculate_retry_window() picks the most recent unexplored gap to retry."""

    @pytest.mark.asyncio
    async def test_returns_none_without_storage(
        self, manager: HeatingCycleLifecycleManager, today: date
    ) -> None:
        """Without storage there is no exploration state to retry from."""
        manager._heating_cycle_storage = None

        assert await manager._calculate_retry_window(today - timedelta(days=1)) is None

    @pytest.mark.asyncio
    async def test_returns_none_when_nothing_explored(
        self, manager: HeatingCycleLifecycleManager, storage: Mock, today: date
    ) -> None:
        """Before any exploration, the startup window and the backfill own every day."""
        assert await manager._calculate_retry_window(today - timedelta(days=1)) is None

        _explore(storage, set())
        assert await manager._calculate_retry_window(today - timedelta(days=1)) is None

    @pytest.mark.asyncio
    async def test_returns_none_without_gap(
        self, manager: HeatingCycleLifecycleManager, storage: Mock, today: date
    ) -> None:
        """A contiguous explored span leaves nothing to retry."""
        _explore(storage, _days(today - timedelta(days=20), today))

        assert await manager._calculate_retry_window(today - timedelta(days=1)) is None

    @pytest.mark.asyncio
    async def test_returns_the_gap_left_by_a_failed_read(
        self, manager: HeatingCycleLifecycleManager, storage: Mock, today: date
    ) -> None:
        """A gap inside the explored span is returned as is."""
        gap = _days(today - timedelta(days=12), today - timedelta(days=10))
        _explore(storage, _days(today - timedelta(days=20), today - timedelta(days=2)) - gap)

        window = await manager._calculate_retry_window(today - timedelta(days=1))

        assert window == (today - timedelta(days=12), today - timedelta(days=10))

    @pytest.mark.asyncio
    async def test_limits_a_long_gap_to_its_most_recent_period(
        self, manager: HeatingCycleLifecycleManager, storage: Mock, today: date
    ) -> None:
        """At most one task_range_days period is retried per refresh, the most recent one."""
        gap = _days(today - timedelta(days=18), today - timedelta(days=3))
        _explore(storage, _days(today - timedelta(days=20), today - timedelta(days=2)) - gap)

        window = await manager._calculate_retry_window(today - timedelta(days=1))

        assert window == (today - timedelta(days=9), today - timedelta(days=3))

    @pytest.mark.asyncio
    async def test_returns_the_most_recent_of_several_gaps(
        self, manager: HeatingCycleLifecycleManager, storage: Mock, today: date
    ) -> None:
        """Recent days matter most for learning, so the most recent gap goes first."""
        older_gap = _days(today - timedelta(days=16), today - timedelta(days=15))
        recent_gap = _days(today - timedelta(days=6), today - timedelta(days=5))
        explored = _days(today - timedelta(days=20), today - timedelta(days=2))
        _explore(storage, explored - older_gap - recent_gap)

        window = await manager._calculate_retry_window(today - timedelta(days=1))

        assert window == (today - timedelta(days=6), today - timedelta(days=5))

    @pytest.mark.asyncio
    async def test_ignores_gaps_older_than_retention(
        self, manager: HeatingCycleLifecycleManager, storage: Mock, today: date
    ) -> None:
        """Days outside the retention window are never worth a Recorder query."""
        gap = _days(today - timedelta(days=38), today - timedelta(days=32))
        _explore(storage, _days(today - timedelta(days=40), today - timedelta(days=2)) - gap)

        assert await manager._calculate_retry_window(today - timedelta(days=1)) is None

    @pytest.mark.asyncio
    async def test_ignores_days_re_extracted_by_the_refresh(
        self, manager: HeatingCycleLifecycleManager, storage: Mock, today: date
    ) -> None:
        """Yesterday and today are re-extracted by every refresh, whatever their state."""
        _explore(storage, _days(today - timedelta(days=20), today - timedelta(days=2)))

        window = await manager._calculate_retry_window(today - timedelta(days=1))

        assert window is None


class TestRefreshRetriesFailedPeriods:
    """trigger_24h_refresh() retries a failed gap alongside the backfill step."""

    @pytest.mark.asyncio
    async def test_refresh_launches_retry_with_backfill(
        self, manager: HeatingCycleLifecycleManager, storage: Mock, today: date
    ) -> None:
        """Both catch-up ranges are launched together, retry first."""
        gap = _days(today - timedelta(days=12), today - timedelta(days=10))
        _explore(storage, _days(today - timedelta(days=20), today - timedelta(days=2)) - gap)
        manager._launch_extraction_for_ranges = AsyncMock(return_value=True)

        await manager.trigger_24h_refresh()
        await manager.cancel_extraction()

        manager._launch_extraction_for_ranges.assert_awaited_once_with(
            [
                (today - timedelta(days=12), today - timedelta(days=10)),
                (today - timedelta(days=27), today - timedelta(days=21)),
            ]
        )

    @pytest.mark.asyncio
    async def test_refresh_launches_retry_when_backfill_is_complete(
        self, manager: HeatingCycleLifecycleManager, storage: Mock, today: date
    ) -> None:
        """A failed gap is retried even once the backfill has reached the retention start."""
        gap = _days(today - timedelta(days=12), today - timedelta(days=10))
        _explore(storage, _days(today - timedelta(days=30), today - timedelta(days=2)) - gap)
        manager._launch_extraction_for_ranges = AsyncMock(return_value=True)

        await manager.trigger_24h_refresh()
        await manager.cancel_extraction()

        manager._launch_extraction_for_ranges.assert_awaited_once_with(
            [(today - timedelta(days=12), today - timedelta(days=10))]
        )

    @pytest.mark.asyncio
    async def test_refresh_launches_nothing_more_without_gap_or_backfill(
        self, manager: HeatingCycleLifecycleManager, storage: Mock, today: date
    ) -> None:
        """Without failures, the refresh costs no extra Recorder query (SC-004)."""
        _explore(storage, _days(today - timedelta(days=30), today - timedelta(days=2)))
        manager._launch_extraction_for_ranges = AsyncMock(return_value=True)

        await manager.trigger_24h_refresh()
        await manager.cancel_extraction()

        manager._launch_extraction_for_ranges.assert_not_awaited()
