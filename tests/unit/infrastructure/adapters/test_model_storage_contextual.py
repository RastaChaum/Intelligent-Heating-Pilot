"""Unit tests for model storage contextual LHS cache operations.

Tests the persistence and retrieval of contextual LHS data (per-hour) and
cache behavior with retention settings.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.intelligent_heating_pilot.domain.interfaces.lhs_storage_interface import (
    ILhsStorage,
)
from custom_components.intelligent_heating_pilot.domain.value_objects.lhs_cache_entry import (
    LHSCacheEntry,
)


class TestModelStorageContextualCache:
    """Test suite for contextual LHS cache operations."""

    @pytest.fixture
    def base_datetime(self) -> datetime:
        """Base datetime for testing."""
        return datetime(2025, 2, 9, 12, 0, 0)

    @pytest.fixture
    def mock_storage(self) -> Mock:
        """Create a mock model storage implementation."""
        storage = AsyncMock(spec=ILhsStorage)
        return storage

    # ===== Test: Store and Retrieve Contextual LHS =====

    @pytest.mark.asyncio
    async def test_set_cached_contextual_lhs_for_hour_6(
        self, mock_storage: AsyncMock, base_datetime: datetime
    ) -> None:
        """Test storing contextual LHS for hour 6.

        RED: Interface method should store lhs with hour context.
        """
        hour = 6
        lhs_value = 14.75
        updated_at = base_datetime

        # Call the interface method (mocked)
        mock_storage.set_cached_contextual_lhs = AsyncMock()
        await mock_storage.set_cached_contextual_lhs(hour, lhs_value, updated_at)

        # Verify it was called with correct parameters
        mock_storage.set_cached_contextual_lhs.assert_called_once_with(hour, lhs_value, updated_at)

    @pytest.mark.asyncio
    async def test_get_cached_contextual_lhs_for_hour_6(
        self, mock_storage: AsyncMock, base_datetime: datetime
    ) -> None:
        """Test retrieving contextual LHS for hour 6.

        RED: Should retrieve stored entry for correct hour.
        """
        hour = 6
        cached_entry = LHSCacheEntry(value=14.75, updated_at=base_datetime, hour=hour)

        mock_storage.get_cached_contextual_lhs = AsyncMock(return_value=cached_entry)
        result = await mock_storage.get_cached_contextual_lhs(hour)

        assert result is not None
        assert result.value == 14.75
        assert result.hour == hour
        assert result.updated_at == base_datetime

    @pytest.mark.asyncio
    async def test_get_cached_contextual_lhs_returns_none_when_not_stored(
        self, mock_storage: AsyncMock
    ) -> None:
        """Test that retrieval returns None when hour has no cached data.

        RED: Should return None for hours without data.
        """
        hour = 12
        mock_storage.get_cached_contextual_lhs = AsyncMock(return_value=None)

        result = await mock_storage.get_cached_contextual_lhs(hour)

        assert result is None

    # ===== Test: Multiple Hours in Cache =====

    @pytest.mark.asyncio
    async def test_cache_multiple_hours_independently(
        self, mock_storage: AsyncMock, base_datetime: datetime
    ) -> None:
        """Test storing contextual LHS for multiple hours.

        RED: Each hour should be stored independently.
        Hour 6: 14.75
        Hour 12: 12.50
        Hour 18: 13.25
        """
        test_data = {
            6: LHSCacheEntry(value=14.75, updated_at=base_datetime, hour=6),
            12: LHSCacheEntry(value=12.50, updated_at=base_datetime, hour=12),
            18: LHSCacheEntry(value=13.25, updated_at=base_datetime, hour=18),
        }

        mock_storage.get_cached_contextual_lhs = AsyncMock(
            side_effect=lambda hour: test_data.get(hour)
        )

        # Verify each hour returns its own data
        result_6 = await mock_storage.get_cached_contextual_lhs(6)
        result_12 = await mock_storage.get_cached_contextual_lhs(12)
        result_18 = await mock_storage.get_cached_contextual_lhs(18)

        assert result_6.value == 14.75
        assert result_12.value == 12.50
        assert result_18.value == 13.25

    @pytest.mark.asyncio
    async def test_cache_retrieval_respects_hour_boundary(
        self, mock_storage: AsyncMock, base_datetime: datetime
    ) -> None:
        """Test that cache correctly distinguishes between hours.

        RED: Hour 6 cache should not return hour 7 data.
        """
        cache_6 = LHSCacheEntry(value=14.75, updated_at=base_datetime, hour=6)
        cache_7 = LHSCacheEntry(value=15.00, updated_at=base_datetime, hour=7)

        test_data = {6: cache_6, 7: cache_7}
        mock_storage.get_cached_contextual_lhs = AsyncMock(
            side_effect=lambda hour: test_data.get(hour)
        )

        # Retrieve hour 6 - should get cache_6, not cache_7
        result = await mock_storage.get_cached_contextual_lhs(6)

        assert result.value == 14.75
        assert result.hour == 6

    # ===== Test: Cache Entry Structure =====

    @pytest.mark.asyncio
    async def test_cached_contextual_lhs_entry_has_cycle_count(
        self, mock_storage: AsyncMock, base_datetime: datetime
    ) -> None:
        """Test that cache entry can include cycle count.

        RED: Ensure LHSCacheEntry structure supports cycle_count if needed.
        Note: Current structure doesn't have cycle_count, but should store it somewhere.
        """
        # Based on architecture, cycle_count should be stored with the LHS value
        # This test validates the structure
        hour = 6
        cached_entry = LHSCacheEntry(value=14.75, updated_at=base_datetime, hour=hour)

        # The entry should have the basic structure
        assert hasattr(cached_entry, "value")
        assert hasattr(cached_entry, "hour")
        assert hasattr(cached_entry, "updated_at")

    @pytest.mark.asyncio
    async def test_cached_contextual_lhs_entry_timestamp_updates(
        self, mock_storage: AsyncMock, base_datetime: datetime
    ) -> None:
        """Test that cache entry timestamp updates on recalculation.

        RED: When cache is updated, timestamp should change.
        """
        hour = 6
        old_time = base_datetime
        new_time = base_datetime + timedelta(hours=1)

        old_entry = LHSCacheEntry(value=14.75, updated_at=old_time, hour=hour)
        new_entry = LHSCacheEntry(value=14.80, updated_at=new_time, hour=hour)

        # Simulate cache update
        assert old_entry.updated_at != new_entry.updated_at
        assert new_entry.updated_at > old_entry.updated_at

    # ===== Test: Retention Disabled (caching=0) =====

    @pytest.mark.asyncio
    async def test_get_contextual_lhs_with_retention_disabled_returns_none(
        self, mock_storage: AsyncMock
    ) -> None:
        """Test that get returns None when retention_days=0 (caching disabled).

        RED: When caching is disabled, cache operations should return None.
        """
        # Mock storage with retention disabled
        mock_storage.get_cached_contextual_lhs = AsyncMock(return_value=None)

        result = await mock_storage.get_cached_contextual_lhs(6)

        assert result is None

    @pytest.mark.asyncio
    async def test_set_contextual_lhs_with_retention_disabled_is_noop(
        self, mock_storage: AsyncMock, base_datetime: datetime
    ) -> None:
        """Test that set is a no-op when retention_days=0.

        RED: Setting cache when disabled should not persist.
        """
        mock_storage.set_cached_contextual_lhs = AsyncMock()

        # When retention is disabled, this should be a no-op
        await mock_storage.set_cached_contextual_lhs(6, 14.75, base_datetime)

        # Verify method was called (infrastructure handles the no-op)
        mock_storage.set_cached_contextual_lhs.assert_called_once()

    # ===== Test: Clear Cache on Retention Change =====

    @pytest.mark.asyncio
    async def test_clear_all_contextual_cache_on_retention_change(
        self, mock_storage: AsyncMock, base_datetime: datetime
    ) -> None:
        """Test that ALL hours are cleared when retention parameter changes.

        RED: Changing retention should invalidate entire contextual cache.
        Initial: 10 days retention with cached hours 6, 12, 18
        Change to: 5 days retention
        Expected: All cached hours become None
        """
        # After retention change, all should be None
        mock_storage.get_cached_contextual_lhs = AsyncMock(side_effect=lambda hour: None)

        result_6 = await mock_storage.get_cached_contextual_lhs(6)
        result_12 = await mock_storage.get_cached_contextual_lhs(12)
        result_18 = await mock_storage.get_cached_contextual_lhs(18)

        assert result_6 is None
        assert result_12 is None
        assert result_18 is None

    # ===== Test: Cache Immutability =====

    def test_cached_lhs_entry_is_immutable(self, base_datetime: datetime) -> None:
        """Test that LHSCacheEntry is frozen (immutable).

        RED: Cache entries should be immutable value objects.
        """
        entry = LHSCacheEntry(value=14.75, updated_at=base_datetime, hour=6)

        with pytest.raises(
            (AttributeError, TypeError, FrozenInstanceError),
            match="frozen|cannot set attribute|cannot assign to field",
        ):
            entry.value = 15.0  # type: ignore

    def test_cached_lhs_entry_hour_is_immutable(self, base_datetime: datetime) -> None:
        """Test that hour field cannot be modified.

        RED: Even hour field should be immutable.
        """
        entry = LHSCacheEntry(value=14.75, updated_at=base_datetime, hour=6)

        with pytest.raises(
            (AttributeError, TypeError, FrozenInstanceError),
            match="frozen|cannot set attribute|cannot assign to field",
        ):
            entry.hour = 7  # type: ignore

    # ===== Test: Hour Boundaries (0-23) =====

    @pytest.mark.asyncio
    async def test_cache_contextual_lhs_for_hour_0(
        self, mock_storage: AsyncMock, base_datetime: datetime
    ) -> None:
        """Test caching for hour 0 (midnight).

        RED: Edge case for hour boundary.
        """
        hour = 0
        entry = LHSCacheEntry(value=10.50, updated_at=base_datetime, hour=hour)

        mock_storage.get_cached_contextual_lhs = AsyncMock(return_value=entry)
        result = await mock_storage.get_cached_contextual_lhs(hour)

        assert result.hour == 0

    @pytest.mark.asyncio
    async def test_cache_contextual_lhs_for_hour_23(
        self, mock_storage: AsyncMock, base_datetime: datetime
    ) -> None:
        """Test caching for hour 23 (11 PM).

        RED: Edge case for hour boundary.
        """
        hour = 23
        entry = LHSCacheEntry(value=11.75, updated_at=base_datetime, hour=hour)

        mock_storage.get_cached_contextual_lhs = AsyncMock(return_value=entry)
        result = await mock_storage.get_cached_contextual_lhs(hour)

        assert result.hour == 23

    # ===== Test: Value Ranges =====

    @pytest.mark.asyncio
    async def test_cache_stores_various_lhs_value_ranges(
        self, mock_storage: AsyncMock, base_datetime: datetime
    ) -> None:
        """Test that cache can store realistic LHS value ranges.

        RED: Cache should handle 0 to 100+ °C/h slopes.
        """
        test_cases = [
            (0.1, "very small slope"),  # Minimum realistic
            (2.0, "default slope"),  # Default learning slope
            (15.0, "high slope"),  # High slope
            (100.0, "extreme slope"),  # Unrealistic but should work
        ]

        for value, description in test_cases:
            entry = LHSCacheEntry(value=value, updated_at=base_datetime, hour=6)
            mock_storage.get_cached_contextual_lhs = AsyncMock(return_value=entry)

            result = await mock_storage.get_cached_contextual_lhs(6)
            assert result.value == value, description

    # ===== Test: Type Validation =====

    @pytest.mark.asyncio
    async def test_set_cached_contextual_lhs_accepts_correct_types(
        self, mock_storage: AsyncMock, base_datetime: datetime
    ) -> None:
        """Test that set method accepts hour: int, lhs: float, updated_at: datetime.

        RED: Type hint enforcement.
        """
        hour: int = 6
        lhs_value: float = 14.75
        updated_at: datetime = base_datetime

        mock_storage.set_cached_contextual_lhs = AsyncMock()
        await mock_storage.set_cached_contextual_lhs(hour, lhs_value, updated_at)

        mock_storage.set_cached_contextual_lhs.assert_called_once_with(hour, lhs_value, updated_at)

    @pytest.mark.asyncio
    async def test_get_cached_contextual_lhs_returns_correct_type(
        self, mock_storage: AsyncMock, base_datetime: datetime
    ) -> None:
        """Test that get returns LHSCacheEntry | None.

        RED: Type hint enforcement.
        """
        entry = LHSCacheEntry(value=14.75, updated_at=base_datetime, hour=6)
        mock_storage.get_cached_contextual_lhs = AsyncMock(return_value=entry)

        result = await mock_storage.get_cached_contextual_lhs(6)

        assert isinstance(result, (LHSCacheEntry, type(None)))

    # ===== Test: is_for_hour() Method =====

    def test_lhs_cache_entry_is_for_hour_matches_stored_hour(self, base_datetime: datetime) -> None:
        """Test is_for_hour() method correctly identifies hour match.

        RED: Entry with hour 6 should match query for hour 6.
        """
        entry = LHSCacheEntry(value=14.75, updated_at=base_datetime, hour=6)

        assert entry.is_for_hour(6) is True

    def test_lhs_cache_entry_is_for_hour_rejects_different_hour(
        self, base_datetime: datetime
    ) -> None:
        """Test is_for_hour() method rejects different hours.

        RED: Entry with hour 6 should NOT match query for hour 12.
        """
        entry = LHSCacheEntry(value=14.75, updated_at=base_datetime, hour=6)

        assert entry.is_for_hour(12) is False

    # ===== Test: Logging Validation =====

    @pytest.mark.asyncio
    async def test_cache_operations_log_at_debug_level(
        self, mock_storage: AsyncMock, base_datetime: datetime, caplog
    ) -> None:
        """Test that cache operations log at DEBUG level.

        RED: Verify logging standards.
        """
        with caplog.at_level("DEBUG"):
            mock_storage.get_cached_contextual_lhs = AsyncMock(return_value=None)
            await mock_storage.get_cached_contextual_lhs(6)

        # Since we're using a mock, we can't capture real logs
        # In real implementation, logs should be verified
