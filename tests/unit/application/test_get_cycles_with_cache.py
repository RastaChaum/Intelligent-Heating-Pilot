"""Unit tests for _get_cycles_with_cache() cache-first behavior.

P3 tests validating:
1. Startup reads cache when available and recent (no recorder extraction).
2. Extracted cycles are persisted via cycle_cache.append_cycles().
3. Incremental extraction starts from last_search_time (not full window).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest

from custom_components.intelligent_heating_pilot.application import HeatingApplicationService
from custom_components.intelligent_heating_pilot.domain.value_objects import (
    CycleCacheData,
    HeatingCycle,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DEVICE_ID = "climate.test_vtherm"


def _make_dt(hour: int = 12, days_offset: int = 0) -> datetime:
    """Return a timezone-aware UTC datetime."""
    base = datetime(2025, 6, 1, hour, 0, 0, tzinfo=timezone.utc)
    return base + timedelta(days=days_offset)


def _make_cycle(start: datetime, duration_h: float = 1.0) -> HeatingCycle:
    """Build a minimal HeatingCycle for tests."""
    end = start + timedelta(hours=duration_h)
    return HeatingCycle(
        device_id=DEVICE_ID,
        start_time=start,
        end_time=end,
        target_temp=21.0,
        end_temp=20.5,
        start_temp=18.0,
        tariff_details=None,
    )


def _make_cache(last_search_time: datetime, cycles: list[HeatingCycle] | None = None) -> CycleCacheData:
    """Build a CycleCacheData value object."""
    return CycleCacheData(
        device_id=DEVICE_ID,
        cycles=tuple(cycles or []),
        last_search_time=last_search_time,
        retention_days=30,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_cycle_cache() -> Mock:
    """Create a mock ICycleCache."""
    cache = Mock()
    cache.get_cache_data = AsyncMock(return_value=None)
    cache.append_cycles = AsyncMock()
    cache.prune_old_cycles = AsyncMock()
    cache.get_last_search_time = AsyncMock(return_value=None)
    return cache


@pytest.fixture
def app_service(mock_cycle_cache: Mock) -> HeatingApplicationService:
    """Create HeatingApplicationService with mocked adapters and cycle cache."""
    scheduler_reader = Mock()
    scheduler_reader.get_next_timeslot = AsyncMock(return_value=None)
    scheduler_reader.is_scheduler_enabled = AsyncMock(return_value=True)

    model_storage = Mock()
    model_storage.get_learned_heating_slope = AsyncMock(return_value=2.0)
    model_storage.get_all_slope_data = AsyncMock(return_value=[])

    scheduler_commander = Mock()
    climate_commander = Mock()

    environment_reader = Mock()
    environment_reader.get_vtherm_entity_id = Mock(return_value=DEVICE_ID)
    environment_reader.get_current_environment = AsyncMock(return_value=None)
    environment_reader.get_hass = Mock(return_value=Mock())
    environment_reader.get_humidity_in_entity_id = Mock(return_value=None)
    environment_reader.get_humidity_out_entity_id = Mock(return_value=None)

    return HeatingApplicationService(
        scheduler_reader=scheduler_reader,
        model_storage=model_storage,
        scheduler_commander=scheduler_commander,
        climate_commander=climate_commander,
        environment_reader=environment_reader,
        cycle_cache=mock_cycle_cache,
        history_lookback_days=21,
    )


# ---------------------------------------------------------------------------
# P3-1: Startup reads cache when recent – no recorder extraction
# ---------------------------------------------------------------------------

class TestStartupUsesCacheWhenRecent:
    """When cache was last searched < 24 h ago, recorder must not be called."""

    @pytest.mark.asyncio
    async def test_cache_used_and_extraction_skipped_when_recent(
        self, app_service: HeatingApplicationService, mock_cycle_cache: Mock
    ) -> None:
        """Cache is recent (12 h ago): _extract_cycles_from_recorder must NOT be called."""
        target_time = _make_dt(hour=8)
        last_search = target_time - timedelta(hours=12)  # 12 h ago – within 24 h

        cached_cycle = _make_cycle(last_search - timedelta(hours=5))
        cache_data = _make_cache(last_search_time=last_search, cycles=[cached_cycle])

        mock_cycle_cache.get_cache_data = AsyncMock(return_value=cache_data)
        # After prune, get_cache_data is called again – return same data
        mock_cycle_cache.prune_old_cycles = AsyncMock()

        with patch.object(
            app_service,
            "_extract_cycles_from_recorder",
            new_callable=AsyncMock,
        ) as mock_extract:
            result = await app_service._get_cycles_with_cache(DEVICE_ID, target_time)

        # Recorder should never be called
        mock_extract.assert_not_called()

        # append_cycles must NOT be called either (no new extraction)
        mock_cycle_cache.append_cycles.assert_not_called()

    @pytest.mark.asyncio
    async def test_cached_cycles_are_returned_when_recent(
        self, app_service: HeatingApplicationService, mock_cycle_cache: Mock
    ) -> None:
        """Returned cycles come from the cache, not the recorder."""
        target_time = _make_dt(hour=8)
        last_search = target_time - timedelta(hours=6)

        cached_cycles = [
            _make_cycle(target_time - timedelta(days=2)),
            _make_cycle(target_time - timedelta(days=1)),
        ]
        cache_data = _make_cache(last_search_time=last_search, cycles=cached_cycles)

        mock_cycle_cache.get_cache_data = AsyncMock(return_value=cache_data)

        with patch.object(
            app_service,
            "_extract_cycles_from_recorder",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await app_service._get_cycles_with_cache(DEVICE_ID, target_time)

        assert len(result) == 2


# ---------------------------------------------------------------------------
# P3-2: Extracted cycles are persisted via append_cycles()
# ---------------------------------------------------------------------------

class TestExtractedCyclesPersistedToCache:
    """After recorder extraction, cycles must be saved through append_cycles()."""

    @pytest.mark.asyncio
    async def test_cycles_persisted_on_full_extraction(
        self, app_service: HeatingApplicationService, mock_cycle_cache: Mock
    ) -> None:
        """No prior cache: full extraction result is passed to append_cycles()."""
        target_time = _make_dt(hour=8)
        mock_cycle_cache.get_cache_data = AsyncMock(return_value=None)

        extracted = [_make_cycle(target_time - timedelta(days=3))]

        with patch.object(
            app_service,
            "_extract_cycles_from_recorder",
            new_callable=AsyncMock,
            return_value=extracted,
        ):
            await app_service._get_cycles_with_cache(DEVICE_ID, target_time)

        mock_cycle_cache.append_cycles.assert_called_once()
        call_args = mock_cycle_cache.append_cycles.call_args
        assert call_args[0][0] == DEVICE_ID          # device_id
        assert call_args[0][1] == extracted          # cycles list
        assert call_args[0][2] == target_time        # search_end_time

    @pytest.mark.asyncio
    async def test_cycles_persisted_on_incremental_extraction(
        self, app_service: HeatingApplicationService, mock_cycle_cache: Mock
    ) -> None:
        """Old cache: incremental extraction result is appended to cache."""
        target_time = _make_dt(hour=8)
        last_search = target_time - timedelta(hours=48)  # > 24 h → triggers incremental

        old_cycle = _make_cycle(target_time - timedelta(days=5))
        cache_data = _make_cache(last_search_time=last_search, cycles=[old_cycle])

        new_cycle = _make_cycle(target_time - timedelta(hours=10))
        mock_cycle_cache.get_cache_data = AsyncMock(return_value=cache_data)

        with patch.object(
            app_service,
            "_extract_cycles_from_recorder",
            new_callable=AsyncMock,
            return_value=[new_cycle],
        ):
            await app_service._get_cycles_with_cache(DEVICE_ID, target_time)

        mock_cycle_cache.append_cycles.assert_called_once()
        call_args = mock_cycle_cache.append_cycles.call_args
        assert call_args[0][1] == [new_cycle]


# ---------------------------------------------------------------------------
# P3-3: Incremental extraction starts from last_search_time (not full window)
# ---------------------------------------------------------------------------

class TestIncrementalExtractionRange:
    """Incremental search must start from last_search_time, not from (now - retention_days)."""

    @pytest.mark.asyncio
    async def test_extraction_starts_from_last_search_time_not_full_window(
        self, app_service: HeatingApplicationService, mock_cycle_cache: Mock
    ) -> None:
        """When cache is stale (>= 24 h), search starts at last_search_time."""
        target_time = _make_dt(hour=8)
        last_search = target_time - timedelta(hours=30)  # 30 h ago → stale

        cache_data = _make_cache(last_search_time=last_search, cycles=[])
        mock_cycle_cache.get_cache_data = AsyncMock(return_value=cache_data)

        with patch.object(
            app_service,
            "_extract_cycles_from_recorder",
            new_callable=AsyncMock,
            return_value=[],
        ) as mock_extract:
            await app_service._get_cycles_with_cache(DEVICE_ID, target_time)

        mock_extract.assert_called_once()
        call_args = mock_extract.call_args[0]
        search_start_used = call_args[1]  # start_time arg

        # Must start from last_search_time, not from target_time - history_lookback_days
        assert search_start_used == last_search

        # Must NOT start from the full retention window
        full_window_start = target_time - timedelta(days=app_service._history_lookback_days)
        assert search_start_used != full_window_start

    @pytest.mark.asyncio
    async def test_full_window_extraction_when_no_cache(
        self, app_service: HeatingApplicationService, mock_cycle_cache: Mock
    ) -> None:
        """When there is no prior cache, search covers the full retention window."""
        target_time = _make_dt(hour=8)
        mock_cycle_cache.get_cache_data = AsyncMock(return_value=None)

        with patch.object(
            app_service,
            "_extract_cycles_from_recorder",
            new_callable=AsyncMock,
            return_value=[],
        ) as mock_extract:
            await app_service._get_cycles_with_cache(DEVICE_ID, target_time)

        mock_extract.assert_called_once()
        call_args = mock_extract.call_args[0]
        search_start_used = call_args[1]

        expected_start = target_time - timedelta(days=app_service._history_lookback_days)
        assert search_start_used == expected_start
