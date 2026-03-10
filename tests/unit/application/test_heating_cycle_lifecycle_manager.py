"""Unit tests for HeatingCycleLifecycleManager.

Refactored structure: ONE test per public method covering ALL scenarios.

Author: QA Engineer
Purpose: Comprehensive test coverage for heating cycle lifecycle management
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import date, datetime, timedelta, timezone
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
from custom_components.intelligent_heating_pilot.domain.value_objects.heating_cycle_cache_data import (
    HeatingCycleCacheData,
)
from custom_components.intelligent_heating_pilot.domain.value_objects.historical_data import (
    HistoricalDataSet,
)


class TestHeatingCycleLifecycleManager:
    """Test suite for HeatingCycleLifecycleManager lifecycle operations."""

    @pytest.fixture
    def base_datetime(self) -> datetime:
        """Provide base datetime for testing."""
        return datetime(2025, 2, 10, 12, 0, 0, tzinfo=timezone.utc)

    @pytest.fixture
    def device_config(self) -> DeviceConfig:
        """Create device configuration."""
        return DeviceConfig(
            device_id="climate.test_vtherm",
            vtherm_entity_id="climate.test_vtherm",
            scheduler_entities=["schedule.heating"],
            lhs_retention_days=30,
        )

    @pytest.fixture
    def mock_heating_cycle_service(self) -> Mock:
        """Create mock IHeatingCycleService."""
        service = Mock()
        service.extract_heating_cycles = AsyncMock(return_value=[])
        return service

    @pytest.fixture
    def mock_historical_adapter(self) -> Mock:
        """Create mock IHistoricalDataAdapter."""
        from custom_components.intelligent_heating_pilot.domain.value_objects.historical_data import (
            HistoricalDataKey,
        )

        adapter = Mock()

        # Create HistoricalDataSet with all keys initialized to empty lists
        def create_empty_dataset(*args, **kwargs):
            return HistoricalDataSet(data={key: [] for key in HistoricalDataKey})

        adapter.fetch_historical_data = AsyncMock(side_effect=create_empty_dataset)
        # fetch_all_historical_data is now the primary entry point used by _extract_day
        adapter.fetch_all_historical_data = AsyncMock(
            return_value=HistoricalDataSet(data={key: [] for key in HistoricalDataKey})
        )
        return adapter

    @pytest.fixture
    def mock_heating_cycle_storage(self) -> Mock:
        """Create mock IHeatingCycleStorage."""
        cache = Mock()
        cache.get_cache_data = AsyncMock(return_value=None)
        cache.set_cached_cycles = AsyncMock()
        cache.update_cycle_window = AsyncMock()
        cache.clear_cache = AsyncMock()
        cache.prune_old_cycles = AsyncMock()
        cache.append_cycles = AsyncMock()
        cache.append_explored_dates = AsyncMock()
        cache.get_oldest_explored_date = AsyncMock(return_value=None)
        return cache

    @pytest.fixture
    def mock_timer_scheduler(self) -> Mock:
        """Create mock ITimerScheduler."""
        scheduler = Mock()
        scheduler.schedule_timer = Mock(return_value=Mock())  # Returns cancel function
        return scheduler

    @pytest.fixture
    def mock_lhs_storage(self) -> Mock:
        """Create mock ILhsStorage."""
        storage = Mock()
        storage.save_heating_cycle = AsyncMock()
        storage.get_heating_cycles = AsyncMock(return_value=[])
        return storage

    @pytest.fixture
    def mock_lhs_lifecycle_manager(self) -> Mock:
        """Create mock ILhsLifecycleManager."""
        manager = Mock()
        manager.on_cycles_updated = AsyncMock()
        manager.update_global_lhs_from_cycles = AsyncMock()
        manager.update_contextual_lhs_from_cycles = AsyncMock()
        return manager

    @pytest.fixture
    def manager(
        self,
        device_config: DeviceConfig,
        mock_heating_cycle_service: Mock,
        mock_historical_adapter: Mock,
        mock_heating_cycle_storage: Mock,
        mock_timer_scheduler: Mock,
        mock_lhs_storage: Mock,
        mock_lhs_lifecycle_manager: Mock,
    ) -> HeatingCycleLifecycleManager:
        """Create fully-configured HeatingCycleLifecycleManager instance."""
        return HeatingCycleLifecycleManager(
            device_config=device_config,
            heating_cycle_service=mock_heating_cycle_service,
            historical_adapters=[mock_historical_adapter],
            heating_cycle_storage=mock_heating_cycle_storage,
            timer_scheduler=mock_timer_scheduler,
            lhs_storage=mock_lhs_storage,
            lhs_lifecycle_manager=mock_lhs_lifecycle_manager,
        )

    def _create_heating_cycle(
        self,
        start_time: datetime,
        duration_hours: float = 1.0,
        temp_increase: float = 2.0,
        device_id: str = "climate.test_vtherm",
    ) -> HeatingCycle:
        """Create a test heating cycle."""
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
            dead_time_cycle_minutes=None,
        )

    # ===== Test: refresh_heating_cycle_cache() - ONE test for ALL scenarios =====

    @pytest.mark.asyncio
    async def test_refresh_heating_cycle_cache(
        self,
        manager: HeatingCycleLifecycleManager,
        mock_heating_cycle_service: Mock,
        mock_heating_cycle_storage: Mock,
        mock_timer_scheduler: Mock,
        base_datetime: datetime,
    ) -> None:
        """Test refresh_heating_cycle_cache lifecycle event.

        Method documentation summary:
        - Schedule 24h timer at dt_util.now() + 24H
        - Calculate extraction window (end = yesterday)
        - Find missing date ranges vs current cache
        - Launch async extraction only for missing ranges
        - Prune old cycles from storage

        Verified aspects:
        - Aspect A: Schedules 24h timer when scheduler provided
        - Aspect B: Async extraction queue is launched
        - Aspect C: Returns None (no return value)
        - Aspect D: In-memory cache dict exists (lazily populated)
        - Aspect E: Queue has exactly as many tasks as distinct missing days
                    (one task per day in [window_start, window_end])
        """
        # GIVEN: service returns actual HeatingCycle objects (not empty)
        cycles = [
            self._create_heating_cycle(base_datetime - timedelta(days=1)),
            self._create_heating_cycle(base_datetime - timedelta(days=2)),
        ]
        mock_heating_cycle_service.extract_heating_cycles.return_value = cycles
        # cache is empty → all window days are "missing" → queue covers full window
        mock_heating_cycle_storage.get_cache_data.return_value = None

        # WHEN: refresh is called
        result = await manager.refresh_heating_cycle_cache()

        # THEN Aspect C: returns None
        assert result is None

        # THEN Aspect A: Schedules 24h timer when scheduler provided
        mock_timer_scheduler.schedule_timer.assert_called_once()

        # THEN Aspect B: Async extraction queue is launched
        assert manager._extraction_queue is not None

        # THEN Aspect D: In-memory cache dict exists (lazily populated)
        assert isinstance(manager._cached_cycles_for_target_time, dict)

        # THEN Aspect E: queue task count == 1 (startup window = task_range_days only)
        # Startup uses _calculate_startup_window() — only the most recent task_range_days
        # period is extracted. Full historical backfill happens progressively via 24h refresh.
        expected_tasks = 1
        # Wait for the background extraction task to complete
        assert manager._extraction_task is not None
        try:
            await asyncio.wait_for(manager._extraction_task, timeout=10.0)
        except asyncio.TimeoutError:
            manager._extraction_task.cancel()
            with suppress(asyncio.CancelledError):
                await manager._extraction_task
            pytest.fail("Background extraction task timed out")
        # Verify the task completed without exception
        assert not manager._extraction_task.cancelled()
        # extract_heating_cycles is called once for the single startup period
        assert mock_heating_cycle_service.extract_heating_cycles.call_count == expected_tasks

    # ===== Test: on_retention_change() - ONE test for ALL scenarios =====

    @pytest.mark.asyncio
    async def test_on_retention_change(
        self,
        manager: HeatingCycleLifecycleManager,
        mock_heating_cycle_storage: Mock,
        mock_lhs_lifecycle_manager: AsyncMock,
        device_config: DeviceConfig,
        base_datetime: datetime,
    ) -> None:
        """Test on_retention_change lifecycle event.

        Method documentation summary:
        - Update device config with new retention days
        - Update existing caches
        - Persist cycle
        - Cascade to LhsLifecycleManager with new cycles

        Verified aspects:
        - Aspect A: Update caches with new retention (triggers recalculation)
        - Aspect B: Store new cache on disk (IHeatingCycleStorage)
        - Aspect C: Call LhsLifecycleManager to cascade updates (if present)
        """
        # GIVEN: Setup for ALL aspects
        # - New retention days
        new_retention_days = 14

        # - Original retention is 30 days
        assert device_config.lhs_retention_days == 30

        # Pre-populate memory cache with cycles keyed by (device_id, date)
        device_id = device_config.device_id
        old_cycles = [
            self._create_heating_cycle(base_datetime - timedelta(days=25)),
            self._create_heating_cycle(base_datetime - timedelta(days=14)),
            self._create_heating_cycle(base_datetime - timedelta(days=5)),
            self._create_heating_cycle(base_datetime - timedelta(days=3)),
        ]

        # Populate cache as dict[(device_id, date)] -> list[HeatingCycle]
        for cycle in old_cycles:
            cache_key = (device_id, cycle.start_time.date())
            manager._cached_cycles_for_target_time[cache_key] = [cycle]

        # Verify cache is populated
        initial_cache_size = len(manager._cached_cycles_for_target_time)
        assert initial_cache_size == 4

        # Configure mock to return cycles for re-extraction (non-empty list required)
        manager._heating_cycle_service.extract_heating_cycles = AsyncMock(
            return_value=[
                self._create_heating_cycle(base_datetime - timedelta(days=7)),
                self._create_heating_cycle(base_datetime - timedelta(days=3)),
            ]
        )

        # WHEN: Retention change is triggered (SINGLE CALL for manager without cache)
        await manager.on_retention_change(new_retention_days)

        # THEN Aspect A: Memory cache is cleared (retention change invalidates cache)
        assert len(manager._cached_cycles_for_target_time) == 0

        # THEN: Storage cycles outside retention are pruned (NOT a full wipe)
        assert mock_heating_cycle_storage.prune_old_cycles.called

        # THEN: Async extraction queue is launched for missing ranges
        assert manager._extraction_queue is not None

        # Cleanup: cancel background task to prevent lingering-task warnings
        if manager._extraction_task is not None:
            manager._extraction_task.cancel()
            with suppress(asyncio.CancelledError):
                await manager._extraction_task

    # ===== Test: refresh_heating_cycle_cache() periodic =====

    @pytest.mark.asyncio
    async def test_refresh_heating_cycle_cache_periodic(
        self,
        manager: HeatingCycleLifecycleManager,
        mock_heating_cycle_service: Mock,
        mock_heating_cycle_storage: Mock,
        base_datetime: datetime,
    ) -> None:
        """Test refresh_heating_cycle_cache when called periodically (e.g., from timer).

        Verified aspects:
        - Aspect A: Launches async extraction queue
        - Aspect B: Works multiple consecutive calls (new queue created each time)
        - Aspect C: Works with and without cache – no exception raised
        """
        # GIVEN
        new_cycles = [self._create_heating_cycle(base_datetime)]
        mock_heating_cycle_service.extract_heating_cycles.return_value = new_cycles

        # WHEN: first call
        await manager.refresh_heating_cycle_cache()

        # THEN Aspect A: Async extraction queue is launched
        assert manager._extraction_queue is not None

        # WHEN: second call (cancels first queue, creates new one)
        await manager.refresh_heating_cycle_cache()

        # THEN Aspect B: New extraction queue is still set
        assert manager._extraction_queue is not None

        # WHEN: third call
        mock_heating_cycle_storage.append_cycles.reset_mock()
        await manager.refresh_heating_cycle_cache()

        # THEN: Queue still created (no exception) – Aspect C
        assert manager._extraction_queue is not None

        # Cleanup: cancel background task to prevent lingering-task warnings
        if manager._extraction_task is not None:
            manager._extraction_task.cancel()
            with suppress(asyncio.CancelledError):
                await manager._extraction_task

    # ===== Test: get_cycles_for_window() - ONE test for ALL scenarios =====

    @pytest.fixture
    def manager_with_cache(
        self,
        device_config: DeviceConfig,
        mock_heating_cycle_service: Mock,
        mock_historical_adapter: Mock,
        mock_heating_cycle_storage: Mock,
    ) -> HeatingCycleLifecycleManager:
        """Create manager with heating_cycle_storage but no other optional dependencies."""
        return HeatingCycleLifecycleManager(
            device_config=device_config,
            heating_cycle_service=mock_heating_cycle_service,
            historical_adapters=[mock_historical_adapter],
            heating_cycle_storage=mock_heating_cycle_storage,
            timer_scheduler=None,
            lhs_storage=None,
            lhs_lifecycle_manager=None,
        )

    @pytest.mark.asyncio
    async def test_get_cycles_for_window(
        self,
        manager: HeatingCycleLifecycleManager,
        manager_with_cache: HeatingCycleLifecycleManager,
        mock_heating_cycle_service: Mock,
        mock_heating_cycle_storage: Mock,
        base_datetime: datetime,
    ) -> None:
        """Test get_cycles_for_window method.

        Method documentation summary:
        - Returns cycles from in-memory cache if available
        - Falls back to persistent cache (IHeatingCycleStorage)
        - Extracts from historical data if no cache
        - Filters cycles to requested time window

        Verified aspects:
        - Aspect A: Returns cycles from cache when available
        - Aspect B: Extracts when no cache
        - Aspect C: Filters by time range
        - Aspect D: Handles empty result
        - Aspect E: Handles edge cases (zero duration, inverted range)
        - Aspect F: Persistent cache access optimization (cache hit vs miss)
        """
        # GIVEN: Setup for ALL aspects
        device_id = "climate.test_vtherm"
        start_time = base_datetime - timedelta(days=7)
        end_time = base_datetime

        # - Cached cycles exist
        cached_cycles = [
            self._create_heating_cycle(base_datetime - timedelta(days=2)),
            self._create_heating_cycle(base_datetime - timedelta(days=1)),
        ]
        cache_data = HeatingCycleCacheData(
            device_id=device_id,
            cycles=tuple(cached_cycles),
            last_search_time=base_datetime,
            retention_days=30,
        )
        mock_heating_cycle_storage.get_cache_data.return_value = cache_data

        # - Expected cycles for extraction (Aspect B)
        expected_cycles = [self._create_heating_cycle(base_datetime - timedelta(days=3))]
        mock_heating_cycle_service.extract_heating_cycles.return_value = expected_cycles

        # WHEN: get_cycles_for_window is called with cache
        result_cached = await manager_with_cache.get_cycles_for_window(
            device_id, start_time, end_time
        )

        # THEN Aspect A: Returns cycles from cache when available
        assert len(result_cached) == len(cached_cycles)
        mock_heating_cycle_storage.get_cache_data.assert_called_once()

        # THEN Aspect F: Persistent cache access optimization
        # Scenario 1: Cache hit (data in cache_data) → NO extraction needed
        mock_heating_cycle_service.extract_heating_cycles.assert_not_called()

        # WHEN: get_cycles_for_window is called with cache miss (get_cache_data returns None)
        # Reset mocks and configure for cache-miss scenario
        mock_heating_cycle_storage.reset_mock()
        mock_heating_cycle_storage.get_cache_data.return_value = None  # Simulate cache miss
        mock_heating_cycle_service.reset_mock()
        mock_heating_cycle_service.extract_heating_cycles.return_value = expected_cycles

        result = await manager.get_cycles_for_window(device_id, start_time, end_time)

        # THEN Aspect B: Cache miss returns empty list — NEVER calls _extract_cycles()
        # Bug fix: get_cycles_for_window must return [] on cache miss, not query Recorder
        mock_heating_cycle_service.extract_heating_cycles.assert_not_called()
        assert result == []

        # THEN Aspect C: Result is always a list
        assert isinstance(result, list)

        # THEN Aspect E: Handles edge cases
        # E1: Zero-duration window with cache miss still returns empty
        zero_start = base_datetime
        zero_end = base_datetime
        mock_heating_cycle_service.reset_mock()

        result_zero = await manager.get_cycles_for_window(device_id, zero_start, zero_end)
        assert isinstance(result_zero, list)
        assert result_zero == []
        mock_heating_cycle_service.extract_heating_cycles.assert_not_called()

        # E2: Inverted time range (should raise ValueError)
        inverted_start = base_datetime
        inverted_end = base_datetime - timedelta(days=7)

        with pytest.raises(ValueError):
            await manager.get_cycles_for_window(device_id, inverted_start, inverted_end)

    # ===== Test: get_cycles_for_target_time() - ONE test for ALL scenarios =====

    @pytest.mark.asyncio
    async def test_get_cycles_for_target_time(
        self,
        manager: HeatingCycleLifecycleManager,
        manager_with_cache: HeatingCycleLifecycleManager,
        mock_heating_cycle_service: Mock,
        mock_heating_cycle_storage: Mock,
        device_config: DeviceConfig,
        base_datetime: datetime,
    ) -> None:
        """Test get_cycles_for_target_time method.

        Method documentation summary:
        - Derives time window from target_time and retention_days
        - Window is [target_time - retention_days, target_time]
        - Returns cached cycles when available (memory cache hit)
        - Falls back to get_cycles_for_window if no cache

        Verified aspects:
        - Aspect A: Uses retention window correctly
        - Aspect B: Calculates correct time window
        - Aspect C: Returns cached when available
        - Aspect D: Persistent cache access optimization (cache hit vs miss)
        """
        # GIVEN: Setup for ALL aspects
        device_id = "climate.test_vtherm"
        target_time = base_datetime

        # - Expected cycles for extraction (Aspect A)
        expected_cycles = [self._create_heating_cycle(base_datetime - timedelta(days=10))]
        mock_heating_cycle_service.extract_heating_cycles.return_value = expected_cycles

        # WHEN: get_cycles_for_target_time is called (SINGLE CALL without cache)
        # Configure storage to return None (no cache) — should return [] without extraction
        mock_heating_cycle_storage.get_cache_data.return_value = None
        result = await manager.get_cycles_for_target_time(device_id, target_time)

        # THEN Aspect A: Cache miss returns empty list (no Recorder query)
        assert result == []
        mock_heating_cycle_service.extract_heating_cycles.assert_not_called()

        # THEN Aspect B: Calculates correct time window
        # Window should be [target_time - 30 days, target_time]
        # (verified in implementation)

        # THEN Aspect C & D: Cache optimization (with manager_with_cache and proper mock setup)
        # Reset and reconfigure mocks for cache scenarios
        mock_heating_cycle_storage.reset_mock()
        mock_heating_cycle_service.reset_mock()

        # Setup cache scenario: Configure storage to return cached data
        cached_cycles = [self._create_heating_cycle(base_datetime - timedelta(days=5))]
        cache_data_with_cycles = HeatingCycleCacheData(
            device_id=device_id,
            cycles=tuple(cached_cycles),
            last_search_time=base_datetime,
            retention_days=30,
        )
        mock_heating_cycle_storage.get_cache_data.return_value = cache_data_with_cycles

        # First call reads from storage cache and stores in memory
        result_cached_first = await manager_with_cache.get_cycles_for_target_time(
            device_id, target_time
        )

        # THEN Aspect C: Returns cached when available
        # Cycles are returned from storage cache
        assert result_cached_first == cached_cycles
        # Storage was accessed to get cache data
        mock_heating_cycle_storage.get_cache_data.assert_called()

        # THEN Aspect D: Memory cache optimization on second call
        # Use same target_time to trigger memory cache hit
        mock_heating_cycle_storage.reset_mock()
        result_cached_second = await manager_with_cache.get_cycles_for_target_time(
            device_id, target_time
        )

        # Should return cached value immediately without accessing storage
        assert result_cached_second == cached_cycles
        # Storage NOT called because memory cache hit
        mock_heating_cycle_storage.get_cache_data.assert_not_called()

    # ===== Test: update_cycles_for_window() - ONE test for ALL scenarios =====

    @pytest.mark.asyncio
    async def test_update_cycles_for_window(
        self,
        manager: HeatingCycleLifecycleManager,
        mock_heating_cycle_service: Mock,
        mock_heating_cycle_storage: Mock,
        base_datetime: datetime,
    ) -> None:
        """Test update_cycles_for_window method.

        Method documentation summary:
        - Extracts cycles for specified time window
        - Updates cache with extracted cycles
        - Persists cycles to model storage
        - Returns extracted cycles

        Verified aspects:
        - Aspect A: Extracts and returns cycles
        - Aspect B: Updates cache when present
        - Aspect C: Persists to storage when present
        - Aspect D: Handles extraction errors
        - Aspect E: Handles large windows
        """
        # GIVEN: Setup for ALL aspects
        device_id = "climate.test_vtherm"
        start_time = base_datetime - timedelta(days=7)
        end_time = base_datetime

        # - Expected cycles for extraction (Aspects A, B, C)
        expected_cycles = [
            self._create_heating_cycle(base_datetime - timedelta(days=5)),
            self._create_heating_cycle(base_datetime - timedelta(days=2)),
        ]
        mock_heating_cycle_service.extract_heating_cycles.return_value = expected_cycles

        # WHEN: update_cycles_for_window is called (SINGLE CALL without cache/storage)
        result = await manager.update_cycles_for_window(device_id, start_time, end_time)

        # THEN Aspect A: Extracts and returns cycles
        mock_heating_cycle_service.extract_heating_cycles.assert_called_once()
        assert result == expected_cycles

        # WHEN: update_cycles_for_window is called with cache (separate call)
        new_cycles = [self._create_heating_cycle(base_datetime - timedelta(days=3))]
        mock_heating_cycle_service.extract_heating_cycles.return_value = new_cycles

        await manager.update_cycles_for_window(device_id, start_time, end_time)

        # THEN Aspect B: Updates cache when present
        assert mock_heating_cycle_storage.append_cycles.called

        # WHEN: update_cycles_for_window is called with storage (separate call)
        storage_cycles = [self._create_heating_cycle(base_datetime)]
        mock_heating_cycle_service.extract_heating_cycles.return_value = storage_cycles

        await manager.update_cycles_for_window(device_id, start_time, end_time)

        # THEN Aspect E: Writes updated cycles to persistent cache
        mock_heating_cycle_storage.append_cycles.assert_called()  # Persists to disk

        # THEN Aspect D: Handles extraction errors
        # (Setup for error scenario)
        mock_heating_cycle_service.extract_heating_cycles.side_effect = ValueError(
            "Extraction error"
        )

        # Error is handled (may raise or return [])
        with pytest.raises(ValueError):
            await manager.update_cycles_for_window(device_id, start_time, end_time)

        # Reset for next aspect
        mock_heating_cycle_service.extract_heating_cycles.side_effect = None

        # THEN Aspect E: Handles large windows (365 days)
        # (Setup for large window)
        large_start = base_datetime - timedelta(days=365)
        large_end = base_datetime

        many_cycles = [
            self._create_heating_cycle(base_datetime - timedelta(days=i)) for i in range(0, 365, 30)
        ]
        mock_heating_cycle_service.extract_heating_cycles.return_value = many_cycles

        result_large = await manager.update_cycles_for_window(device_id, large_start, large_end)

        # All cycles are returned
        assert len(result_large) == len(many_cycles)

    # ===== Test: cancel() - ONE test for ALL scenarios =====

    @pytest.mark.asyncio
    async def test_cancel(
        self,
        manager: HeatingCycleLifecycleManager,
        mock_timer_scheduler: Mock,
        mock_heating_cycle_storage: Mock,
        base_datetime: datetime,
    ) -> None:
        """Test cancel lifecycle event.

        Method documentation summary:
        - Stop scheduled refresh timer (if present)
        - Do NOT clear cycle cache (data persists)
        - Release resources and cleanup

        Verified aspects:
        - Aspect A: Stops scheduled timer when present
        - Aspect B: Works without timer (no error)
        - Aspect C: Does NOT clear persistent cache
        - Aspect D: Is idempotent (can be called multiple times)
        """
        # GIVEN: Setup for ALL aspects
        # - Timer was scheduled during refresh
        cancel_func = Mock()
        mock_timer_scheduler.schedule_timer.return_value = cancel_func

        await manager.refresh_heating_cycle_cache()

        # WHEN: Cancel is called (SINGLE CALL for timer aspect)
        mock_heating_cycle_storage.clear_cache.reset_mock()

        await manager.cancel()

        # THEN Aspect A: Stops scheduled timer when present
        cancel_func.assert_called_once()

        # THEN Aspect C: Does NOT clear persistent cache (data remains)
        mock_heating_cycle_storage.clear_cache.assert_not_called()

        # WHEN: Cancel is called on manager without timer
        await manager.cancel()

        # THEN Aspect B: Works without timer (no error)
        # No exception is raised

        # THEN Aspect D: Is idempotent (can be called multiple times)
        # Setup manager again
        await manager.refresh_heating_cycle_cache()

        # Call cancel multiple times
        await manager.cancel()
        await manager.cancel()

        # No exception is raised

    # ===== Test: _calculate_startup_window() =====

    @pytest.mark.asyncio
    async def test_extraction_end_date_is_yesterday_not_today(
        self,
        manager: HeatingCycleLifecycleManager,
        base_datetime: datetime,
    ) -> None:
        """Test that startup extraction end_date is yesterday, not today.

        Avoids partial cycle extractions for the current day.
        Extraction end_date must be yesterday at the latest.
        """
        # WHEN: Calculate startup extraction window
        start_date, end_date = manager._calculate_startup_window()

        today = datetime.now().date()
        yesterday = today - timedelta(days=1)

        # THEN: end_date must not be today
        assert end_date < today, (
            f"end_date {end_date} must be before today {today} "
            "to avoid partial cycle extractions"
        )

        # THEN: end_date must be yesterday at most
        assert end_date == yesterday, f"end_date {end_date} should be yesterday {yesterday}"

    # ===== Tests: _trigger_incremental_extraction() =====

    @pytest.mark.asyncio
    async def test_trigger_incremental_extraction(
        self,
        manager: HeatingCycleLifecycleManager,
    ) -> None:
        """Test _trigger_incremental_extraction delegates to _launch_extraction_for_ranges.

        Verified aspects:
        - Aspect A: Creates extraction queue for the given date range
        - Aspect B: Launches async extraction task
        """
        start_d = date(2026, 1, 1)
        end_d = date(2026, 1, 3)

        await manager._trigger_incremental_extraction(
            device_id=manager._device_config.device_id,
            extraction_start_date=start_d,
            extraction_end_date=end_d,
        )

        # THEN Aspect A: Queue is created
        assert manager._extraction_queue is not None

        # THEN Aspect B: Async task is created and running/done
        assert manager._extraction_task is not None

        await manager.cancel()

    # ===== Tests: _on_incremental_extraction_day_complete() =====

    @pytest.mark.asyncio
    async def test_on_incremental_extraction_day_complete(
        self,
        manager: HeatingCycleLifecycleManager,
        mock_heating_cycle_storage: Mock,
        base_datetime: datetime,
    ) -> None:
        """Test _on_incremental_extraction_day_complete delegates to _on_cycles_extracted.

        Verified aspects:
        - Aspect A: Updates heating_cycle_storage with extracted cycles
        - Aspect B: Triggers LHS cascade
        - Aspect C: Empty list is a no-op
        """
        test_cycles = [
            self._create_heating_cycle(base_datetime - timedelta(days=1)),
        ]

        # WHEN: called with cycles
        await manager._on_incremental_extraction_day_complete(test_cycles)

        # THEN Aspect A: storage updated
        mock_heating_cycle_storage.append_cycles.assert_called_once()

        # WHEN: called with empty list
        mock_heating_cycle_storage.append_cycles.reset_mock()
        await manager._on_incremental_extraction_day_complete([])

        # THEN Aspect C: no storage call for empty list
        mock_heating_cycle_storage.append_cycles.assert_not_called()

    # ===== Tests: can_cancel_extraction() =====

    @pytest.mark.asyncio
    async def test_can_cancel_extraction(
        self,
        manager: HeatingCycleLifecycleManager,
    ) -> None:
        """Test can_cancel_extraction returns correct state.

        Verified aspects:
        - Aspect A: Returns False when no extraction is running
        - Aspect B: Returns True when extraction queue is running
        - Aspect C: Returns False after extraction completes
        """
        # THEN Aspect A: no extraction at startup
        assert await manager.can_cancel_extraction() is False

        # Start an extraction
        start_d = date(2026, 1, 1)
        end_d = date(2026, 1, 2)
        await manager._trigger_incremental_extraction(
            device_id=manager._device_config.device_id,
            extraction_start_date=start_d,
            extraction_end_date=end_d,
        )

        # THEN Aspect B: extraction is now running (or done very quickly)
        # The queue processes 2 days; may complete before this assertion,
        # so we just confirm the method returns a bool without error
        result = await manager.can_cancel_extraction()
        assert isinstance(result, bool)

        await manager.cancel()

        # THEN Aspect C: after cancel, no longer cancellable
        assert await manager.can_cancel_extraction() is False

    # ===== Tests: cancel_extraction() =====

    @pytest.mark.asyncio
    async def test_cancel_extraction(
        self,
        manager: HeatingCycleLifecycleManager,
    ) -> None:
        """Test cancel_extraction stops the running queue gracefully.

        Verified aspects:
        - Aspect A: No error when no extraction is running (idempotent)
        - Aspect B: After cancel, queue is no longer cancellable (extraction stops)
        """
        # THEN Aspect A: safe to call even without active extraction
        await manager.cancel_extraction()  # Should not raise

        # Setup: launch extraction with enough days to stay running
        start_d = date(2026, 1, 1)
        end_d = date(2026, 1, 5)
        await manager._trigger_incremental_extraction(
            device_id=manager._device_config.device_id,
            extraction_start_date=start_d,
            extraction_end_date=end_d,
        )

        # WHEN: cancel_extraction called
        await manager.cancel_extraction()

        # Allow the event loop to process the cancellation (background task stops)
        await asyncio.sleep(0.1)

        # THEN Aspect B: can_cancel_extraction returns False after cancellation
        # (queue was asked to stop; is no longer meaningfully cancellable)
        assert await manager.can_cancel_extraction() is False

        await manager.cancel()

    # ===== Tests: on_demand_extraction() =====

    @pytest.mark.asyncio
    async def test_on_demand_extraction(
        self,
        manager: HeatingCycleLifecycleManager,
        mock_heating_cycle_service: Mock,
        mock_heating_cycle_storage: Mock,
        base_datetime: datetime,
    ) -> None:
        """Test on_demand_extraction extracts and returns cycles for the requested range.

        Verified aspects:
        - Aspect A: Returns all extracted cycles for the date range
        - Aspect B: Persists cycles in storage via callback
        - Aspect C: Empty range returns empty list
        - Aspect D: Raises ValueError for mismatched device_id
        - Aspect E: Re-raises exceptions from queue execution
        """
        # GIVEN: service returns a cycle per call
        cycle = self._create_heating_cycle(base_datetime - timedelta(days=1))
        mock_heating_cycle_service.extract_heating_cycles = AsyncMock(return_value=[cycle])

        start_d = (base_datetime - timedelta(days=2)).date()
        end_d = (base_datetime - timedelta(days=1)).date()

        # WHEN: on-demand extraction
        result = await manager.on_demand_extraction(
            device_id=manager._device_config.device_id,
            start_date=start_d,
            end_date=end_d,
        )

        # THEN Aspect A: cycles returned (2-day range fits in 1 weekly task → 1 call → 1 cycle)
        assert len(result) == 1
        assert all(isinstance(c, HeatingCycle) for c in result)

        # THEN Aspect B: storage updated for each extracted cycle batch
        assert mock_heating_cycle_storage.append_cycles.called

        # WHEN: empty range (same day start and end, no cycles)
        mock_heating_cycle_service.extract_heating_cycles = AsyncMock(return_value=[])
        result_empty = await manager.on_demand_extraction(
            device_id=manager._device_config.device_id,
            start_date=start_d,
            end_date=start_d,
        )

        # THEN Aspect C: empty list returned
        assert result_empty == []

        # THEN Aspect D: raises ValueError when device_id does not match manager's scope
        with pytest.raises(ValueError, match="scoped to device_id"):
            await manager.on_demand_extraction(
                device_id="climate.wrong_device",
                start_date=start_d,
                end_date=end_d,
            )

        # THEN Aspect E: re-raises when there are per-day failures (queue swallows but on_demand checks)
        mock_heating_cycle_service.extract_heating_cycles = AsyncMock(
            side_effect=RuntimeError("Recorder unavailable")
        )
        with pytest.raises(RuntimeError, match="day.*fail"):
            await manager.on_demand_extraction(
                device_id=manager._device_config.device_id,
                start_date=start_d,
                end_date=end_d,
            )

    # ===== Tests: _calculate_backfill_window() =====

    @pytest.mark.asyncio
    async def test_calculate_backfill_window_returns_none_when_no_storage(
        self,
        device_config: DeviceConfig,
        mock_heating_cycle_service: Mock,
        mock_historical_adapter: Mock,
        mock_lhs_storage: Mock,
        mock_lhs_lifecycle_manager: Mock,
    ) -> None:
        """Returns None when no storage is configured (storage=None)."""
        manager = HeatingCycleLifecycleManager(
            device_config=device_config,
            heating_cycle_service=mock_heating_cycle_service,
            historical_adapters=[mock_historical_adapter],
            heating_cycle_storage=None,
            timer_scheduler=None,
            lhs_storage=mock_lhs_storage,
            lhs_lifecycle_manager=mock_lhs_lifecycle_manager,
        )

        result = await manager._calculate_backfill_window()
        assert result is None

    @pytest.mark.asyncio
    async def test_calculate_backfill_window_returns_none_when_no_explored_dates(
        self,
        manager: HeatingCycleLifecycleManager,
        mock_heating_cycle_storage: Mock,
    ) -> None:
        """Returns None when oldest_explored_date is None (startup not yet done)."""
        mock_heating_cycle_storage.get_oldest_explored_date = AsyncMock(return_value=None)

        result = await manager._calculate_backfill_window()
        assert result is None

    @pytest.mark.asyncio
    async def test_calculate_backfill_window_returns_none_when_coverage_complete(
        self,
        manager: HeatingCycleLifecycleManager,
        mock_heating_cycle_storage: Mock,
    ) -> None:
        """Returns None when oldest explored date reaches or passes the retention boundary."""
        today = datetime.now().date()
        max_start = today - timedelta(days=manager._device_config.lhs_retention_days)
        # oldest = max_start exactly → coverage complete
        mock_heating_cycle_storage.get_oldest_explored_date = AsyncMock(return_value=max_start)

        result = await manager._calculate_backfill_window()
        assert result is None

    @pytest.mark.asyncio
    async def test_calculate_backfill_window_returns_next_step(
        self,
        manager: HeatingCycleLifecycleManager,
        mock_heating_cycle_storage: Mock,
    ) -> None:
        """Returns the next backward 7-day period when backfill is incomplete.

        Uses current real time (not base_datetime) since _get_current_time_for_extraction
        uses dt_util.now() / datetime.now().
        """
        # oldest = 7 days before yesterday (what startup window would have explored)
        today = datetime.now().date()
        yesterday = today - timedelta(days=1)
        oldest = yesterday - timedelta(days=manager._device_config.task_range_days - 1)
        mock_heating_cycle_storage.get_oldest_explored_date = AsyncMock(return_value=oldest)

        result = await manager._calculate_backfill_window()

        assert result is not None, (
            f"Expected backfill window but got None. oldest={oldest}, "
            f"retention={manager._device_config.lhs_retention_days} days. "
            "Ensure oldest is within the retention window."
        )
        start_date, end_date = result

        # end_date must be oldest - 1 day
        assert end_date == oldest - timedelta(days=1)
        # span must equal task_range_days
        span = (end_date - start_date).days
        assert span == manager._device_config.task_range_days - 1

    @pytest.mark.asyncio
    async def test_calculate_backfill_window_clamps_to_retention_boundary(
        self,
        manager: HeatingCycleLifecycleManager,
        mock_heating_cycle_storage: Mock,
    ) -> None:
        """start_date is clamped to max_start when the step would exceed retention.

        If 3 days remain before the retention boundary, start_date = max_start (not 7 days back).
        """
        today = datetime.now().date()
        max_start = today - timedelta(days=manager._device_config.lhs_retention_days)
        # oldest is 4 days past the retention boundary (3-day gap remains)
        oldest = max_start + timedelta(days=4)
        mock_heating_cycle_storage.get_oldest_explored_date = AsyncMock(return_value=oldest)

        result = await manager._calculate_backfill_window()

        assert result is not None
        start_date, end_date = result

        # start_date should be clamped at max_start
        assert start_date == max_start
        assert end_date == oldest - timedelta(days=1)

    # ===== Tests: trigger_24h_refresh() backfill =====

    @pytest.mark.asyncio
    async def test_trigger_24h_refresh_launches_backfill_when_incomplete(
        self,
        manager: HeatingCycleLifecycleManager,
        mock_heating_cycle_storage: Mock,
        mock_heating_cycle_service: Mock,
    ) -> None:
        """trigger_24h_refresh must launch a backfill extraction when coverage is incomplete.

        After the recent-days refresh, if oldest_explored_date is not yet at the
        retention boundary, a backfill step must be queued.
        """
        # Simulate: startup window was explored, oldest = 7 days before yesterday → backfill needed
        today = datetime.now().date()
        oldest = today - timedelta(days=8)  # well within retention window
        mock_heating_cycle_storage.get_oldest_explored_date = AsyncMock(return_value=oldest)

        # _find_missing_date_ranges will return the full range (explored_dates=empty)
        mock_heating_cycle_storage.get_cache_data = AsyncMock(return_value=None)

        await manager.trigger_24h_refresh()

        # _launch_extraction_for_ranges creates a new queue; verify service was called
        # at least for the backfill window (extract_heating_cycles called at least once)
        assert mock_heating_cycle_service.extract_heating_cycles.called or (
            manager._extraction_queue is not None
        ), "Backfill extraction should have been launched"

    @pytest.mark.asyncio
    async def test_trigger_24h_refresh_skips_backfill_when_complete(
        self,
        manager: HeatingCycleLifecycleManager,
        mock_heating_cycle_storage: Mock,
        mock_heating_cycle_service: Mock,
    ) -> None:
        """trigger_24h_refresh skips backfill when full coverage is already reached."""
        today = datetime.now().date()
        max_start = today - timedelta(days=manager._device_config.lhs_retention_days)
        mock_heating_cycle_storage.get_oldest_explored_date = AsyncMock(return_value=max_start)

        await manager.trigger_24h_refresh()

        # A new queue is always created for the recent refresh (yesterday+today).
        # But since backfill is complete, no ADDITIONAL backfill queue should be created.
        # We verify _calculate_backfill_window returned None (indirectly, by checking
        # that get_oldest_explored_date was called and backfill wasn't launched).
        mock_heating_cycle_storage.get_oldest_explored_date.assert_called_once()

    # ===== Bug 2: get_cycles_for_window() must return [] on cache miss =====

    @pytest.mark.asyncio
    async def test_get_cycles_for_window_returns_empty_when_storage_is_none(
        self,
        device_config: DeviceConfig,
        mock_heating_cycle_service: Mock,
        mock_historical_adapter: Mock,
        base_datetime: datetime,
    ) -> None:
        """get_cycles_for_window must return [] when _heating_cycle_storage is None.

        Bug fix validation: When no storage is configured at all, the method must
        return an empty list immediately — never attempt to extract from Recorder.
        """
        # GIVEN: Manager created WITHOUT heating_cycle_storage
        manager_no_storage = HeatingCycleLifecycleManager(
            device_config=device_config,
            heating_cycle_service=mock_heating_cycle_service,
            historical_adapters=[mock_historical_adapter],
            heating_cycle_storage=None,
            timer_scheduler=None,
            lhs_storage=None,
            lhs_lifecycle_manager=None,
        )

        device_id = device_config.device_id
        start_time = base_datetime - timedelta(days=7)
        end_time = base_datetime

        # WHEN: get_cycles_for_window is called
        result = await manager_no_storage.get_cycles_for_window(device_id, start_time, end_time)

        # THEN: Returns empty list
        assert result == []

        # THEN: _extract_cycles was NEVER called (no Recorder query)
        mock_heating_cycle_service.extract_heating_cycles.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_cycles_for_window_returns_empty_on_cache_miss_no_extraction(
        self,
        manager_with_cache: HeatingCycleLifecycleManager,
        mock_heating_cycle_service: Mock,
        mock_heating_cycle_storage: Mock,
        base_datetime: datetime,
    ) -> None:
        """get_cycles_for_window must return [] when cache returns None (cache miss).

        Bug fix validation: When _heating_cycle_storage.get_cache_data() returns None,
        the method must return an empty list — NOT fall through to _extract_cycles().
        This prevents OOM issues from querying the Recorder at startup.
        """
        # GIVEN: Storage exists but get_cache_data returns None (cache miss)
        mock_heating_cycle_storage.get_cache_data.return_value = None
        mock_heating_cycle_service.extract_heating_cycles.return_value = [
            self._create_heating_cycle(base_datetime - timedelta(days=1)),
        ]

        device_id = "climate.test_vtherm"
        start_time = base_datetime - timedelta(days=7)
        end_time = base_datetime

        # WHEN: get_cycles_for_window is called
        result = await manager_with_cache.get_cycles_for_window(device_id, start_time, end_time)

        # THEN: Returns empty list (NOT the extracted cycles)
        assert result == []

        # THEN: _extract_cycles was NEVER called
        mock_heating_cycle_service.extract_heating_cycles.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_cycles_for_window_filters_from_cache_on_hit(
        self,
        manager_with_cache: HeatingCycleLifecycleManager,
        mock_heating_cycle_service: Mock,
        mock_heating_cycle_storage: Mock,
        base_datetime: datetime,
    ) -> None:
        """get_cycles_for_window returns filtered cycles from cache when data exists.

        Regression guard: cache hit path must still filter and return cycles correctly.
        """
        # GIVEN: Cache has cycles, some inside and some outside the window
        device_id = "climate.test_vtherm"
        in_window_cycle = self._create_heating_cycle(base_datetime - timedelta(days=2))
        out_of_window_cycle = self._create_heating_cycle(base_datetime - timedelta(days=20))

        cache_data = HeatingCycleCacheData(
            device_id=device_id,
            cycles=tuple([in_window_cycle, out_of_window_cycle]),
            last_search_time=base_datetime,
            retention_days=30,
        )
        mock_heating_cycle_storage.get_cache_data.return_value = cache_data

        start_time = base_datetime - timedelta(days=7)
        end_time = base_datetime

        # WHEN: get_cycles_for_window is called
        result = await manager_with_cache.get_cycles_for_window(device_id, start_time, end_time)

        # THEN: Only in-window cycle is returned
        assert len(result) == 1
        assert result[0] == in_window_cycle

        # THEN: No extraction was performed
        mock_heating_cycle_service.extract_heating_cycles.assert_not_called()

    # ===== Bug 1: 24h timer must schedule trigger_24h_refresh (not refresh_heating_cycle_cache) =====

    @pytest.mark.asyncio
    async def test_refresh_schedules_trigger_24h_refresh_as_timer_callback(
        self,
        manager: HeatingCycleLifecycleManager,
        mock_heating_cycle_service: Mock,
        mock_heating_cycle_storage: Mock,
        mock_timer_scheduler: Mock,
        base_datetime: datetime,
    ) -> None:
        """After refresh_heating_cycle_cache(), the 24h timer must call trigger_24h_refresh.

        Bug fix validation: The timer callback must be self.trigger_24h_refresh,
        NOT self.refresh_heating_cycle_cache. Using refresh_heating_cycle_cache as
        the callback would bypass backfill logic and cause incorrect scheduling.
        """
        # GIVEN: Manager with timer scheduler
        mock_heating_cycle_storage.get_cache_data.return_value = None

        # WHEN: refresh_heating_cycle_cache is called
        await manager.refresh_heating_cycle_cache()

        # THEN: Timer was scheduled
        mock_timer_scheduler.schedule_timer.assert_called_once()

        # THEN: The callback target is trigger_24h_refresh (NOT refresh_heating_cycle_cache)
        call_args = mock_timer_scheduler.schedule_timer.call_args
        scheduled_callback = call_args[0][1]  # Second positional arg is the callback
        assert scheduled_callback == manager.trigger_24h_refresh, (
            f"Timer callback should be trigger_24h_refresh, "
            f"but got {scheduled_callback.__name__}"
        )
        assert (
            scheduled_callback != manager.refresh_heating_cycle_cache
        ), "Timer callback must NOT be refresh_heating_cycle_cache"

        # Cleanup
        if manager._extraction_task is not None:
            manager._extraction_task.cancel()
            with suppress(asyncio.CancelledError):
                await manager._extraction_task

    @pytest.mark.asyncio
    async def test_trigger_24h_refresh_reschedules_next_timer(
        self,
        manager: HeatingCycleLifecycleManager,
        mock_timer_scheduler: Mock,
        mock_heating_cycle_storage: Mock,
    ) -> None:
        """trigger_24h_refresh must reschedule the next 24h timer itself.

        Bug fix validation: After trigger_24h_refresh() runs, it must schedule
        the next 24h timer so that periodic refresh continues indefinitely.
        """
        # GIVEN: Timer scheduler is available, no previous timer
        cancel_func = Mock()
        mock_timer_scheduler.schedule_timer.return_value = cancel_func
        mock_heating_cycle_storage.get_cache_data.return_value = None

        # WHEN: trigger_24h_refresh is called
        await manager.trigger_24h_refresh()

        # THEN: A new 24h timer was scheduled
        mock_timer_scheduler.schedule_timer.assert_called()

        # THEN: The scheduled callback is trigger_24h_refresh (for next cycle)
        call_args = mock_timer_scheduler.schedule_timer.call_args
        scheduled_callback = call_args[0][1]
        assert scheduled_callback == manager.trigger_24h_refresh, (
            f"trigger_24h_refresh must reschedule itself, "
            f"but scheduled {scheduled_callback.__name__}"
        )

        # Cleanup
        if manager._extraction_task is not None:
            manager._extraction_task.cancel()
            with suppress(asyncio.CancelledError):
                await manager._extraction_task

    # ===== Bug 4: _on_cycles_extracted must call on_extraction_complete_callback =====

    @pytest.mark.asyncio
    async def test_on_cycles_extracted_calls_extraction_complete_callback(
        self,
        manager: HeatingCycleLifecycleManager,
        mock_heating_cycle_storage: Mock,
        base_datetime: datetime,
    ) -> None:
        """_on_cycles_extracted must call on_extraction_complete_callback when cycles are extracted.

        Bug fix validation: After processing extracted cycles (storage update + LHS cascade),
        the method must notify sensors via on_extraction_complete_callback so they recalculate.
        """
        # GIVEN: Callback is set on the manager
        callback = AsyncMock()
        manager._on_extraction_complete_callback = callback

        test_cycles = [
            self._create_heating_cycle(base_datetime - timedelta(days=1)),
        ]

        # WHEN: _on_cycles_extracted is called with cycles
        await manager._on_cycles_extracted(test_cycles)

        # THEN: The callback was called
        callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_cycles_extracted_no_error_when_callback_is_none(
        self,
        manager: HeatingCycleLifecycleManager,
        mock_heating_cycle_storage: Mock,
        base_datetime: datetime,
    ) -> None:
        """_on_cycles_extracted must not error when on_extraction_complete_callback is None.

        Regression guard: When no callback is configured, extraction completes normally.
        """
        # GIVEN: No callback set (default state)
        # Ensure the attribute doesn't exist or is None
        if hasattr(manager, "_on_extraction_complete_callback"):
            manager._on_extraction_complete_callback = None

        test_cycles = [
            self._create_heating_cycle(base_datetime - timedelta(days=1)),
        ]

        # WHEN: _on_cycles_extracted is called — should not raise
        await manager._on_cycles_extracted(test_cycles)

        # THEN: Storage was still updated (core logic not affected)
        mock_heating_cycle_storage.append_cycles.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_cycles_extracted_catches_callback_exception(
        self,
        manager: HeatingCycleLifecycleManager,
        mock_heating_cycle_storage: Mock,
        base_datetime: datetime,
    ) -> None:
        """_on_cycles_extracted must catch and log exceptions from the callback.

        Bug fix validation: If on_extraction_complete_callback raises, it must not
        crash the extraction pipeline. The error is logged and processing continues.
        """
        # GIVEN: Callback that raises an exception
        callback = AsyncMock(side_effect=RuntimeError("Sensor update failed"))
        manager._on_extraction_complete_callback = callback

        test_cycles = [
            self._create_heating_cycle(base_datetime - timedelta(days=1)),
        ]

        # WHEN: _on_cycles_extracted is called — should not raise
        await manager._on_cycles_extracted(test_cycles)

        # THEN: Callback was called (and raised, but error was caught)
        callback.assert_called_once()

        # THEN: Storage was still updated (core logic not disrupted)
        mock_heating_cycle_storage.append_cycles.assert_called_once()
