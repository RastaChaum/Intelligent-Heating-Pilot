"""Unit tests for HA recorder optimization changes.

Validates the key behavioral changes introduced to prevent HA reboot-in-loop:

1. HAClimateDataReader.fetch_all_historical_data() issues exactly ONE recorder query
   (instead of one per HistoricalDataKey).
2. HeatingCycleLifecycleManager.refresh_heating_cycle_cache(is_startup=True) limits
   extraction to 1 day (yesterday only) — not the full retention window.
3. HeatingCycleLifecycleManager.get_cycles_for_window() returns [] when cache is empty
   (no synchronous fallback to direct recorder extraction).
4. _find_missing_date_ranges(max_catchup_days=1) correctly caps results to 1 day.
"""
from __future__ import annotations

from contextlib import suppress
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch, call
import pytest

from custom_components.intelligent_heating_pilot.domain.value_objects import (
    HistoricalDataKey,
    HistoricalDataSet,
    HistoricalMeasurement,
)


def make_aware(dt: datetime) -> datetime:
    """Return timezone-aware UTC datetime."""
    return dt.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Helpers for HeatingCycleLifecycleManager fixture
# ---------------------------------------------------------------------------


def _make_device_config(device_id: str = "climate.vtherm_test", retention_days: int = 30):
    from custom_components.intelligent_heating_pilot.domain.interfaces.device_config_reader_interface import (
        DeviceConfig,
    )

    return DeviceConfig(
        device_id=device_id,
        vtherm_entity_id=device_id,
        scheduler_entities=[],
        lhs_retention_days=retention_days,
    )


def _make_lifecycle_manager(
    cycle_storage=None,
    historical_adapters=None,
    lhs_storage=None,
):
    """Build a HeatingCycleLifecycleManager with minimal mocks."""
    from custom_components.intelligent_heating_pilot.application.heating_cycle_lifecycle_manager import (
        HeatingCycleLifecycleManager,
    )
    from custom_components.intelligent_heating_pilot.domain.services import HeatingCycleService

    device_config = _make_device_config()
    heating_cycle_service = HeatingCycleService(
        temp_delta_threshold=1.0,
        cycle_split_duration_minutes=30,
        min_cycle_duration_minutes=5,
        max_cycle_duration_minutes=300,
    )
    return HeatingCycleLifecycleManager(
        device_config=device_config,
        heating_cycle_service=heating_cycle_service,
        heating_cycle_storage=cycle_storage,
        historical_adapters=historical_adapters or [],
        lhs_storage=lhs_storage,
        lhs_lifecycle_manager=None,
        timer_scheduler=None,
        dead_time_updated_callback=None,
    )


# ---------------------------------------------------------------------------
# Test 1: HAClimateDataReader.fetch_all_historical_data issues exactly one query
# ---------------------------------------------------------------------------


