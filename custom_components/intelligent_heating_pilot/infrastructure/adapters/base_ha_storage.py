"""Base class for Home Assistant storage adapters.

This module provides a unified base class for storage adapters that use
Home Assistant's Store helper. It implements common patterns like lazy loading,
timezone-aware datetime handling, and caching control.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Generic, TypeVar

from homeassistant.helpers.storage import Store

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# Storage version
STORAGE_VERSION = 1

# Type variable for generic data structure
TData = TypeVar("TData")


class BaseHAStorageAdapter(ABC, Generic[TData]):
    """Abstract base class for Home Assistant storage adapters.

    This class provides common functionality for storage adapters:
    - Lazy loading with caching (_loaded flag)
    - Timezone-aware datetime parsing and serialization
    - Caching control based on retention_days
    - Centralized data persistence

    Subclasses must implement:
    - _get_default_data(): Returns the default data structure
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        storage_key: str | None = None,
        retention_days: int = 30,
    ) -> None:
        """Initialize the base storage adapter.

        Args:
            hass: Home Assistant instance
            entry_id: Config entry ID for scoped storage
            storage_key: Custom storage key (optional, derived from class name if not provided)
            retention_days: Number of days to retain cached data (0 disables caching)
        """
        self._hass = hass
        self._entry_id = entry_id
        self._retention_days = retention_days
        self._loaded = False

        # Create storage key if not provided
        if storage_key is None:
            # Use class name as storage key (e.g., HALhsStorage -> ha_lhs_storage)
            storage_key = self.__class__.__name__.lower()

        # Initialize Store
        self._store = Store(hass, STORAGE_VERSION, f"{storage_key}_{entry_id}")
        self._data: TData = self._get_default_data()

    @abstractmethod
    def _get_default_data(self) -> TData:
        """Return the default data structure for this storage adapter.

        Subclasses must implement this method to provide the initial
        data structure when storage is empty.

        Returns:
            The default data structure
        """
        pass

    async def _ensure_loaded(self) -> None:
        """Ensure storage data is loaded (lazy loading pattern).

        This method loads data from storage only once (on first call).
        Subsequent calls use the cached data (_loaded flag).
        """
        if self._loaded:
            return

        _LOGGER.debug("Loading storage data for %s", self.__class__.__name__)

        stored_data = await self._store.async_load()
        if stored_data is not None:
            self._data = stored_data
            _LOGGER.debug("Loaded existing storage data (version %d)", STORAGE_VERSION)
        else:
            # Initialize with default structure
            self._data = self._get_default_data()
            _LOGGER.debug("Initialized new storage with default data")

        self._loaded = True

    async def _save_data(self) -> None:
        """Persist current data to storage.

        This method saves the current _data to Home Assistant's Store.
        Should be called after any modification to _data.
        """
        await self._store.async_save(self._data)
        _LOGGER.debug("Saved storage data for %s", self.__class__.__name__)

    def _parse_datetime(self, dt_string: str) -> datetime:
        """Parse an ISO datetime string to a timezone-aware datetime object.

        This method ensures that all datetime objects are timezone-aware.
        If the input string represents a naive datetime (no timezone),
        UTC timezone is automatically added.

        Args:
            dt_string: ISO 8601 datetime string (e.g., "2025-12-18T14:30:00+00:00")

        Returns:
            Timezone-aware datetime object

        Raises:
            ValueError: If the datetime string is invalid or empty
        """
        if not dt_string:
            raise ValueError("Datetime string cannot be empty")

        dt = datetime.fromisoformat(dt_string)

        # Ensure timezone-aware: add UTC if naive
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt

    def _serialize_datetime(self, dt: datetime) -> str:
        """Serialize a datetime object to ISO 8601 format string.

        Args:
            dt: Datetime object (preferably timezone-aware)

        Returns:
            ISO 8601 formatted string (e.g., "2025-12-18T14:30:00+00:00")
        """
        return dt.isoformat()

    def _is_caching_disabled(self) -> bool:
        """Check if caching is disabled based on retention_days setting.

        Caching is considered disabled when retention_days is set to 0.

        Returns:
            True if caching is disabled, False otherwise
        """
        return self._retention_days == 0
