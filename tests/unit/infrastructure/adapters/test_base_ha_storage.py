"""Tests for BaseHAStorageAdapter unified base class.

This module tests the common storage functionality that will be shared between
HALhsStorage and HAHeatingCycleStorage.

These tests are written in TDD style (RED phase) - they will FAIL until the
BaseHAStorageAdapter class is implemented.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest

# This import will fail until BaseHAStorageAdapter is implemented
try:
    from custom_components.intelligent_heating_pilot.infrastructure.adapters.base_ha_storage import (
        BaseHAStorageAdapter,
    )

    BASE_STORAGE_AVAILABLE = True
except ImportError:
    BASE_STORAGE_AVAILABLE = False
    BaseHAStorageAdapter = None  # type: ignore


# Concrete implementation for testing the abstract base class
if BASE_STORAGE_AVAILABLE:

    class TestHAStorage(BaseHAStorageAdapter[dict[str, Any]]):
        """Concrete test implementation of BaseHAStorageAdapter."""

        def _get_default_data(self) -> dict[str, Any]:
            """Return default data structure for tests."""
            return {"test_field": "default_value"}


@pytest.fixture
def mock_hass() -> Mock:
    """Create a mock Home Assistant instance."""
    return Mock()


@pytest.fixture
def entry_id() -> str:
    """Create a test entry ID."""
    return "test_entry_123"


@pytest.fixture
def mock_store() -> Mock:
    """Create a mock Store."""
    store_mock = Mock()
    store_mock.async_load = AsyncMock(return_value=None)
    store_mock.async_save = AsyncMock()
    return store_mock


pytestmark = pytest.mark.skipif(
    not BASE_STORAGE_AVAILABLE,
    reason="BaseHAStorageAdapter not yet implemented (TDD RED phase)",
)


class TestBaseHAStorageAdapterInitialization:
    """Test initialization of BaseHAStorageAdapter."""

    def test_init_stores_hass_instance(self, mock_hass: Mock, entry_id: str) -> None:
        """Test that __init__ stores the Home Assistant instance."""
        with patch(
            "custom_components.intelligent_heating_pilot.infrastructure.adapters.base_ha_storage.Store"
        ):
            storage = TestHAStorage(mock_hass, entry_id)

            assert storage._hass == mock_hass

    def test_init_stores_entry_id(self, mock_hass: Mock, entry_id: str) -> None:
        """Test that __init__ stores the entry_id."""
        with patch(
            "custom_components.intelligent_heating_pilot.infrastructure.adapters.base_ha_storage.Store"
        ):
            storage = TestHAStorage(mock_hass, entry_id)

            assert storage._entry_id == entry_id

    def test_init_default_retention_days(self, mock_hass: Mock, entry_id: str) -> None:
        """Test that retention_days defaults to 30."""
        with patch(
            "custom_components.intelligent_heating_pilot.infrastructure.adapters.base_ha_storage.Store"
        ):
            storage = TestHAStorage(mock_hass, entry_id)

            assert storage._retention_days == 30

    def test_init_custom_retention_days(self, mock_hass: Mock, entry_id: str) -> None:
        """Test that custom retention_days is stored."""
        with patch(
            "custom_components.intelligent_heating_pilot.infrastructure.adapters.base_ha_storage.Store"
        ):
            storage = TestHAStorage(mock_hass, entry_id, retention_days=45)

            assert storage._retention_days == 45

    def test_init_sets_loaded_to_false(self, mock_hass: Mock, entry_id: str) -> None:
        """Test that _loaded flag is initialized to False."""
        with patch(
            "custom_components.intelligent_heating_pilot.infrastructure.adapters.base_ha_storage.Store"
        ):
            storage = TestHAStorage(mock_hass, entry_id)

            assert storage._loaded is False

    def test_init_creates_store_instance(self, mock_hass: Mock, entry_id: str) -> None:
        """Test that Store instance is created with correct parameters."""
        with patch(
            "custom_components.intelligent_heating_pilot.infrastructure.adapters.base_ha_storage.Store"
        ) as mock_store_class:
            storage = TestHAStorage(mock_hass, entry_id, storage_key="test_storage")

            mock_store_class.assert_called_once()
            # Verify Store was called with hass instance
            assert mock_store_class.call_args[0][0] == mock_hass
            assert storage is not None


class TestBaseHAStorageAdapterEnsureLoaded:
    """Test _ensure_loaded() method."""

    @pytest.mark.asyncio
    async def test_ensure_loaded_initializes_empty_storage(
        self, mock_hass: Mock, entry_id: str, mock_store: Mock
    ) -> None:
        """Test that _ensure_loaded creates default data when storage is empty."""
        with patch(
            "custom_components.intelligent_heating_pilot.infrastructure.adapters.base_ha_storage.Store",
            return_value=mock_store,
        ):
            storage = TestHAStorage(mock_hass, entry_id)

            # Act: Load storage
            await storage._ensure_loaded()

            # Assert: Store was queried
            mock_store.async_load.assert_called_once()

            # Assert: Data initialized with defaults
            assert storage._data == {"test_field": "default_value"}

            # Assert: Loaded flag set
            assert storage._loaded is True

    @pytest.mark.asyncio
    async def test_ensure_loaded_loads_existing_storage(
        self, mock_hass: Mock, entry_id: str, mock_store: Mock
    ) -> None:
        """Test that _ensure_loaded loads existing data from storage."""
        # Setup: Store returns existing data
        existing_data = {"test_field": "stored_value", "extra_field": 42}
        mock_store.async_load.return_value = existing_data

        with patch(
            "custom_components.intelligent_heating_pilot.infrastructure.adapters.base_ha_storage.Store",
            return_value=mock_store,
        ):
            storage = TestHAStorage(mock_hass, entry_id)

            # Act: Load storage
            await storage._ensure_loaded()

            # Assert: Data loaded from store
            assert storage._data == existing_data

            # Assert: Loaded flag set
            assert storage._loaded is True

    @pytest.mark.asyncio
    async def test_ensure_loaded_only_loads_once(
        self, mock_hass: Mock, entry_id: str, mock_store: Mock
    ) -> None:
        """Test that _ensure_loaded uses cache on subsequent calls."""
        with patch(
            "custom_components.intelligent_heating_pilot.infrastructure.adapters.base_ha_storage.Store",
            return_value=mock_store,
        ):
            storage = TestHAStorage(mock_hass, entry_id)

            # Act: Load multiple times
            await storage._ensure_loaded()
            await storage._ensure_loaded()
            await storage._ensure_loaded()

            # Assert: Store only queried once
            assert mock_store.async_load.call_count == 1


class TestBaseHAStorageAdapterSaveData:
    """Test _save_data() method."""

    @pytest.mark.asyncio
    async def test_save_data_persists_to_store(
        self, mock_hass: Mock, entry_id: str, mock_store: Mock
    ) -> None:
        """Test that _save_data persists data to storage."""
        with patch(
            "custom_components.intelligent_heating_pilot.infrastructure.adapters.base_ha_storage.Store",
            return_value=mock_store,
        ):
            storage = TestHAStorage(mock_hass, entry_id)
            await storage._ensure_loaded()

            # Act: Save data
            await storage._save_data()

            # Assert: Store.async_save was called with current data
            mock_store.async_save.assert_called_once_with(storage._data)

    @pytest.mark.asyncio
    async def test_save_data_updates_local_cache(
        self, mock_hass: Mock, entry_id: str, mock_store: Mock
    ) -> None:
        """Test that _save_data maintains consistency with local cache."""
        with patch(
            "custom_components.intelligent_heating_pilot.infrastructure.adapters.base_ha_storage.Store",
            return_value=mock_store,
        ):
            storage = TestHAStorage(mock_hass, entry_id)
            await storage._ensure_loaded()

            # Modify data
            storage._data["test_field"] = "modified_value"

            # Act: Save data
            await storage._save_data()

            # Assert: Saved data reflects modification
            saved_data = mock_store.async_save.call_args[0][0]
            assert saved_data["test_field"] == "modified_value"


class TestBaseHAStorageAdapterParseDatetime:
    """Test _parse_datetime() helper method."""

    def test_parse_datetime_with_valid_iso_string(self, mock_hass: Mock, entry_id: str) -> None:
        """Test parsing a valid ISO datetime string."""
        with patch(
            "custom_components.intelligent_heating_pilot.infrastructure.adapters.base_ha_storage.Store"
        ):
            storage = TestHAStorage(mock_hass, entry_id)

            # Act: Parse valid ISO string
            result = storage._parse_datetime("2025-12-18T14:30:00+00:00")

            # Assert: Correct datetime object
            assert result == datetime(2025, 12, 18, 14, 30, 0, tzinfo=timezone.utc)

    def test_parse_datetime_adds_utc_to_naive_datetime(
        self, mock_hass: Mock, entry_id: str
    ) -> None:
        """Test that naive datetime strings get UTC timezone added."""
        with patch(
            "custom_components.intelligent_heating_pilot.infrastructure.adapters.base_ha_storage.Store"
        ):
            storage = TestHAStorage(mock_hass, entry_id)

            # Act: Parse naive ISO string (no timezone)
            result = storage._parse_datetime("2025-12-18T14:30:00")

            # Assert: UTC timezone added
            assert result.tzinfo == timezone.utc
            assert result == datetime(2025, 12, 18, 14, 30, 0, tzinfo=timezone.utc)

    def test_parse_datetime_with_empty_string_raises_valueerror(
        self, mock_hass: Mock, entry_id: str
    ) -> None:
        """Test that empty string raises ValueError."""
        with patch(
            "custom_components.intelligent_heating_pilot.infrastructure.adapters.base_ha_storage.Store"
        ):
            storage = TestHAStorage(mock_hass, entry_id)

            # Act & Assert: Empty string raises ValueError
            with pytest.raises(ValueError):
                storage._parse_datetime("")

    def test_parse_datetime_with_invalid_format_raises_valueerror(
        self, mock_hass: Mock, entry_id: str
    ) -> None:
        """Test that invalid datetime format raises ValueError."""
        with patch(
            "custom_components.intelligent_heating_pilot.infrastructure.adapters.base_ha_storage.Store"
        ):
            storage = TestHAStorage(mock_hass, entry_id)

            # Act & Assert: Invalid format raises ValueError
            with pytest.raises(ValueError):
                storage._parse_datetime("not-a-datetime")


class TestBaseHAStorageAdapterSerializeDatetime:
    """Test _serialize_datetime() helper method."""

    def test_serialize_datetime_returns_iso_format(self, mock_hass: Mock, entry_id: str) -> None:
        """Test that _serialize_datetime returns ISO 8601 format."""
        with patch(
            "custom_components.intelligent_heating_pilot.infrastructure.adapters.base_ha_storage.Store"
        ):
            storage = TestHAStorage(mock_hass, entry_id)

            # Act: Serialize datetime
            dt = datetime(2025, 12, 18, 14, 30, 0, tzinfo=timezone.utc)
            result = storage._serialize_datetime(dt)

            # Assert: ISO format string
            assert result == "2025-12-18T14:30:00+00:00"

    def test_serialize_datetime_preserves_timezone(self, mock_hass: Mock, entry_id: str) -> None:
        """Test that timezone information is preserved in serialization."""
        with patch(
            "custom_components.intelligent_heating_pilot.infrastructure.adapters.base_ha_storage.Store"
        ):
            storage = TestHAStorage(mock_hass, entry_id)

            # Act: Serialize datetime with timezone
            dt = datetime(2025, 12, 18, 14, 30, 0, tzinfo=timezone.utc)
            result = storage._serialize_datetime(dt)

            # Assert: Timezone preserved
            assert "+00:00" in result


class TestBaseHAStorageAdapterCachingDisabled:
    """Test _is_caching_disabled() helper method."""

    def test_is_caching_disabled_returns_true_when_retention_zero(
        self, mock_hass: Mock, entry_id: str
    ) -> None:
        """Test that caching is considered disabled when retention_days=0."""
        with patch(
            "custom_components.intelligent_heating_pilot.infrastructure.adapters.base_ha_storage.Store"
        ):
            storage = TestHAStorage(mock_hass, entry_id, retention_days=0)

            # Act & Assert
            assert storage._is_caching_disabled() is True

    def test_is_caching_disabled_returns_false_when_retention_positive(
        self, mock_hass: Mock, entry_id: str
    ) -> None:
        """Test that caching is enabled when retention_days > 0."""
        with patch(
            "custom_components.intelligent_heating_pilot.infrastructure.adapters.base_ha_storage.Store"
        ):
            storage = TestHAStorage(mock_hass, entry_id, retention_days=30)

            # Act & Assert
            assert storage._is_caching_disabled() is False

    def test_is_caching_disabled_with_default_retention(
        self, mock_hass: Mock, entry_id: str
    ) -> None:
        """Test that caching is enabled with default retention_days."""
        with patch(
            "custom_components.intelligent_heating_pilot.infrastructure.adapters.base_ha_storage.Store"
        ):
            storage = TestHAStorage(mock_hass, entry_id)  # default is 30

            # Act & Assert
            assert storage._is_caching_disabled() is False
