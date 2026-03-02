"""Unit tests for HA recorder optimization changes.

Validates the key behavioral changes introduced to prevent HA reboot-in-loop:

1. fetch_all_historical_data() on ClimateDataAdapter issues a single recorder query
   (instead of one per HistoricalDataKey).
2. _get_cycles_with_cache() at first boot (empty cache) extracts only yesterday,
   not the full history_lookback_days window.
3. _get_contextual_lhs() never falls back to direct recorder extraction when the
   cycle cache is unavailable — it returns [] and uses the global LHS.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch
import pytest

from custom_components.intelligent_heating_pilot.application import HeatingApplicationService
from custom_components.intelligent_heating_pilot.domain.value_objects import (
    EnvironmentState,
    HistoricalDataKey,
    HistoricalDataSet,
    HistoricalMeasurement,
    ScheduledTimeslot,
)


def make_aware(dt: datetime) -> datetime:
    """Return timezone-aware UTC datetime."""
    return dt.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_adapters():
    """Create mock adapters for HeatingApplicationService."""
    scheduler_reader = Mock()
    scheduler_reader.get_next_timeslot = AsyncMock(return_value=None)
    scheduler_reader.is_scheduler_enabled = AsyncMock(return_value=True)

    model_storage = Mock()
    model_storage.get_learned_heating_slope = AsyncMock(return_value=2.0)
    model_storage.get_all_slope_data = AsyncMock(return_value=[])
    model_storage.get_cached_global_lhs = AsyncMock(return_value=None)
    model_storage.set_cached_global_lhs = AsyncMock()
    model_storage.get_cached_contextual_lhs = AsyncMock(return_value=None)
    model_storage.set_cached_contextual_lhs = AsyncMock()

    scheduler_commander = Mock()
    scheduler_commander.run_action = AsyncMock()
    scheduler_commander.cancel_action = AsyncMock()

    climate_commander = Mock()
    climate_commander.turn_on_heat = AsyncMock()
    climate_commander.turn_off = AsyncMock()
    climate_commander.set_temperature = AsyncMock()
    climate_commander.set_hvac_mode = AsyncMock()

    environment_reader = Mock()
    environment_reader.get_current_environment = AsyncMock()
    environment_reader.is_heating_active = AsyncMock(return_value=False)
    environment_reader.get_vtherm_slope = Mock(return_value=None)
    environment_reader.get_vtherm_entity_id = Mock(return_value="climate.vtherm_test")
    environment_reader.get_humidity_in_entity_id = Mock(return_value=None)
    environment_reader.get_humidity_out_entity_id = Mock(return_value=None)
    environment_reader.get_hass = Mock(return_value=Mock())

    return {
        "scheduler_reader": scheduler_reader,
        "model_storage": model_storage,
        "scheduler_commander": scheduler_commander,
        "climate_commander": climate_commander,
        "environment_reader": environment_reader,
    }


@pytest.fixture
def cycle_cache_mock():
    """Create a mock ICycleCache adapter."""
    cache = Mock()
    cache.get_cache_data = AsyncMock(return_value=None)
    cache.append_cycles = AsyncMock()
    cache.prune_old_cycles = AsyncMock()
    return cache


@pytest.fixture
def app_service_with_cache(mock_adapters, cycle_cache_mock):
    """HeatingApplicationService with a cycle cache mock."""
    return HeatingApplicationService(
        scheduler_reader=mock_adapters["scheduler_reader"],
        model_storage=mock_adapters["model_storage"],
        scheduler_commander=mock_adapters["scheduler_commander"],
        climate_commander=mock_adapters["climate_commander"],
        environment_reader=mock_adapters["environment_reader"],
        cycle_cache=cycle_cache_mock,
        history_lookback_days=30,
    )


@pytest.fixture
def app_service_no_cache(mock_adapters):
    """HeatingApplicationService WITHOUT a cycle cache (cycle_cache=None)."""
    return HeatingApplicationService(
        scheduler_reader=mock_adapters["scheduler_reader"],
        model_storage=mock_adapters["model_storage"],
        scheduler_commander=mock_adapters["scheduler_commander"],
        climate_commander=mock_adapters["climate_commander"],
        environment_reader=mock_adapters["environment_reader"],
        cycle_cache=None,
        history_lookback_days=30,
    )


# ---------------------------------------------------------------------------
# Test 1: ClimateDataAdapter.fetch_all_historical_data issues exactly one query
# ---------------------------------------------------------------------------


class TestClimateAdapterSingleQuery:
    """Ensure fetch_all_historical_data calls _fetch_history exactly once."""

    @pytest.mark.asyncio
    async def test_fetch_all_issues_single_recorder_query(self):
        """fetch_all_historical_data must call _fetch_history exactly once, not ×3."""
        from custom_components.intelligent_heating_pilot.infrastructure.adapters.climate_data_adapter import (
            ClimateDataAdapter,
        )

        mock_hass = Mock()
        adapter = ClimateDataAdapter(mock_hass)

        start = make_aware(datetime(2025, 1, 1, 0, 0))
        end = make_aware(datetime(2025, 1, 2, 0, 0))

        sample_records = [
            {
                "entity_id": "climate.vtherm",
                "state": "heat",
                "attributes": {
                    "current_temperature": 19.5,
                    "temperature": 21.0,
                    "hvac_action": "heating",
                },
                "last_changed": start,
                "last_updated": start,
            }
        ]

        fetch_call_count = 0

        async def fake_fetch_history(entity_id, s, e):
            nonlocal fetch_call_count
            fetch_call_count += 1
            return sample_records

        adapter._fetch_history = fake_fetch_history

        result = await adapter.fetch_all_historical_data("climate.vtherm", start, end)

        assert fetch_call_count == 1, (
            "fetch_all_historical_data must issue exactly ONE recorder query, "
            f"but _fetch_history was called {fetch_call_count} time(s)."
        )

    @pytest.mark.asyncio
    async def test_fetch_all_returns_all_keys_from_single_query(self):
        """fetch_all_historical_data extracts INDOOR_TEMP, TARGET_TEMP, HEATING_STATE in one pass."""
        from custom_components.intelligent_heating_pilot.infrastructure.adapters.climate_data_adapter import (
            ClimateDataAdapter,
        )

        mock_hass = Mock()
        adapter = ClimateDataAdapter(mock_hass)

        ts = make_aware(datetime(2025, 1, 1, 6, 0))
        records = [
            {
                "entity_id": "climate.vtherm",
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

        adapter._fetch_history = AsyncMock(return_value=records)

        result = await adapter.fetch_all_historical_data(
            "climate.vtherm",
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
        from custom_components.intelligent_heating_pilot.infrastructure.adapters.climate_data_adapter import (
            ClimateDataAdapter,
        )

        adapter = ClimateDataAdapter(Mock())
        adapter._fetch_history = AsyncMock(return_value=[])

        ts = make_aware(datetime(2025, 1, 1))
        result = await adapter.fetch_all_historical_data("climate.vtherm", ts, ts + timedelta(days=1))

        assert result.data == {}


# ---------------------------------------------------------------------------
# Test 2: Boot extraction is limited to yesterday only
# ---------------------------------------------------------------------------


class TestBootExtractionLimit:
    """Verify that first-boot cache fill covers only yesterday, not 30 days."""

    @pytest.mark.asyncio
    async def test_empty_cache_extracts_only_one_day(
        self, app_service_with_cache, cycle_cache_mock
    ):
        """When cache is empty, _get_cycles_with_cache must search at most 1 day back."""
        target_time = make_aware(datetime(2025, 3, 1, 6, 30))

        # No existing cache
        cycle_cache_mock.get_cache_data.return_value = None

        # Patch _extract_cycles_from_recorder to capture the time window used
        captured_windows: list[tuple[datetime, datetime]] = []

        async def fake_extract(device_id, start, end):
            captured_windows.append((start, end))
            return []

        app_service_with_cache._extract_cycles_from_recorder = fake_extract

        await app_service_with_cache._get_cycles_with_cache("climate.vtherm", target_time)

        assert len(captured_windows) == 1, "Expected exactly one extraction call at boot"
        start_used, end_used = captured_windows[0]
        window_days = (end_used - start_used).total_seconds() / 86400

        assert window_days <= 1.0, (
            f"Boot extraction window must be ≤ 1 day, but was {window_days:.1f} days. "
            "This would issue too many recorder queries with 10 devices."
        )

    @pytest.mark.asyncio
    async def test_empty_cache_initializes_cache_after_extraction(
        self, app_service_with_cache, cycle_cache_mock
    ):
        """After boot extraction, append_cycles is called to persist the cache."""
        target_time = make_aware(datetime(2025, 3, 1, 6, 30))
        cycle_cache_mock.get_cache_data.return_value = None
        app_service_with_cache._extract_cycles_from_recorder = AsyncMock(return_value=[])

        await app_service_with_cache._get_cycles_with_cache("climate.vtherm", target_time)

        cycle_cache_mock.append_cycles.assert_called_once()


# ---------------------------------------------------------------------------
# Test 3: No direct recorder fallback when cache is unavailable
# ---------------------------------------------------------------------------


class TestNoDirectFallbackWhenCacheEmpty:
    """Ensure _get_contextual_lhs never calls _extract_cycles_from_recorder directly."""

    @pytest.mark.asyncio
    async def test_no_cache_adapter_uses_global_lhs(
        self, app_service_no_cache, mock_adapters
    ):
        """Without a cycle cache, _get_contextual_lhs must return global LHS, no recorder call."""
        target_time = make_aware(datetime(2025, 3, 1, 6, 30))

        extract_called = []

        async def should_not_be_called(*args, **kwargs):
            extract_called.append(True)
            return []

        app_service_no_cache._extract_cycles_from_recorder = should_not_be_called

        lhs = await app_service_no_cache._get_contextual_lhs(target_time)

        assert not extract_called, (
            "_extract_cycles_from_recorder must NOT be called when cycle_cache is None. "
            "Direct extraction without throttling can cause 900+ recorder queries at boot."
        )
        # Falls back to global LHS from model_storage
        assert lhs == pytest.approx(2.0)

    @pytest.mark.asyncio
    async def test_cache_exception_uses_global_lhs(
        self, app_service_with_cache, cycle_cache_mock, mock_adapters
    ):
        """When cycle cache raises an exception, return global LHS without recorder fallback."""
        target_time = make_aware(datetime(2025, 3, 1, 6, 30))

        cycle_cache_mock.get_cache_data.side_effect = RuntimeError("cache unavailable")

        extract_called = []

        async def should_not_be_called(*args, **kwargs):
            extract_called.append(True)
            return []

        app_service_with_cache._extract_cycles_from_recorder = should_not_be_called

        lhs = await app_service_with_cache._get_contextual_lhs(target_time)

        assert not extract_called, (
            "_extract_cycles_from_recorder must NOT be called on cache exception. "
            "Direct extraction without throttling risks saturating the recorder."
        )
        assert lhs == pytest.approx(2.0)

    @pytest.mark.asyncio
    async def test_empty_cache_returns_global_lhs(
        self, app_service_with_cache, cycle_cache_mock, mock_adapters
    ):
        """When cache returns [] (e.g. first boot not yet done), global LHS is used."""
        target_time = make_aware(datetime(2025, 3, 1, 6, 30))

        # Cache exists but returns no cycles (e.g. first boot extraction found nothing)
        from custom_components.intelligent_heating_pilot.domain.value_objects.cycle_cache_data import (
            CycleCacheData,
        )

        empty_cache = CycleCacheData(
            device_id="climate.vtherm",
            cycles=tuple(),
            last_search_time=target_time - timedelta(hours=1),
            retention_days=30,
        )
        cycle_cache_mock.get_cache_data.return_value = empty_cache
        cycle_cache_mock.prune_old_cycles = AsyncMock()

        # Updated cache returns empty as well
        async def fake_get_cache_data_after_prune(device_id):
            return empty_cache

        cycle_cache_mock.get_cache_data.side_effect = [empty_cache, empty_cache]

        extract_called = []

        async def should_not_be_called(*args, **kwargs):
            extract_called.append(True)
            return []

        app_service_with_cache._extract_cycles_from_recorder = should_not_be_called

        lhs = await app_service_with_cache._get_contextual_lhs(target_time)

        assert not extract_called, (
            "_extract_cycles_from_recorder must NOT be called when cache is empty."
        )
        assert lhs == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# Test 4: _extract_cycles_from_recorder uses fetch_all_historical_data
# ---------------------------------------------------------------------------


class TestExtractCyclesUsesOneSingleQuery:
    """Confirm _extract_cycles_from_recorder uses fetch_all_historical_data (÷3 queries)."""

    @pytest.mark.asyncio
    async def test_extract_cycles_uses_fetch_all(
        self, app_service_with_cache, mock_adapters
    ):
        """_extract_cycles_from_recorder must call fetch_all_historical_data, not 3× fetch_historical_data."""
        from custom_components.intelligent_heating_pilot.infrastructure.adapters import (
            ClimateDataAdapter,
        )

        start = make_aware(datetime(2025, 1, 1))
        end = make_aware(datetime(2025, 1, 2))

        fetch_all_calls = []
        fetch_individual_calls = []

        async def fake_fetch_all(*args):
            # Called as instance method: (self, entity_id, start, end)
            # Capture the entity_id (args[1]) ignoring self (args[0])
            fetch_all_calls.append(args[1:])
            return HistoricalDataSet(data={})

        async def fake_fetch_historical(*args):
            # Called as instance method: (self, entity_id, key, start, end)
            fetch_individual_calls.append(args[1:])
            return HistoricalDataSet(data={})

        with patch.object(ClimateDataAdapter, "fetch_all_historical_data", fake_fetch_all):
            with patch.object(ClimateDataAdapter, "fetch_historical_data", fake_fetch_historical):
                await app_service_with_cache._extract_cycles_from_recorder(
                    "climate.vtherm", start, end
                )

        assert len(fetch_all_calls) == 1, (
            "_extract_cycles_from_recorder must call fetch_all_historical_data exactly once."
        )
        assert fetch_individual_calls == [], (
            "fetch_historical_data must NOT be called for climate keys — "
            "fetch_all_historical_data handles all of them in one recorder query."
        )