class TestHAClimateDataReaderSingleQuery:
    """Ensure fetch_all_historical_data calls _fetch_history exactly once."""

    def _make_reader(self):
        """Create a reader with a mocked mapper registry."""
        from custom_components.intelligent_heating_pilot.infrastructure.adapters.climate_data_reader import (
            HAClimateDataReader,
        )
        from custom_components.intelligent_heating_pilot.infrastructure.adapters.vtherm_attribute_mapper import (
            VThermAttributeMapper,
        )

        mock_hass = Mock()
        mock_queue = Mock()
        mock_queue.lock = Mock()
        mock_queue.lock.__aenter__ = AsyncMock(return_value=None)
        mock_queue.lock.__aexit__ = AsyncMock(return_value=None)

        reader = HAClimateDataReader(mock_hass, mock_queue, "climate.vtherm_test")
        # Inject a VTherm mapper directly to avoid HA state lookup in unit tests
        reader._mapper_registry = Mock()
        reader._mapper_registry.get_mapper_for_entity = Mock(
            return_value=VThermAttributeMapper(mock_hass)
        )
        return reader

    @pytest.mark.asyncio
    async def test_fetch_all_issues_single_recorder_query(self):
        """fetch_all_historical_data must call _fetch_history exactly once, not ×3."""
        reader = self._make_reader()

        start = make_aware(datetime(2025, 1, 1, 0, 0))
        end = make_aware(datetime(2025, 1, 2, 0, 0))

        fetch_call_count = 0

        async def fake_fetch_history(entity_id, s, e):
            nonlocal fetch_call_count
            fetch_call_count += 1
            return []

        reader._fetch_history = fake_fetch_history

        await reader.fetch_all_historical_data("climate.vtherm_test", start, end)

        assert fetch_call_count == 1, (
            "fetch_all_historical_data must issue exactly ONE recorder query, "
            f"but _fetch_history was called {fetch_call_count} time(s)."
        )

    @pytest.mark.asyncio
    async def test_fetch_all_returns_all_keys_from_single_query(self):
        """fetch_all_historical_data extracts INDOOR_TEMP, TARGET_TEMP, HEATING_STATE in one pass."""
        reader = self._make_reader()

        ts = make_aware(datetime(2025, 1, 1, 6, 0))
        records = [
            {
                "entity_id": "climate.vtherm_test",
                "state": "heat",
                "attributes": {
                    "current_temperature": 18.0,
                    "temperature": 20.0,
                    "hvac_action": "heating",
                },
                "last_changed": ts,
                "last_updated": ts,
            }
        ]

        reader._fetch_history = AsyncMock(return_value=records)

        result = await reader.fetch_all_historical_data(
            "climate.vtherm_test",
            ts - timedelta(hours=1),
            ts + timedelta(hours=1),
        )

        assert HistoricalDataKey.INDOOR_TEMP in result.data
        assert HistoricalDataKey.TARGET_TEMP in result.data
        assert HistoricalDataKey.HEATING_STATE in result.data
        assert result.data[HistoricalDataKey.INDOOR_TEMP][0].value == 18.0
        assert result.data[HistoricalDataKey.TARGET_TEMP][0].value == 20.0
        assert result.data[HistoricalDataKey.HEATING_STATE][0].value == "heating"

    @pytest.mark.asyncio
    async def test_fetch_all_empty_history_returns_empty_dataset(self):
        """fetch_all_historical_data returns empty HistoricalDataSet when no records."""
        reader = self._make_reader()
        reader._fetch_history = AsyncMock(return_value=[])

        ts = make_aware(datetime(2025, 1, 1))
        result = await reader.fetch_all_historical_data(
            "climate.vtherm_test", ts, ts + timedelta(days=1)
        )

        assert result.data == {}


# ---------------------------------------------------------------------------
# Test 2: Boot extraction is limited to yesterday only (max_catchup_days=1)
# ---------------------------------------------------------------------------


class TestBootExtractionLimit:
    """Verify _find_missing_date_ranges respects max_catchup_days=1 at startup."""

    @pytest.mark.asyncio
    async def test_empty_cache_max_catchup_1_returns_only_yesterday(self):
        """With empty cache and max_catchup_days=1, only yesterday is returned."""
        cycle_storage = Mock()
        cycle_storage.get_cache_data = AsyncMock(return_value=None)

        manager = _make_lifecycle_manager(cycle_storage=cycle_storage)

        today = date(2025, 3, 2)
        yesterday = date(2025, 3, 1)
        thirty_days_ago = today - timedelta(days=30)

        ranges = await manager._find_missing_date_ranges(
            thirty_days_ago, yesterday, max_catchup_days=1
        )

        assert len(ranges) == 1
        start, end = ranges[0]
        total_days = (end - start).days + 1
        assert total_days == 1, (
            f"Boot extraction must be limited to 1 day, got {total_days} days."
        )
        # Should be yesterday (most recent day)
        assert end == yesterday

    @pytest.mark.asyncio
    async def test_no_limit_returns_full_window(self):
        """Without max_catchup_days, all missing days are returned."""
        cycle_storage = Mock()
        cycle_storage.get_cache_data = AsyncMock(return_value=None)

        manager = _make_lifecycle_manager(cycle_storage=cycle_storage)

        today = date(2025, 3, 2)
        yesterday = date(2025, 3, 1)
        five_days_ago = today - timedelta(days=5)

        ranges = await manager._find_missing_date_ranges(
            five_days_ago, yesterday, max_catchup_days=None
        )

        # Without limit, the entire 5-day range is missing
        total_days = sum((e - s).days + 1 for s, e in ranges)
        assert total_days == 5

    def test_apply_max_catchup_truncates_to_most_recent(self):
        """_apply_max_catchup keeps the most recent days."""
        from custom_components.intelligent_heating_pilot.application.heating_cycle_lifecycle_manager import (
            HeatingCycleLifecycleManager,
        )

        # 5-day gap: 2025-02-24 to 2025-02-28
        ranges = [(date(2025, 2, 24), date(2025, 2, 28))]
        result = HeatingCycleLifecycleManager._apply_max_catchup(ranges, max_catchup_days=1)

        assert len(result) == 1
        start, end = result[0]
        assert start == end  # 1 day only
        assert end == date(2025, 2, 28)  # Most recent day


