"""Unit tests for ClimateDataAdapter."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.intelligent_heating_pilot.domain.value_objects import (
    HistoricalDataKey,
    HistoricalDataSet,
)
from custom_components.intelligent_heating_pilot.infrastructure.adapters.climate_data_adapter import (
    ClimateDataAdapter,
)
from tests.unit.domain.fixtures import (
    MOCK_CLIMATE_HISTORY_RESPONSE,
    TEST_ENTITY_ID,
    get_future_datetime,
    get_test_datetime,
)


class TestClimateDataAdapter:
    """Tests for ClimateDataAdapter."""

    @pytest.fixture
    def mock_hass(self):
        """Create a mock Home Assistant instance."""
        return MagicMock()

    @pytest.fixture
    def adapter(self, mock_hass):
        """Create a ClimateDataAdapter instance."""
        return ClimateDataAdapter(mock_hass)

    @pytest.mark.asyncio
    async def test_fetch_historical_data_returns_dataset(self, adapter):
        """Return a HistoricalDataSet when data exists."""
        start_time = get_test_datetime()
        end_time = get_future_datetime(hours=1)

        adapter._fetch_history = AsyncMock(return_value=MOCK_CLIMATE_HISTORY_RESPONSE[0])

        result = await adapter.fetch_historical_data(
            TEST_ENTITY_ID, HistoricalDataKey.INDOOR_TEMP, start_time, end_time
        )

        assert isinstance(result, HistoricalDataSet)
        assert HistoricalDataKey.INDOOR_TEMP in result.data
        assert len(result.data[HistoricalDataKey.INDOOR_TEMP]) == 3

    @pytest.mark.asyncio
    async def test_fetch_historical_data_extracts_indoor_temp(self, adapter):
        """Extract indoor temperature from current_temperature attribute."""
        start_time = get_test_datetime()
        end_time = get_future_datetime(hours=1)

        adapter._fetch_history = AsyncMock(return_value=MOCK_CLIMATE_HISTORY_RESPONSE[0])

        result = await adapter.fetch_historical_data(
            "climate.living_room", HistoricalDataKey.INDOOR_TEMP, start_time, end_time
        )

        measurements = result.data[HistoricalDataKey.INDOOR_TEMP]
        assert measurements[0].value == 18.0
        assert measurements[1].value == 19.0
        assert measurements[2].value == 21.0

    @pytest.mark.asyncio
    async def test_fetch_historical_data_extracts_target_temperature(self, adapter):
        """Extract target temperature from target_temperature attribute."""
        start_time = get_test_datetime()
        end_time = get_future_datetime(hours=1)

        adapter._fetch_history = AsyncMock(return_value=MOCK_CLIMATE_HISTORY_RESPONSE[0])

        result = await adapter.fetch_historical_data(
            "climate.living_room", HistoricalDataKey.TARGET_TEMP, start_time, end_time
        )

        measurements = result.data[HistoricalDataKey.TARGET_TEMP]
        assert measurements[0].value == 21.0
        assert measurements[1].value == 21.0
        assert measurements[2].value == 21.0

    @pytest.mark.asyncio
    async def test_fetch_historical_data_prefers_temperature_attribute(self, adapter):
        """Use temperature attribute when available before target_temperature."""
        start_time = get_test_datetime()
        end_time = get_future_datetime(hours=1)
        custom_records = [
            {
                "entity_id": "climate.living_room",
                "state": "heat",
                "attributes": {"temperature": 22.5, "target_temperature": 20.0},
                "last_changed": "2024-01-15T12:00:00+00:00",
            }
        ]

        adapter._fetch_history = AsyncMock(return_value=custom_records)

        result = await adapter.fetch_historical_data(
            "climate.living_room", HistoricalDataKey.TARGET_TEMP, start_time, end_time
        )

        measurements = result.data[HistoricalDataKey.TARGET_TEMP]
        assert measurements[0].value == 22.5

    @pytest.mark.asyncio
    async def test_fetch_historical_data_extracts_heating_state(self, adapter):
        """Extract hvac_action values when requested."""
        start_time = get_test_datetime()
        end_time = get_future_datetime(hours=1)

        adapter._fetch_history = AsyncMock(return_value=MOCK_CLIMATE_HISTORY_RESPONSE[0])

        result = await adapter.fetch_historical_data(
            "climate.living_room", HistoricalDataKey.HEATING_STATE, start_time, end_time
        )

        measurements = result.data[HistoricalDataKey.HEATING_STATE]
        assert measurements[0].value == "heating"
        assert measurements[1].value == "heating"
        assert measurements[2].value == "idle"

    @pytest.mark.asyncio
    async def test_fetch_historical_data_skips_unsupported_key(self, adapter):
        """Return empty dataset when data_key is unsupported."""
        start_time = get_test_datetime()
        end_time = get_future_datetime(hours=1)

        adapter._fetch_history = AsyncMock(return_value=MOCK_CLIMATE_HISTORY_RESPONSE[0])

        result = await adapter.fetch_historical_data(
            "climate.living_room", HistoricalDataKey.OUTDOOR_TEMP, start_time, end_time
        )

        assert result.data == {}

    @pytest.mark.asyncio
    async def test_fetch_historical_data_returns_empty_when_no_history(self, adapter):
        """Return empty dataset when no history is found."""
        start_time = get_test_datetime()
        end_time = get_future_datetime(hours=1)

        adapter._fetch_history = AsyncMock(return_value=[])

        result = await adapter.fetch_historical_data(
            "climate.living_room", HistoricalDataKey.INDOOR_TEMP, start_time, end_time
        )

        assert result.data == {}

    @pytest.mark.asyncio
    async def test_fetch_historical_data_raises_value_error_on_fetch_failure(self, adapter):
        """Raise ValueError when history retrieval fails."""
        start_time = get_test_datetime()
        end_time = get_future_datetime(hours=1)

        adapter._fetch_history = AsyncMock(side_effect=RuntimeError("boom"))

        with pytest.raises(ValueError, match="Cannot fetch history for entity"):
            await adapter.fetch_historical_data(
                "climate.living_room",
                HistoricalDataKey.INDOOR_TEMP,
                start_time,
                end_time,
            )


def test_parse_timestamp_handles_iso_strings() -> None:
    """Parse ISO strings with timezone markers."""
    record_plus = {"last_changed": "2024-01-15T12:00:00+00:00"}
    record_zulu = {"last_changed": "2024-01-15T12:00:00Z"}

    assert ClimateDataAdapter._parse_timestamp(record_plus) == datetime(2024, 1, 15, 12, 0, 0)
    assert ClimateDataAdapter._parse_timestamp(record_zulu) == datetime(2024, 1, 15, 12, 0, 0)


def test_parse_timestamp_returns_datetime_when_already_datetime() -> None:
    """Return datetime values as-is."""
    now = datetime(2024, 1, 15, 12, 0, 0)

    assert ClimateDataAdapter._parse_timestamp({"last_changed": now}) == now


def test_parse_timestamp_falls_back_to_now() -> None:
    """Fallback to now when no timestamp is present."""
    fixed_now = datetime(2024, 1, 15, 12, 0, 0)

    class _FakeDatetime:
        @staticmethod
        def fromisoformat(value: str) -> datetime:
            return datetime.fromisoformat(value)

        @staticmethod
        def now() -> datetime:
            return fixed_now

    with patch(
        "custom_components.intelligent_heating_pilot.infrastructure.adapters.climate_data_adapter.datetime",
        _FakeDatetime,
    ):
        assert ClimateDataAdapter._parse_timestamp({}) == fixed_now


def test_safe_float_returns_float() -> None:
    """Convert valid values to float."""
    assert ClimateDataAdapter._safe_float("12.5") == 12.5


def test_safe_float_returns_none_on_invalid() -> None:
    """Return None for invalid float values."""
    assert ClimateDataAdapter._safe_float("bad") is None
    assert ClimateDataAdapter._safe_float(None) is None
