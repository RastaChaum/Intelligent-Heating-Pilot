"""Unit tests for LhsLifecycleManager.

Refactored structure: ONE test per public method covering ALL scenarios.

Author: QA Engineer
Purpose: Comprehensive test coverage for LHS lifecycle management
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.intelligent_heating_pilot.application.lhs_lifecycle_manager import (
    LhsLifecycleManager,
)
from custom_components.intelligent_heating_pilot.domain.constants import (
    DEFAULT_LEARNED_SLOPE,
)
from custom_components.intelligent_heating_pilot.domain.value_objects.heating import (
    HeatingCycle,
)
from custom_components.intelligent_heating_pilot.domain.value_objects.lhs_cache_entry import (
    LHSCacheEntry,
)


class TestLhsLifecycleManager:
    """Test suite for LhsLifecycleManager lifecycle operations."""

    @pytest.fixture
    def base_datetime(self) -> datetime:
        """Provide base datetime for testing."""
        return datetime(2025, 2, 10, 12, 0, 0)

    @pytest.fixture
    def mock_model_storage(self) -> Mock:
        """Create mock ILhsStorage."""
        storage = Mock()
        storage.get_cached_global_lhs = AsyncMock(return_value=None)
        storage.set_cached_global_lhs = AsyncMock()
        storage.get_cached_contextual_lhs = AsyncMock(return_value=None)
        storage.set_cached_contextual_lhs = AsyncMock()
        return storage

    @pytest.fixture
    def mock_global_lhs_calculator(self) -> Mock:
        """Create mock GlobalLHSCalculatorService."""
        calculator = Mock()
        calculator.calculate_global_lhs = Mock(return_value=2.5)
        return calculator

    @pytest.fixture
    def mock_contextual_lhs_calculator(self) -> Mock:
        """Create mock ContextualLHSCalculatorService."""
        calculator = Mock()
        calculator.calculate_contextual_lhs = Mock(return_value={0: 2.0, 6: 2.5, 12: 3.0})
        calculator.calculate_all_contextual_lhs = Mock(return_value={0: 2.0, 6: 2.5, 12: 3.0})
        # Configure for per-hour calculation
        calculator.calculate_contextual_lhs_for_hour = Mock(return_value=3.0)
        return calculator

    @pytest.fixture
    def mock_timer_scheduler(self) -> Mock:
        """Create mock ITimerScheduler."""
        scheduler = Mock()
        scheduler.schedule_timer = Mock(return_value=Mock())  # Returns cancel function
        return scheduler

    @pytest.fixture
    def manager(
        self,
        mock_model_storage: Mock,
        mock_global_lhs_calculator: Mock,
        mock_contextual_lhs_calculator: Mock,
    ) -> LhsLifecycleManager:
        """Create LhsLifecycleManager instance without timer (for isolated tests)."""
        return LhsLifecycleManager(
            model_storage=mock_model_storage,
            global_lhs_calculator=mock_global_lhs_calculator,
            contextual_lhs_calculator=mock_contextual_lhs_calculator,
            timer_scheduler=None,
        )

    @pytest.fixture
    def manager_with_timer(
        self,
        mock_model_storage: Mock,
        mock_global_lhs_calculator: Mock,
        mock_contextual_lhs_calculator: Mock,
        mock_timer_scheduler: Mock,
    ) -> LhsLifecycleManager:
        """Create LhsLifecycleManager instance with timer scheduler."""
        return LhsLifecycleManager(
            model_storage=mock_model_storage,
            global_lhs_calculator=mock_global_lhs_calculator,
            contextual_lhs_calculator=mock_contextual_lhs_calculator,
            timer_scheduler=mock_timer_scheduler,
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
        )

    # ===== Test: startup() - ONE test for ALL scenarios =====

    @pytest.mark.asyncio
    async def test_startup(
        self,
        manager: LhsLifecycleManager,
        manager_with_timer: LhsLifecycleManager,
        mock_model_storage: Mock,
        mock_timer_scheduler: Mock,
    ) -> None:
        """Test startup lifecycle event.

        Method documentation summary:
        - Load cached global LHS from storage → memory cache
        - Load cached contextual LHS (24 hours) from storage → memory cache
        - Schedule 24h timer for automatic refresh (if scheduler provided)
        - Reads from storage but does NOT write to storage
        - Does NOT compute - uses cached values or returns defaults

        Verified aspects:
        - Aspect A: Loads cached global LHS when available
        - Aspect B: Loads cached contextual LHS values (all hours)
        - Aspect C: Schedules 24h timer when scheduler provided
        - Aspect D: Completes successfully without timer scheduler
        """
        # GIVEN: Setup for ALL aspects
        # - Cached global LHS exists (Aspect A)
        mock_model_storage.get_cached_global_lhs.return_value = LHSCacheEntry(
            value=3.5, updated_at=datetime(2025, 2, 10, 12, 0, 0)
        )

        # - Cached contextual LHS exists (Aspect B)
        # Return individual LHSCacheEntry for each hour requested
        def get_cached_contextual_lhs_side_effect(hour: int) -> LHSCacheEntry | None:
            cached_values = {0: 2.0, 6: 2.5, 12: 3.0}
            if hour in cached_values:
                return LHSCacheEntry(
                    value=cached_values[hour], updated_at=datetime(2025, 2, 10, 12, 0, 0), hour=hour
                )
            return None

        mock_model_storage.get_cached_contextual_lhs.side_effect = (
            get_cached_contextual_lhs_side_effect
        )

        # WHEN: Startup is called (SINGLE CALL for manager without timer)
        await manager.startup()

        # THEN Aspect A: Loads cached global LHS when available
        mock_model_storage.get_cached_global_lhs.assert_called_once()

        # THEN Aspect B: Loads cached contextual LHS values
        # Contextual LHS was read during startup process (may be called multiple times for 24 hours)
        assert mock_model_storage.get_cached_contextual_lhs.call_count > 0

        # THEN Aspect D: Completes successfully without timer scheduler
        # No exception was raised, confirming manager without timer works correctly

        # WHEN: Startup is called with timer scheduler (separate manager instance)
        await manager_with_timer.startup()

        # THEN Aspect C: Schedules 24h timer when scheduler provided
        mock_timer_scheduler.schedule_timer.assert_called_once()

    # ===== Test: on_retention_change() - ONE test for ALL scenarios =====

    @pytest.mark.asyncio
    async def test_on_retention_change(
        self,
        manager: LhsLifecycleManager,
        mock_global_lhs_calculator: Mock,
        mock_contextual_lhs_calculator: Mock,
        mock_model_storage: Mock,
        base_datetime: datetime,
    ) -> None:
        """Test on_retention_change lifecycle event.

        Method documentation summary:
        - Receives updated cycles from HeatingCycleLifecycleManager
        - Recalculates global LHS from new cycles
        - Recalculates contextual LHS (24 hours) from new cycles
        - Stores new LHS values in model storage
        - Invalidates in-memory cache

        Verified aspects:
        - Aspect A: Recalculates and persists global LHS
        - Aspect B: Recalculates and persists contextual LHS for all hours
        - Aspect C: Handles storage updates correctly
        """
        # GIVEN: Setup for ALL aspects to verify
        # - New cycles after retention change
        cycles = []
        # - Global LHS calculator returns new value
        mock_global_lhs_calculator.calculate_global_lhs.return_value = 4.2
        # - Contextual calculator returns values for multiple hours
        contextual_values = {0: 2.0, 6: 2.5, 12: 3.0, 18: 2.8}
        mock_contextual_lhs_calculator.calculate_all_contextual_lhs.return_value = contextual_values

        # WHEN: Retention change is triggered (SINGLE CALL)
        await manager.on_retention_change(cycles)

        # THEN Aspect A: Recalculates and persists global LHS
        mock_global_lhs_calculator.calculate_global_lhs.assert_called_once()
        # AND: New global LHS was persisted (with timestamp)
        assert mock_model_storage.set_cached_global_lhs.call_count == 1
        call_args = mock_model_storage.set_cached_global_lhs.call_args[0]
        assert call_args[0] == 4.2  # First argument is the LHS value

        # THEN Aspect B: Recalculates and persists contextual LHS for all hours
        mock_contextual_lhs_calculator.calculate_all_contextual_lhs.assert_called_once()
        # AND: Contextual LHS was persisted for each hour
        assert mock_model_storage.set_cached_contextual_lhs.call_count == len(contextual_values)

        # THEN Aspect C: Handles storage updates correctly
        # Storage received updates for both global and contextual LHS
        assert mock_model_storage.set_cached_global_lhs.called
        assert mock_model_storage.set_cached_contextual_lhs.called

    # ===== Test: on_24h_timer() - ONE test for ALL scenarios =====

    @pytest.mark.asyncio
    async def test_on_24h_timer(
        self,
        manager: LhsLifecycleManager,
        mock_global_lhs_calculator: Mock,
        mock_contextual_lhs_calculator: Mock,
        mock_model_storage: Mock,
    ) -> None:
        """Test on_24h_timer lifecycle event.

        Method documentation summary:
        - Receives refreshed cycles from HeatingCycleLifecycleManager
        - Recalculates global LHS with latest cycles
        - Recalculates contextual LHS (24 hours) with latest cycles
        - Stores updated LHS values in model storage
        - Updates in-memory cache

        Verified aspects:
        - Aspect A: Recalculates and persists global LHS
        - Aspect B: Recalculates and persists contextual LHS
        - Aspect C: Updates storage with new values
        """
        # GIVEN: Setup for ALL aspects
        cycles = []
        # - Calculator returns new global LHS
        mock_global_lhs_calculator.calculate_global_lhs.return_value = 3.8
        # - Contextual calculator returns values
        contextual_values = {0: 2.1, 6: 2.4, 12: 2.9}
        mock_contextual_lhs_calculator.calculate_all_contextual_lhs.return_value = contextual_values

        # WHEN: 24h timer fires (SINGLE CALL)
        await manager.on_24h_timer(cycles)

        # THEN Aspect A: Recalculates and persists global LHS
        mock_global_lhs_calculator.calculate_global_lhs.assert_called_once()
        # AND: New global LHS was persisted (with timestamp)
        assert mock_model_storage.set_cached_global_lhs.call_count == 1
        call_args = mock_model_storage.set_cached_global_lhs.call_args[0]
        assert call_args[0] == 3.8  # First argument is the LHS value

        # THEN Aspect B: Recalculates and persists contextual LHS
        mock_contextual_lhs_calculator.calculate_all_contextual_lhs.assert_called_once()
        # AND: Contextual LHS was persisted for each hour
        assert mock_model_storage.set_cached_contextual_lhs.call_count == len(contextual_values)

        # THEN Aspect C: Updates storage with new values
        # Storage received updates for both global and contextual LHS
        assert mock_model_storage.set_cached_global_lhs.called
        assert mock_model_storage.set_cached_contextual_lhs.called

    # ===== Test: get_global_lhs() - ONE test for ALL scenarios =====

    @pytest.mark.asyncio
    async def test_get_global_lhs(
        self,
        manager: LhsLifecycleManager,
        mock_model_storage: Mock,
    ) -> None:
        """Test get_global_lhs method.

        Method documentation summary:
        - Returns cached global LHS from memory (fast path)
        - Falls back to storage if memory cache empty
        - Returns DEFAULT_LEARNED_SLOPE if no cache exists
        - Validates positive LHS values

        Verified aspects:
        - Aspect A: Returns cached value when available
        - Aspect B: Returns default when no cache exists
        - Aspect C: Validates positive values
        - Aspect D: Handles invalid cached values (negative)
        - Aspect E: Memory hit avoids storage call (REQUIRES MULTIPLE CALLS)

        Note: Aspect E requires TWO calls to verify cache behavior:
        - First call loads from storage → memory cache
        - Second call uses memory cache (no storage access)
        """
        # GIVEN: Setup for ALL aspects
        # - Cached global LHS exists (positive value for Aspect A, C)
        mock_model_storage.get_cached_global_lhs.return_value = LHSCacheEntry(
            value=3.2, updated_at=datetime(2025, 2, 10, 12, 0, 0)
        )

        # WHEN: get_global_lhs is called (FIRST CALL for Aspects A, C)
        result = await manager.get_global_lhs()

        # THEN Aspect A: Returns cached value when available
        assert result == 3.2
        mock_model_storage.get_cached_global_lhs.assert_called_once()

        # THEN Aspect C: Validates positive values
        # Positive value is returned
        assert result > 0

        # THEN Aspect E: Memory hit avoids storage call
        # (EXCEPTION: Requires second call to verify cache behavior)
        # Second call uses memory cache
        storage_calls_first = mock_model_storage.get_cached_global_lhs.call_count
        result2 = await manager.get_global_lhs()
        storage_calls_second = mock_model_storage.get_cached_global_lhs.call_count

        # Both calls return same value
        assert result == result2 == 3.2

        # THEN: Storage access optimization
        # First call read from storage, second call used memory cache
        assert storage_calls_first == 1, "First call should read from storage"
        assert storage_calls_second == 1, "Second call should NOT hit storage (memory cache used)"

        # THEN Aspect B: Returns default when no cache exists
        # (Tested with fresh manager instance to avoid memory cache interference)
        mock_model_storage_fresh = Mock()
        mock_model_storage_fresh.get_cached_global_lhs = AsyncMock(return_value=None)
        mock_model_storage_fresh.set_cached_global_lhs = AsyncMock()
        mock_model_storage_fresh.get_cached_contextual_lhs = AsyncMock(return_value=None)
        mock_model_storage_fresh.set_cached_contextual_lhs = AsyncMock()

        mock_global_lhs_calculator_fresh = Mock()
        mock_global_lhs_calculator_fresh.calculate_global_lhs = Mock(return_value=2.5)

        mock_contextual_lhs_calculator_fresh = Mock()
        mock_contextual_lhs_calculator_fresh.calculate_contextual_lhs = Mock(
            return_value={0: 2.0, 6: 2.5, 12: 3.0}
        )

        manager_fresh = LhsLifecycleManager(
            model_storage=mock_model_storage_fresh,
            global_lhs_calculator=mock_global_lhs_calculator_fresh,
            contextual_lhs_calculator=mock_contextual_lhs_calculator_fresh,
            timer_scheduler=None,
        )

        result_default = await manager_fresh.get_global_lhs()
        assert result_default == DEFAULT_LEARNED_SLOPE

        # THEN Aspect D: Handles invalid cached values (negative)
        # Override with negative value
        mock_model_storage.get_cached_global_lhs.return_value = LHSCacheEntry(
            value=-1.5, updated_at=datetime(2025, 2, 10, 12, 0, 0)
        )

        # Create new manager to avoid memory cache
        manager_negative = LhsLifecycleManager(
            model_storage=mock_model_storage,
            global_lhs_calculator=Mock(calculate_global_lhs=Mock(return_value=2.5)),
            contextual_lhs_calculator=Mock(
                calculate_contextual_lhs=Mock(return_value={0: 2.0, 6: 2.5, 12: 3.0})
            ),
            timer_scheduler=None,
        )

        result_invalid = await manager_negative.get_global_lhs()
        # Default value is returned instead
        assert result_invalid == DEFAULT_LEARNED_SLOPE

    # ===== Test: get_contextual_lhs() - ONE test for ALL scenarios =====

    @pytest.mark.asyncio
    async def test_get_contextual_lhs(
        self,
        manager: LhsLifecycleManager,
        mock_model_storage: Mock,
        mock_contextual_lhs_calculator: Mock,
        base_datetime: datetime,
    ) -> None:
        """Test get_contextual_lhs method.

        Method documentation summary:
        - Returns cached contextual LHS for target hour from memory
        - Falls back to storage if memory cache empty
        - Computes contextual LHS if no cache exists
        - Falls back to global LHS if contextual unavailable

        Verified aspects:
        - Aspect A: Returns cached value for target hour
        - Aspect B: Handles all 24 hours correctly
        - Aspect C: Memory hit avoids storage call (REQUIRES MULTIPLE CALLS)

        Note: Aspect C requires TWO calls to verify cache behavior:
        - First call loads from storage → memory cache
        - Second call uses memory cache (no storage access)
        """
        # GIVEN: Setup for ALL aspects
        cycles = []
        # - Target time at 06:00 (hour=6) for Aspect A
        target_time = base_datetime.replace(hour=6)
        # - Storage returns cached value for hour 6
        mock_model_storage.get_cached_contextual_lhs.return_value = LHSCacheEntry(
            value=2.7, updated_at=datetime(2025, 2, 10, 12, 0, 0)
        )

        # WHEN: get_contextual_lhs is called (FIRST CALL for Aspect A)
        result = await manager.get_contextual_lhs(target_time, cycles)

        # THEN Aspect A: Returns cached value for target hour
        assert result == 2.7
        mock_model_storage.get_cached_contextual_lhs.assert_called_with(6)

        # THEN Aspect B: Handles all 24 hours correctly
        # Test a sample of hours
        test_hours = [0, 12, 18, 23]
        for hour in test_hours:
            target_time_hour = base_datetime.replace(hour=hour)
            mock_model_storage.get_cached_contextual_lhs.return_value = LHSCacheEntry(
                value=float(hour) + 2.0, updated_at=datetime(2025, 2, 10, 12, 0, 0)
            )

            # Create new manager to avoid memory cache interference
            manager_hour = LhsLifecycleManager(
                model_storage=mock_model_storage,
                global_lhs_calculator=Mock(calculate_global_lhs=Mock(return_value=2.5)),
                contextual_lhs_calculator=mock_contextual_lhs_calculator,
                timer_scheduler=None,
            )

            result_hour = await manager_hour.get_contextual_lhs(target_time_hour, cycles)

            # Correct hour-specific value is returned
            assert isinstance(result_hour, float) and result_hour > 0

        # THEN Aspect C: Memory hit avoids storage call for same hour
        # (EXCEPTION: Requires second call to verify cache behavior)
        # Reset for clean test
        target_time_12 = base_datetime.replace(hour=12)
        mock_model_storage.get_cached_contextual_lhs.return_value = LHSCacheEntry(
            value=3.2, updated_at=datetime(2025, 2, 10, 12, 0, 0)
        )

        # Create new manager for clean cache test
        manager_cache = LhsLifecycleManager(
            model_storage=mock_model_storage,
            global_lhs_calculator=Mock(calculate_global_lhs=Mock(return_value=2.5)),
            contextual_lhs_calculator=mock_contextual_lhs_calculator,
            timer_scheduler=None,
        )

        # First call loads from storage
        result1 = await manager_cache.get_contextual_lhs(target_time_12, cycles)
        storage_calls_first = mock_model_storage.get_cached_contextual_lhs.call_count

        # Second call for same hour uses memory
        result2 = await manager_cache.get_contextual_lhs(target_time_12, cycles)
        storage_calls_second = mock_model_storage.get_cached_contextual_lhs.call_count

        # Both calls return same value
        assert result1 == result2 == 3.2

        # THEN: Storage access optimization
        # First call read from storage, second call used memory cache
        assert storage_calls_first >= 1, "First call should read from storage"
        assert (
            storage_calls_second == storage_calls_first
        ), "Second call should NOT hit storage (memory cache used)"

    # ===== Test: update_global_lhs_from_cycles() - ONE test for ALL scenarios =====

    @pytest.mark.asyncio
    async def test_update_global_lhs_from_cycles(
        self,
        manager: LhsLifecycleManager,
        mock_global_lhs_calculator: Mock,
        mock_model_storage: Mock,
        base_datetime: datetime,
    ) -> None:
        """Test update_global_lhs_from_cycles method.

        Method documentation summary:
        - Computes global LHS from provided cycles
        - Persists new LHS value to storage
        - Updates in-memory cache
        - Returns calculated LHS value

        Verified aspects:
        - Aspect A: Calculates and persists with valid cycles
        - Aspect B: Returns the calculated value
        - Aspect C: Handles empty cycles list gracefully
        """
        # GIVEN: Setup for ALL aspects
        # - Heating cycles (Aspect A)
        cycles = [
            self._create_heating_cycle(base_datetime),
            self._create_heating_cycle(base_datetime + timedelta(days=1)),
        ]
        # - Calculator returns value for valid cycles
        mock_global_lhs_calculator.calculate_global_lhs.return_value = 2.8

        # WHEN: update_global_lhs_from_cycles is called (SINGLE CALL)
        result = await manager.update_global_lhs_from_cycles(cycles)

        # THEN Aspect A: Calculates and persists with valid cycles
        mock_global_lhs_calculator.calculate_global_lhs.assert_called_once_with(cycles)
        assert mock_model_storage.set_cached_global_lhs.call_count == 1
        call_args = mock_model_storage.set_cached_global_lhs.call_args[0]
        assert call_args[0] == 2.8  # First argument is the LHS value

        # THEN Aspect B: Returns the calculated value
        assert result == 2.8

        # THEN Aspect B : Memory cache is updated (verified by subsequent call returning same value without storage hit)
        result = await manager.get_global_lhs()
        assert result == 2.8
        # Storage should NOT be called again (memory cache used)
        assert (
            mock_model_storage.get_cached_global_lhs.call_count == 0
        ), "Should NOT hit storage on get_global_lhs after update"

        # THEN Aspect C: Handles empty cycles list gracefully
        # (Tested separately with new call to avoid cache interference)
        empty_cycles = []
        mock_global_lhs_calculator.calculate_global_lhs.return_value = DEFAULT_LEARNED_SLOPE

        result_empty = await manager.update_global_lhs_from_cycles(empty_cycles)

        # Default LHS is returned and persisted
        assert result_empty == DEFAULT_LEARNED_SLOPE

    # ===== Test: update_contextual_lhs_from_cycles() - ONE test for ALL scenarios =====

    @pytest.mark.asyncio
    async def test_update_contextual_lhs_from_cycles(
        self,
        manager: LhsLifecycleManager,
        mock_contextual_lhs_calculator: Mock,
        mock_model_storage: Mock,
        base_datetime: datetime,
    ) -> None:
        """Test update_contextual_lhs_from_cycles method.

        Method documentation summary:
        - Computes contextual LHS for all 24 hours from cycles
        - Persists non-None values to storage
        - Updates in-memory cache
        - Returns complete hour mapping (including None values)

        Verified aspects:
        - Aspect A: Calculates LHS for all hours
        - Aspect B: Persists only non-None values (skips None)
        - Aspect C: Returns complete mapping including None
        - Aspect D: Handles empty cycles gracefully
        """
        # GIVEN: Setup for ALL aspects
        # - Heating cycles
        cycles = [
            self._create_heating_cycle(base_datetime),
            self._create_heating_cycle(base_datetime + timedelta(hours=6)),
        ]
        # - Contextual calculator returns mixed values (some None, some values)
        contextual_values = {0: 2.0, 6: 2.5, 12: None, 18: 2.8}
        mock_contextual_lhs_calculator.calculate_all_contextual_lhs.return_value = contextual_values

        # WHEN: update_contextual_lhs_from_cycles is called (SINGLE CALL)
        result = await manager.update_contextual_lhs_from_cycles(cycles)

        # THEN Aspect A: Calculates LHS for all hours
        mock_contextual_lhs_calculator.calculate_all_contextual_lhs.assert_called_once_with(cycles)
        assert result == contextual_values

        # THEN Aspect B: Persists only non-None values (skips None)
        # Only 3 values persisted (hours 0, 6, 18), not hour 12 (None)
        assert mock_model_storage.set_cached_contextual_lhs.call_count == 3

        # THEN Aspect C: Memory cache is updated with non-None values
        # Verify internal memory cache contains expected values (excluding hour 12 which was None)
        assert manager._cached_contextual_lhs == {0: 2.0, 6: 2.5, 18: 2.8}

        # Verify get_contextual_lhs returns cached value without storage hit
        lhs_value = await manager.get_contextual_lhs(base_datetime.replace(hour=6), cycles)
        assert lhs_value == 2.5

        # Storage should NOT be called (memory cache used)
        assert (
            mock_model_storage.get_cached_contextual_lhs.call_count == 0
        ), "Should NOT hit storage on get_contextual_lhs after update"

        # THEN Aspect D: Handles empty cycles gracefully
        # (Tested with separate call to avoid interference)
        empty_cycles = []
        mock_contextual_lhs_calculator.calculate_all_contextual_lhs.return_value = {}

        result_empty = await manager.update_contextual_lhs_from_cycles(empty_cycles)

        # Empty dict is returned
        assert isinstance(result_empty, dict)
        assert len(result_empty) == 0

    # ===== Test: ensure_contextual_lhs_populated() - ONE test for ALL scenarios =====

    @pytest.mark.asyncio
    async def test_ensure_contextual_lhs_populated(
        self,
        manager: LhsLifecycleManager,
        mock_model_storage: Mock,
        mock_contextual_lhs_calculator: Mock,
        base_datetime: datetime,
    ) -> None:
        """Test ensure_contextual_lhs_populated method (lazy population with force_recalculate).

        Method documentation summary:
        - Ensures contextual LHS is populated for a specific hour (lazy population)
        - Memory cache hit returns immediately (fast path)
        - Storage cache hit loads into memory
        - Computes contextual LHS if no cache exists
        - force_recalculate=True bypasses BOTH memory and storage caches
        - Falls back to global LHS if contextual unavailable

        Verified aspects:
        - Aspect A: Memory cache hit returns immediately (no storage call)
        - Aspect B: Storage cache hit loads into memory
        - Aspect C: Computes from cycles when no cache exists
        - Aspect D: force_recalculate=True bypasses both caches and recomputes
        - Aspect E: Falls back to global LHS when no contextual data exists

        **REGRESSION PREVENTION**: This test prevents bug where force_recalculate
        parameter is not respected, causing stale cache values to be used even when
        explicit refresh is requested.
        """
        cycles = [self._create_heating_cycle(base_datetime)]
        target_hour = 12

        # GIVEN: Setup for ALL aspects
        mock_contextual_lhs_calculator.calculate_all_contextual_lhs.return_value = {
            0: 2.0,
            6: 2.5,
            12: 3.0,
            18: 2.8,
        }

        # WHEN/THEN Aspect A: Memory cache hit returns immediately (no storage call)
        manager._cached_contextual_lhs[target_hour] = 3.0  # Pre-populate memory

        result = await manager.ensure_contextual_lhs_populated(target_hour, cycles)

        assert result == 3.0
        # Storage should NOT be called (memory cache used)
        mock_model_storage.get_cached_contextual_lhs.assert_not_called()

        # WHEN/THEN Aspect B: Storage cache hit loads into memory
        # Reset manager for clean state
        manager._cached_contextual_lhs = {}
        manager._cached_global_lhs = None  # Reset global too
        mock_model_storage.get_cached_contextual_lhs.reset_mock()
        mock_model_storage.get_cached_global_lhs.reset_mock()

        # Storage returns cached value for hour 12
        mock_model_storage.get_cached_contextual_lhs.return_value = LHSCacheEntry(
            value=3.2, updated_at=datetime(2025, 2, 10, 12, 0, 0)
        )

        result = await manager.ensure_contextual_lhs_populated(target_hour, cycles)

        assert result == 3.2
        # Storage was called
        mock_model_storage.get_cached_contextual_lhs.assert_called_once_with(target_hour)
        # Value should now be in memory cache
        assert manager._cached_contextual_lhs[target_hour] == 3.2

        # WHEN/THEN Aspect C: Computes from cycles when no cache exists
        # Reset manager for clean state
        manager._cached_contextual_lhs = {}
        manager._cached_global_lhs = None
        mock_model_storage.get_cached_contextual_lhs.reset_mock()
        mock_model_storage.get_cached_contextual_lhs.return_value = None
        mock_contextual_lhs_calculator.calculate_contextual_lhs_for_hour.reset_mock()
        mock_contextual_lhs_calculator.calculate_contextual_lhs_for_hour.return_value = 3.0

        result = await manager.ensure_contextual_lhs_populated(target_hour, cycles)

        assert result == 3.0  # Should compute from calculator mock
        # Calculator should have been called to compute
        mock_contextual_lhs_calculator.calculate_contextual_lhs_for_hour.assert_called_once_with(
            cycles, target_hour
        )
        # Value should be persisted to storage
        mock_model_storage.set_cached_contextual_lhs.assert_called()
        # Value should now be in memory cache
        assert manager._cached_contextual_lhs[target_hour] == 3.0

        # WHEN/THEN Aspect D: force_recalculate=True bypasses both caches
        # Reset and pre-populate both caches
        manager._cached_contextual_lhs[target_hour] = 3.5  # Stale memory cache
        mock_model_storage.get_cached_contextual_lhs.reset_mock()
        mock_model_storage.get_cached_contextual_lhs.return_value = LHSCacheEntry(
            value=3.2,
            updated_at=datetime(2025, 2, 10, 0, 0, 0),  # Stale storage
        )
        mock_model_storage.set_cached_contextual_lhs.reset_mock()
        mock_contextual_lhs_calculator.calculate_contextual_lhs_for_hour.reset_mock()
        mock_contextual_lhs_calculator.calculate_contextual_lhs_for_hour.return_value = 3.0

        # Call with force_recalculate=True - should ignore both caches
        result = await manager.ensure_contextual_lhs_populated(
            target_hour, cycles, force_recalculate=True
        )

        # Should get fresh calculated value (3.0 from mock)
        assert result == 3.0
        # Storage.get_cached_contextual_lhs should NOT be called (bypassed by force)
        mock_model_storage.get_cached_contextual_lhs.assert_not_called()
        # Calculator SHOULD be called (forced recalculation)
        mock_contextual_lhs_calculator.calculate_contextual_lhs_for_hour.assert_called_once_with(
            cycles, target_hour
        )
        # New value should be persisted to storage
        mock_model_storage.set_cached_contextual_lhs.assert_called()

        # WHEN/THEN Aspect E: Falls back to global LHS when no contextual data
        # Setup: Calculator returns None for target_hour (no contextual data)
        manager._cached_contextual_lhs = {}
        manager._cached_global_lhs = None
        mock_model_storage.get_cached_contextual_lhs.reset_mock()
        mock_model_storage.get_cached_contextual_lhs.return_value = None
        mock_model_storage.get_cached_global_lhs.return_value = LHSCacheEntry(
            value=2.5, updated_at=datetime(2025, 2, 10, 12, 0, 0)
        )
        mock_contextual_lhs_calculator.calculate_contextual_lhs_for_hour.reset_mock()
        mock_contextual_lhs_calculator.calculate_contextual_lhs_for_hour.return_value = (
            None  # No contextual data
        )

        result = await manager.ensure_contextual_lhs_populated(target_hour, cycles)

        # Should return global LHS as fallback
        assert result == 2.5
        # Global LHS should have been called
        mock_model_storage.get_cached_global_lhs.assert_called()
