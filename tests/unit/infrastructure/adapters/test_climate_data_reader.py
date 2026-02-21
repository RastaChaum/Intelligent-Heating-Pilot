"""Tests for HAClimateDataReader adapter (unified real-time + historical)."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from custom_components.intelligent_heating_pilot.domain.value_objects import (
    HistoricalDataKey,
    HistoricalDataSet,
)
from custom_components.intelligent_heating_pilot.infrastructure.adapters.climate_data_reader import (
    HAClimateDataReader,
)
from custom_components.intelligent_heating_pilot.infrastructure.adapters.generic_climate_attribute_mapper import (
    GenericClimateAttributeMapper,
)
from custom_components.intelligent_heating_pilot.infrastructure.recorder_queue import (
    RecorderAccessQueue,
)
from tests.unit.domain.fixtures import (
    MOCK_CLIMATE_HISTORY_RESPONSE,
    TEST_ENTITY_ID,
    get_future_datetime,
    get_test_datetime,
)


@pytest.fixture
def mock_hass() -> Mock:
    """Create a mock Home Assistant instance."""
    hass = Mock()
    hass.states.get = Mock()
    return hass


@pytest.fixture
def recorder_queue() -> RecorderAccessQueue:
    """Create a RecorderAccessQueue."""
    return RecorderAccessQueue()


@pytest.fixture
def reader(mock_hass: Mock, recorder_queue: RecorderAccessQueue) -> HAClimateDataReader:
    """Create a HAClimateDataReader with mocked mapper registry."""
    reader = HAClimateDataReader(mock_hass, recorder_queue, TEST_ENTITY_ID)

    # Replace the mapper registry with a mock that returns our test mapper
    # This avoids the real entity detection process while using real mapping logic
    mock_registry = MagicMock()
    real_mapper = GenericClimateAttributeMapper(mock_hass)
    mock_registry.get_mapper_for_entity.return_value = real_mapper
    reader._mapper_registry = mock_registry

    return reader


def _make_state(state_value: str | None = None, attributes: dict | None = None) -> Mock:
    state = Mock()
    state.state = state_value
    state.attributes = attributes or {}
    return state


# ===========================================================================
# Real-time state tests (IClimateDataReader)
# ===========================================================================


def test_get_vtherm_entity_id(mock_hass: Mock, recorder_queue: RecorderAccessQueue) -> None:
    """Return the configured VTherm entity ID."""
    reader = HAClimateDataReader(mock_hass, recorder_queue, "climate.vtherm")

    assert reader.get_vtherm_entity_id() == "climate.vtherm"


def test_get_current_slope_returns_float(
    mock_hass: Mock, recorder_queue: RecorderAccessQueue
) -> None:
    """Return slope value when available."""
    vtherm_state = _make_state(attributes={"slope": "0.75"})
    mock_hass.states.get.return_value = vtherm_state

    reader = HAClimateDataReader(mock_hass, recorder_queue, "climate.vtherm")

    assert reader.get_current_slope() == 0.75


def test_get_current_slope_returns_none_on_invalid(
    mock_hass: Mock, recorder_queue: RecorderAccessQueue
) -> None:
    """Return None when slope is invalid."""
    vtherm_state = _make_state(attributes={"slope": "bad"})
    mock_hass.states.get.return_value = vtherm_state

    reader = HAClimateDataReader(mock_hass, recorder_queue, "climate.vtherm")

    assert reader.get_current_slope() is None


def test_is_heating_active_true_when_heat_and_below_target(
    mock_hass: Mock, recorder_queue: RecorderAccessQueue
) -> None:
    """Return True when heating is active and below target."""
    vtherm_state = _make_state(
        state_value="heat",
        attributes={"current_temperature": 19.0, "temperature": 21.0},
    )
    mock_hass.states.get.return_value = vtherm_state

    reader = HAClimateDataReader(mock_hass, recorder_queue, "climate.vtherm")

    assert reader.is_heating_active() is True


def test_is_heating_active_false_when_not_heating_mode(
    mock_hass: Mock, recorder_queue: RecorderAccessQueue
) -> None:
    """Return False when HVAC mode is not heat."""
    vtherm_state = _make_state(
        state_value="off",
        attributes={"current_temperature": 19.0, "temperature": 21.0},
    )
    mock_hass.states.get.return_value = vtherm_state

    reader = HAClimateDataReader(mock_hass, recorder_queue, "climate.vtherm")

    assert reader.is_heating_active() is False


def test_is_heating_active_false_when_at_or_above_target(
    mock_hass: Mock, recorder_queue: RecorderAccessQueue
) -> None:
    """Return False when current temperature is at or above target."""
    vtherm_state = _make_state(
        state_value="heat",
        attributes={"current_temperature": 21.0, "temperature": 21.0},
    )
    mock_hass.states.get.return_value = vtherm_state

    reader = HAClimateDataReader(mock_hass, recorder_queue, "climate.vtherm")

    assert reader.is_heating_active() is False


# ===========================================================================
# Historical data tests (IHistoricalDataAdapter) — fetch_historical_data
# ===========================================================================


class TestFetchHistoricalData:
    """Tests for fetch_historical_data covering data extraction, error handling,
    and RecorderAccessQueue usage."""

    @pytest.mark.asyncio
    async def test_returns_historical_dataset(self, reader: HAClimateDataReader) -> None:
        """Return a HistoricalDataSet when data exists."""
        start_time = get_test_datetime()
        end_time = get_future_datetime(hours=1)

        reader._fetch_history = AsyncMock(return_value=MOCK_CLIMATE_HISTORY_RESPONSE[0])

        result = await reader.fetch_historical_data(
            TEST_ENTITY_ID, HistoricalDataKey.INDOOR_TEMP, start_time, end_time
        )

        assert isinstance(result, HistoricalDataSet)
        assert HistoricalDataKey.INDOOR_TEMP in result.data
        assert len(result.data[HistoricalDataKey.INDOOR_TEMP]) == 3

    @pytest.mark.asyncio
    async def test_extracts_indoor_temp(self, reader: HAClimateDataReader) -> None:
        """Extract indoor temperature from current_temperature attribute."""
        start_time = get_test_datetime()
        end_time = get_future_datetime(hours=1)

        reader._fetch_history = AsyncMock(return_value=MOCK_CLIMATE_HISTORY_RESPONSE[0])

        result = await reader.fetch_historical_data(
            TEST_ENTITY_ID, HistoricalDataKey.INDOOR_TEMP, start_time, end_time
        )

        measurements = result.data[HistoricalDataKey.INDOOR_TEMP]
        assert measurements[0].value == 18.0
        assert measurements[1].value == 19.0
        assert measurements[2].value == 21.0

    @pytest.mark.asyncio
    async def test_extracts_target_temperature(self, reader: HAClimateDataReader) -> None:
        """Extract target temperature from target_temperature attribute."""
        start_time = get_test_datetime()
        end_time = get_future_datetime(hours=1)

        reader._fetch_history = AsyncMock(return_value=MOCK_CLIMATE_HISTORY_RESPONSE[0])

        result = await reader.fetch_historical_data(
            TEST_ENTITY_ID, HistoricalDataKey.TARGET_TEMP, start_time, end_time
        )

        measurements = result.data[HistoricalDataKey.TARGET_TEMP]
        assert measurements[0].value == 21.0
        assert measurements[1].value == 21.0
        assert measurements[2].value == 21.0

    @pytest.mark.asyncio
    async def test_prefers_temperature_attribute(self, reader: HAClimateDataReader) -> None:
        """Use temperature attribute when available before target_temperature."""
        start_time = get_test_datetime()
        end_time = get_future_datetime(hours=1)
        custom_records = [
            {
                "entity_id": TEST_ENTITY_ID,
                "state": "heat",
                "attributes": {"temperature": 22.5, "target_temperature": 20.0},
                "last_changed": "2024-01-15T12:00:00+00:00",
            }
        ]

        reader._fetch_history = AsyncMock(return_value=custom_records)

        result = await reader.fetch_historical_data(
            TEST_ENTITY_ID, HistoricalDataKey.TARGET_TEMP, start_time, end_time
        )

        measurements = result.data[HistoricalDataKey.TARGET_TEMP]
        assert measurements[0].value == 22.5

    @pytest.mark.asyncio
    async def test_extracts_heating_state(self, reader: HAClimateDataReader) -> None:
        """Extract hvac_action values when requested."""
        start_time = get_test_datetime()
        end_time = get_future_datetime(hours=1)

        reader._fetch_history = AsyncMock(return_value=MOCK_CLIMATE_HISTORY_RESPONSE[0])

        result = await reader.fetch_historical_data(
            TEST_ENTITY_ID, HistoricalDataKey.HEATING_STATE, start_time, end_time
        )

        measurements = result.data[HistoricalDataKey.HEATING_STATE]
        assert measurements[0].value == "heating"
        assert measurements[1].value == "heating"
        assert measurements[2].value == "idle"

    @pytest.mark.asyncio
    async def test_skips_unsupported_concept(self, reader: HAClimateDataReader) -> None:
        """Return empty dataset when data_key maps to unsupported concept."""
        start_time = get_test_datetime()
        end_time = get_future_datetime(hours=1)

        reader._fetch_history = AsyncMock(return_value=MOCK_CLIMATE_HISTORY_RESPONSE[0])

        result = await reader.fetch_historical_data(
            TEST_ENTITY_ID, HistoricalDataKey.OUTDOOR_TEMP, start_time, end_time
        )

        assert result.data == {}

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_history(self, reader: HAClimateDataReader) -> None:
        """Return empty dataset when no history is found."""
        start_time = get_test_datetime()
        end_time = get_future_datetime(hours=1)

        reader._fetch_history = AsyncMock(return_value=[])

        result = await reader.fetch_historical_data(
            TEST_ENTITY_ID, HistoricalDataKey.INDOOR_TEMP, start_time, end_time
        )

        assert result.data == {}

    @pytest.mark.asyncio
    async def test_raises_value_error_on_fetch_failure(
        self, reader: HAClimateDataReader
    ) -> None:
        """Raise ValueError when history retrieval fails."""
        start_time = get_test_datetime()
        end_time = get_future_datetime(hours=1)

        reader._fetch_history = AsyncMock(side_effect=RuntimeError("boom"))

        with pytest.raises(ValueError, match="Cannot fetch history for entity"):
            await reader.fetch_historical_data(
                TEST_ENTITY_ID,
                HistoricalDataKey.INDOOR_TEMP,
                start_time,
                end_time,
            )

    @pytest.mark.asyncio
    async def test_raises_value_error_on_mapper_failure(
        self, reader: HAClimateDataReader
    ) -> None:
        """Raise ValueError when mapper selection fails."""
        start_time = get_test_datetime()
        end_time = get_future_datetime(hours=1)

        reader._mapper_registry.get_mapper_for_entity.side_effect = ValueError(
            "Entity not found"
        )

        with pytest.raises(ValueError, match="Entity not found"):
            await reader.fetch_historical_data(
                TEST_ENTITY_ID,
                HistoricalDataKey.INDOOR_TEMP,
                start_time,
                end_time,
            )

    @pytest.mark.asyncio
    async def test_skips_non_numeric_temperature_values(
        self, reader: HAClimateDataReader
    ) -> None:
        """Skip records with non-numeric temperature values."""
        start_time = get_test_datetime()
        end_time = get_future_datetime(hours=1)
        records = [
            {
                "entity_id": TEST_ENTITY_ID,
                "state": "heat",
                "attributes": {"current_temperature": "not_a_number"},
                "last_changed": "2024-01-15T12:00:00+00:00",
            },
            {
                "entity_id": TEST_ENTITY_ID,
                "state": "heat",
                "attributes": {"current_temperature": 20.0},
                "last_changed": "2024-01-15T12:15:00+00:00",
            },
        ]

        reader._fetch_history = AsyncMock(return_value=records)

        result = await reader.fetch_historical_data(
            TEST_ENTITY_ID, HistoricalDataKey.INDOOR_TEMP, start_time, end_time
        )

        # Only the valid record should remain
        measurements = result.data[HistoricalDataKey.INDOOR_TEMP]
        assert len(measurements) == 1
        assert measurements[0].value == 20.0

    @pytest.mark.asyncio
    async def test_stores_recorder_queue(
        self,
        mock_hass: Mock,
        recorder_queue: RecorderAccessQueue,
    ) -> None:
        """RecorderAccessQueue is stored and used in _fetch_history."""
        rdr = HAClimateDataReader(mock_hass, recorder_queue, TEST_ENTITY_ID)
        assert rdr._recorder_queue is recorder_queue


# ===========================================================================
# Timestamp parsing tests
# ===========================================================================


def test_parse_timestamp_handles_iso_strings() -> None:
    """Parse ISO strings with timezone markers."""
    record_plus = {"last_changed": "2024-01-15T12:00:00+00:00"}
    record_zulu = {"last_changed": "2024-01-15T12:00:00Z"}

    assert HAClimateDataReader._parse_timestamp(record_plus) == datetime(2024, 1, 15, 12, 0, 0)
    assert HAClimateDataReader._parse_timestamp(record_zulu) == datetime(2024, 1, 15, 12, 0, 0)


def test_parse_timestamp_returns_datetime_when_already_datetime() -> None:
    """Return datetime values as-is."""
    now = datetime(2024, 1, 15, 12, 0, 0)

    assert HAClimateDataReader._parse_timestamp({"last_changed": now}) == now


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
        "custom_components.intelligent_heating_pilot.infrastructure.adapters.climate_data_reader.datetime",
        _FakeDatetime,
    ):
        assert HAClimateDataReader._parse_timestamp({}) == fixed_now


# ===========================================================================
# Float conversion safety tests
# ===========================================================================


def test_safe_float_returns_float() -> None:
    """Convert valid values to float."""
    assert HAClimateDataReader._safe_float("12.5") == 12.5


def test_safe_float_returns_none_on_invalid() -> None:
    """Return None for invalid float values."""
    assert HAClimateDataReader._safe_float("bad") is None
    assert HAClimateDataReader._safe_float(None) is None
