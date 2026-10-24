"""Extension tests for HALhsStorage dead time learning functionality.

Tests for new methods:
- get_learned_dead_time()
- set_learned_dead_time()

These tests are RED phase tests (should FAIL with current code).
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

# Conditional import handling
try:
    from custom_components.intelligent_heating_pilot.infrastructure.adapters.lhs_storage import (
        HALhsStorage,
    )

    LHS_STORAGE_AVAILABLE = True
except ImportError:
    LHS_STORAGE_AVAILABLE = False
    HALhsStorage = None  # type: ignore


def _get_storage_patch_path() -> str:
    """Helper to get the correct patch path for storage module."""
    return (
        "custom_components.intelligent_heating_pilot.infrastructure.adapters.base_ha_storage.Store"
    )


pytestmark = pytest.mark.skipif(
    not LHS_STORAGE_AVAILABLE,
    reason="HALhsStorage not yet available",
)


@pytest.fixture
def mock_hass() -> Mock:
    """Create a mock Home Assistant instance."""
    return Mock()


@pytest.fixture
def entry_id() -> str:
    """Create a test entry ID."""
    return "test_entry_dead_time"


@pytest.fixture
def mock_store() -> Mock:
    """Create a mock Store."""
    store_mock = Mock()
    store_mock.async_load = AsyncMock(return_value=None)
    store_mock.async_save = AsyncMock()
    return store_mock


@pytest.fixture
async def storage(mock_hass: Mock, entry_id: str, mock_store: Mock) -> HALhsStorage:
    """Create storage adapter with mocked dependencies."""
    patch_path = _get_storage_patch_path()

    with patch(patch_path, return_value=mock_store):
        storage_obj = HALhsStorage(mock_hass, entry_id)
        await storage_obj._ensure_loaded()
        return storage_obj


class TestHALhsStorageDeadTimeStorage:
    """Test suite for dead time persistence in HALhsStorage.

    These tests verify that learned dead time values can be stored,
    retrieved, and persist across Home Assistant restarts.
    """

    @pytest.mark.asyncio
    async def test_get_learned_dead_time_returns_none_initially(
        self, storage: HALhsStorage
    ) -> None:
        """Test that get_learned_dead_time returns None when no value is set.

        RED: This test FAILS because method doesn't exist yet.
        """
        result = await storage.get_learned_dead_time()
        assert result is None

    @pytest.mark.asyncio
    async def test_set_learned_dead_time_persists_value(
        self, storage: HALhsStorage, mock_store: Mock
    ) -> None:
        """Test that set_learned_dead_time stores and retrieves a value.

        RED: This test FAILS because method doesn't exist yet.
        """
        # Set a dead time value
        await storage.set_learned_dead_time(10.5)

        # Verify it was persisted
        result = await storage.get_learned_dead_time()
        assert result == pytest.approx(10.5)

        # Verify store was called to persist
        mock_store.async_save.assert_called()

    @pytest.mark.asyncio
    async def test_set_learned_dead_time_zero_value(self, storage: HALhsStorage) -> None:
        """Test that set_learned_dead_time handles zero correctly."""
        await storage.set_learned_dead_time(0.0)
        result = await storage.get_learned_dead_time()
        assert result == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_set_learned_dead_time_fractional_value(self, storage: HALhsStorage) -> None:
        """Test that set_learned_dead_time preserves decimal precision."""
        await storage.set_learned_dead_time(7.333)
        result = await storage.get_learned_dead_time()
        assert result == pytest.approx(7.333, abs=0.001)

    @pytest.mark.asyncio
    async def test_set_learned_dead_time_none_clears_value(
        self, storage: HALhsStorage, mock_store: Mock
    ) -> None:
        """Test that setting None clears the learned dead_time value.

        RED: This test FAILS because method doesn't exist yet.
        """
        # First set a value
        await storage.set_learned_dead_time(8.5)
        assert await storage.get_learned_dead_time() == pytest.approx(8.5)

        # Then clear it
        await storage.set_learned_dead_time(None)
        result = await storage.get_learned_dead_time()
        assert result is None

    @pytest.mark.asyncio
    async def test_learned_dead_time_persists_across_restart(
        self, mock_hass: Mock, entry_id: str, mock_store: Mock
    ) -> None:
        """Test that learned dead_time survives simulated Home Assistant restart.

        Simulates persistence by:
        1. Set value and persist
        2. Simulate restart by creating new storage instance
        3. Verify value is still available

        RED: This test FAILS because reload/persistence isn't implemented.
        """
        patch_path = _get_storage_patch_path()

        # Simulate initial load with stored data (dict format used by set_learned_dead_time)
        mock_store.async_load = AsyncMock(
            return_value={
                "learned_dead_time": {
                    "value": 6.5,
                    "updated_at": "2025-01-01T00:00:00",
                }
            }
        )

        with patch(patch_path, return_value=mock_store):
            # Create storage and verify persistence
            storage1 = HALhsStorage(mock_hass, entry_id)
            await storage1._ensure_loaded()

            result = await storage1.get_learned_dead_time()
            assert result == pytest.approx(6.5)

    @pytest.mark.asyncio
    async def test_multiple_set_calls_update_value(
        self, storage: HALhsStorage, mock_store: Mock
    ) -> None:
        """Test that multiple set calls update the value correctly.

        RED: This test FAILS if update logic isn't properly implemented.
        """
        # Set initial value
        await storage.set_learned_dead_time(5.0)
        assert await storage.get_learned_dead_time() == pytest.approx(5.0)

        # Update to new value
        await storage.set_learned_dead_time(7.5)
        assert await storage.get_learned_dead_time() == pytest.approx(7.5)

        # Update again
        await storage.set_learned_dead_time(6.0)
        assert await storage.get_learned_dead_time() == pytest.approx(6.0)

    @pytest.mark.asyncio
    async def test_large_dead_time_value(self, storage: HALhsStorage) -> None:
        """Test that large dead_time values are handled correctly."""
        big_value = 1500.75
        await storage.set_learned_dead_time(big_value)
        result = await storage.get_learned_dead_time()
        assert result == pytest.approx(big_value)

    @pytest.mark.asyncio
    async def test_very_small_dead_time_value(self, storage: HALhsStorage) -> None:
        """Test that very small dead_time values are preserved."""
        small_value = 0.001
        await storage.set_learned_dead_time(small_value)
        result = await storage.get_learned_dead_time()
        assert result == pytest.approx(small_value, abs=0.0001)