# ---------------------------------------------------------------------------
# Test 3: No synchronous fallback when cache is empty
# ---------------------------------------------------------------------------


class TestNoDirectFallbackWhenCacheEmpty:
    """get_cycles_for_window() must return [] without calling _extract_cycles()."""

    @pytest.mark.asyncio
    async def test_no_storage_returns_empty_list(self):
        """When cycle_cache=None, get_cycles_for_window returns [] immediately."""
        manager = _make_lifecycle_manager(cycle_storage=None)

        extract_called = []

        async def should_not_be_called(*args, **kwargs):
            extract_called.append(True)
            return []

        manager._extract_cycles = should_not_be_called

        start = make_aware(datetime(2025, 3, 1, 0, 0))
        end = make_aware(datetime(2025, 3, 1, 23, 59))
        result = await manager.get_cycles_for_window("climate.vtherm_test", start, end)

        assert result == []
        assert not extract_called, (
            "_extract_cycles must NOT be called when cycle_cache is None. "
            "Direct extraction outside the queue risks saturating the recorder."
        )

    @pytest.mark.asyncio
    async def test_empty_storage_returns_empty_list(self):
        """When storage returns None (no data), get_cycles_for_window returns []."""
        cycle_storage = Mock()
        cycle_storage.get_cache_data = AsyncMock(return_value=None)

        manager = _make_lifecycle_manager(cycle_storage=cycle_storage)

        extract_called = []

        async def should_not_be_called(*args, **kwargs):
            extract_called.append(True)
            return []

        manager._extract_cycles = should_not_be_called

        start = make_aware(datetime(2025, 3, 1, 0, 0))
        end = make_aware(datetime(2025, 3, 1, 23, 59))
        result = await manager.get_cycles_for_window("climate.vtherm_test", start, end)

        assert result == []
        assert not extract_called


# ---------------------------------------------------------------------------
# Test 4: _extract_cycles uses fetch_all_historical_data (not per-key loop)
# ---------------------------------------------------------------------------


class TestExtractCyclesUsesAllHistoricalData:
    """_extract_cycles() must call fetch_all_historical_data, not 11×fetch_historical_data."""

    @pytest.mark.asyncio
    async def test_extract_cycles_calls_fetch_all(self):
        """_extract_cycles must call fetch_all_historical_data exactly once per adapter."""
        ts = make_aware(datetime(2025, 1, 1, 8, 0))
        minimal_data = HistoricalDataSet(
            data={
                HistoricalDataKey.INDOOR_TEMP: [
                    HistoricalMeasurement(timestamp=ts, value=18.0, attributes={}, entity_id="climate.vtherm_test")
                ],
                HistoricalDataKey.TARGET_TEMP: [
                    HistoricalMeasurement(timestamp=ts, value=20.0, attributes={}, entity_id="climate.vtherm_test")
                ],
                HistoricalDataKey.HEATING_STATE: [
                    HistoricalMeasurement(timestamp=ts, value="heating", attributes={}, entity_id="climate.vtherm_test")
                ],
            }
        )

        mock_adapter = Mock(spec=["fetch_historical_data", "fetch_all_historical_data"])
        mock_adapter.fetch_all_historical_data = AsyncMock(return_value=minimal_data)
        mock_adapter.fetch_historical_data = AsyncMock(
            return_value=HistoricalDataSet(data={})
        )

        manager = _make_lifecycle_manager(historical_adapters=[mock_adapter])

        start = make_aware(datetime(2025, 1, 1))
        end = make_aware(datetime(2025, 1, 2))

        await manager._extract_cycles("climate.vtherm_test", start, end)

        mock_adapter.fetch_all_historical_data.assert_called_once_with(
            entity_id="climate.vtherm_test",
            start_time=start,
            end_time=end,
        )
        mock_adapter.fetch_historical_data.assert_not_called()


