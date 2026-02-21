"""Unit tests for HAEventBridge smart filtering and deduplication logic.

Two layers of tests:
- Pure unit tests (no HA): test the filter helpers and deduplication logic in isolation.
- Integration-style tests (with ``hass`` fixture): test the full event-bridge behavior
  against a real HA event bus, including regression coverage for bug #81.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.intelligent_heating_pilot.application import HeatingOrchestrator
from custom_components.intelligent_heating_pilot.infrastructure.event_bridge import (
    HAEventBridge,
    _ANTICIPATION_TIME_TOLERANCE_SECONDS,
    _MONITORED_ENTITY_CHANGE_THRESHOLD,
)


# ---------------------------------------------------------------------------
# Pure-unit helpers (no hass)
# ---------------------------------------------------------------------------

def _make_state(state_str: str, attributes: dict | None = None) -> Mock:
    """Return a lightweight mock of a HA State object."""
    s = Mock()
    s.state = state_str
    s.attributes = attributes or {}
    return s


def _make_event(entity_id: str, old_state, new_state) -> Mock:
    """Build a fake EventStateChangedData-style event."""
    event = Mock()
    event.data = {
        "entity_id": entity_id,
        "old_state": old_state,
        "new_state": new_state,
    }
    return event


def _make_bridge(**kwargs) -> HAEventBridge:
    """Create an HAEventBridge with sensible defaults for unit testing."""
    hass = Mock()
    hass.bus = Mock()
    orchestrator = AsyncMock()
    return HAEventBridge(
        hass=hass,
        orchestrator=orchestrator,
        vtherm_entity_id=kwargs.get("vtherm_entity_id", "climate.vtherm"),
        scheduler_entity_ids=kwargs.get("scheduler_entity_ids", ["switch.schedule_1"]),
        monitored_entity_ids=kwargs.get("monitored_entity_ids", []),
        entry_id=kwargs.get("entry_id", "entry_abc"),
    )


# ---------------------------------------------------------------------------
# Integration-style fixtures (with hass)
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_orchestrator() -> Mock:
    """Create mock orchestrator with default None response."""
    service = Mock(spec=HeatingOrchestrator)
    service.calculate_and_schedule_anticipation = AsyncMock(return_value=None)
    return service


@pytest.fixture
def get_ihp_enabled_mock() -> Mock:
    """Create mock get_ihp_enabled callback (default: enabled)."""
    return Mock(return_value=True)


@pytest.fixture
def event_bridge(
    hass: HomeAssistant,
    mock_orchestrator: Mock,
    get_ihp_enabled_mock: Mock,
) -> HAEventBridge:
    """Create HAEventBridge instance for integration-style tests."""
    return HAEventBridge(
        hass=hass,
        orchestrator=mock_orchestrator,
        vtherm_entity_id="climate.bedroom",
        scheduler_entity_ids=["switch.bedroom_schedule"],
        monitored_entity_ids=["sensor.bedroom_humidity", "sensor.cloud_coverage"],
        entry_id="test_entry",
        get_ihp_enabled_func=get_ihp_enabled_mock,
    )


def _full_anticipation_data(
    anticipated_start_time: datetime | None = None,
    next_schedule_time: datetime | None = None,
) -> dict:
    """Create a complete anticipation data dict (successful case)."""
    now = datetime.now(timezone.utc)
    return {
        "anticipated_start_time": anticipated_start_time or now + timedelta(minutes=30),
        "next_schedule_time": next_schedule_time or now + timedelta(hours=1),
        "next_target_temperature": 21.0,
        "anticipation_minutes": 30.0,
        "current_temp": 18.5,
        "learned_heating_slope": 2.5,
        "confidence_level": 85.0,
        "scheduler_entity": "switch.bedroom_schedule",
    }


def _partial_anticipation_data(
    current_temp: float | None = 18.5,
    learned_heating_slope: float | None = 2.5,
) -> dict:
    """Create a partial anticipation data dict (minimal values, None schedule fields)."""
    return {
        "anticipated_start_time": None,
        "next_schedule_time": None,
        "next_target_temperature": None,
        "anticipation_minutes": None,
        "current_temp": current_temp,
        "learned_heating_slope": learned_heating_slope,
        "confidence_level": None,
        "scheduler_entity": None,
    }


# ===========================================================================
# _has_meaningful_scheduler_change
# ===========================================================================

class TestHasMeaningfulSchedulerChange:
    """Tests for scheduler entity change filtering."""

    def test_no_old_state_is_meaningful(self):
        bridge = _make_bridge()
        event = _make_event("switch.schedule_1", None, _make_state("on"))
        assert bridge._has_meaningful_scheduler_change(event) is True

    def test_no_new_state_is_meaningful(self):
        bridge = _make_bridge()
        event = _make_event("switch.schedule_1", _make_state("on"), None)
        assert bridge._has_meaningful_scheduler_change(event) is True

    def test_enabled_to_disabled_is_meaningful(self):
        bridge = _make_bridge()
        event = _make_event(
            "switch.schedule_1",
            _make_state("on", {"next_trigger": "2025-01-01T07:00:00+00:00", "actions": []}),
            _make_state("off", {"next_trigger": "2025-01-01T07:00:00+00:00", "actions": []}),
        )
        assert bridge._has_meaningful_scheduler_change(event) is True

    def test_next_trigger_changed_is_meaningful(self):
        bridge = _make_bridge()
        event = _make_event(
            "switch.schedule_1",
            _make_state("on", {"next_trigger": "2025-01-01T07:00:00+00:00", "actions": []}),
            _make_state("on", {"next_trigger": "2025-01-01T08:00:00+00:00", "actions": []}),
        )
        assert bridge._has_meaningful_scheduler_change(event) is True

    def test_actions_changed_is_meaningful(self):
        bridge = _make_bridge()
        old_actions = [{"entity_id": "climate.vtherm", "service_data": {"temperature": 19}}]
        new_actions = [{"entity_id": "climate.vtherm", "service_data": {"temperature": 21}}]
        event = _make_event(
            "switch.schedule_1",
            _make_state("on", {"next_trigger": "2025-01-01T07:00:00+00:00", "actions": old_actions}),
            _make_state("on", {"next_trigger": "2025-01-01T07:00:00+00:00", "actions": new_actions}),
        )
        assert bridge._has_meaningful_scheduler_change(event) is True

    def test_irrelevant_attribute_change_is_not_meaningful(self):
        """Updating last_triggered or other internal counters must be ignored."""
        bridge = _make_bridge()
        actions = [{"entity_id": "climate.vtherm", "service_data": {"temperature": 21}}]
        event = _make_event(
            "switch.schedule_1",
            _make_state("on", {
                "next_trigger": "2025-01-01T07:00:00+00:00",
                "actions": actions,
                "last_triggered": "2025-01-01T06:55:00+00:00",
            }),
            _make_state("on", {
                "next_trigger": "2025-01-01T07:00:00+00:00",
                "actions": actions,
                "last_triggered": "2025-01-01T07:00:00+00:00",
            }),
        )
        assert bridge._has_meaningful_scheduler_change(event) is False

    def test_no_change_at_all_is_not_meaningful(self):
        bridge = _make_bridge()
        attrs = {"next_trigger": "2025-01-01T07:00:00+00:00", "actions": []}
        event = _make_event(
            "switch.schedule_1",
            _make_state("on", attrs),
            _make_state("on", attrs),
        )
        assert bridge._has_meaningful_scheduler_change(event) is False


# ===========================================================================
# _has_meaningful_monitored_change
# ===========================================================================

class TestHasMeaningfulMonitoredChange:
    """Tests for monitored entity (humidity / cloud coverage) change filtering."""

    def test_no_old_state_is_meaningful(self):
        bridge = _make_bridge()
        event = _make_event("sensor.humidity", None, _make_state("65.0"))
        assert bridge._has_meaningful_monitored_change(event) is True

    def test_no_new_state_is_meaningful(self):
        bridge = _make_bridge()
        event = _make_event("sensor.humidity", _make_state("65.0"), None)
        assert bridge._has_meaningful_monitored_change(event) is True

    def test_large_change_is_meaningful(self):
        bridge = _make_bridge()
        event = _make_event(
            "sensor.humidity",
            _make_state("60.0"),
            _make_state(str(60.0 + _MONITORED_ENTITY_CHANGE_THRESHOLD + 0.1)),
        )
        assert bridge._has_meaningful_monitored_change(event) is True

    def test_change_exactly_at_threshold_is_meaningful(self):
        bridge = _make_bridge()
        event = _make_event(
            "sensor.humidity",
            _make_state("60.0"),
            _make_state(str(60.0 + _MONITORED_ENTITY_CHANGE_THRESHOLD)),
        )
        assert bridge._has_meaningful_monitored_change(event) is True

    def test_small_change_is_not_meaningful(self):
        bridge = _make_bridge()
        event = _make_event("sensor.humidity", _make_state("65.0"), _make_state("65.1"))
        assert bridge._has_meaningful_monitored_change(event) is False

    def test_become_unavailable_is_meaningful(self):
        bridge = _make_bridge()
        event = _make_event("sensor.humidity", _make_state("65.0"), _make_state("unavailable"))
        assert bridge._has_meaningful_monitored_change(event) is True

    def test_recover_from_unavailable_is_meaningful(self):
        bridge = _make_bridge()
        event = _make_event("sensor.humidity", _make_state("unavailable"), _make_state("65.0"))
        assert bridge._has_meaningful_monitored_change(event) is True

    def test_still_unavailable_is_not_meaningful(self):
        bridge = _make_bridge()
        event = _make_event("sensor.humidity", _make_state("unavailable"), _make_state("unknown"))
        assert bridge._has_meaningful_monitored_change(event) is False

    def test_non_numeric_state_change_is_meaningful(self):
        bridge = _make_bridge()
        event = _make_event("sensor.cloud", _make_state("clear"), _make_state("overcast"))
        assert bridge._has_meaningful_monitored_change(event) is True

    def test_same_non_numeric_state_is_not_meaningful(self):
        bridge = _make_bridge()
        event = _make_event("sensor.cloud", _make_state("clear"), _make_state("clear"))
        assert bridge._has_meaningful_monitored_change(event) is False


# ===========================================================================
# _is_meaningful_change_from_last
# ===========================================================================

class TestIsMeaningfulChangeFromLast:
    """Tests for output-data deduplication logic."""

    def _base_data(self) -> dict:
        return {
            "entry_id": "entry_abc",
            "anticipated_start_time": "2025-01-01T06:30:00+00:00",
            "next_schedule_time": "2025-01-01T07:00:00+00:00",
            "next_target_temperature": 21.0,
            "anticipation_minutes": 30.0,
            "current_temp": 18.5,
            "learned_heating_slope": 2.0,
            "confidence_level": 0.8,
            "scheduler_entity": "switch.schedule_1",
        }

    def test_no_last_data_is_meaningful(self):
        bridge = _make_bridge()
        assert bridge._is_meaningful_change_from_last(self._base_data()) is True

    def test_identical_data_is_not_meaningful(self):
        bridge = _make_bridge()
        data = self._base_data()
        bridge._last_published_data = dict(data)
        assert bridge._is_meaningful_change_from_last(data) is False

    def test_schedule_time_change_is_meaningful(self):
        bridge = _make_bridge()
        bridge._last_published_data = self._base_data()
        new_data = dict(self._base_data())
        new_data["next_schedule_time"] = "2025-01-01T08:00:00+00:00"
        assert bridge._is_meaningful_change_from_last(new_data) is True

    def test_target_temp_change_is_meaningful(self):
        bridge = _make_bridge()
        bridge._last_published_data = self._base_data()
        new_data = dict(self._base_data())
        new_data["next_target_temperature"] = 22.0
        assert bridge._is_meaningful_change_from_last(new_data) is True

    def test_scheduler_entity_change_is_meaningful(self):
        bridge = _make_bridge()
        bridge._last_published_data = self._base_data()
        new_data = dict(self._base_data())
        new_data["scheduler_entity"] = "switch.schedule_2"
        assert bridge._is_meaningful_change_from_last(new_data) is True

    def test_current_temp_change_above_threshold_is_meaningful(self):
        bridge = _make_bridge()
        bridge._last_published_data = self._base_data()
        new_data = dict(self._base_data())
        new_data["current_temp"] = 18.5 + 0.1  # exactly at threshold
        assert bridge._is_meaningful_change_from_last(new_data) is True

    def test_current_temp_change_below_threshold_is_not_meaningful(self):
        bridge = _make_bridge()
        bridge._last_published_data = self._base_data()
        new_data = dict(self._base_data())
        new_data["current_temp"] = 18.5 + 0.05  # below threshold
        assert bridge._is_meaningful_change_from_last(new_data) is False

    def test_lhs_change_above_threshold_is_meaningful(self):
        bridge = _make_bridge()
        bridge._last_published_data = self._base_data()
        new_data = dict(self._base_data())
        new_data["learned_heating_slope"] = 2.0 + 0.06  # above threshold (avoid fp boundary)
        assert bridge._is_meaningful_change_from_last(new_data) is True

    def test_lhs_change_below_threshold_is_not_meaningful(self):
        bridge = _make_bridge()
        bridge._last_published_data = self._base_data()
        new_data = dict(self._base_data())
        new_data["learned_heating_slope"] = 2.0 + 0.01  # below threshold
        assert bridge._is_meaningful_change_from_last(new_data) is False

    def test_anticipated_start_change_above_tolerance_is_meaningful(self):
        """Change >= 60 s in anticipated_start_time must be considered meaningful."""
        bridge = _make_bridge()
        bridge._last_published_data = self._base_data()
        new_data = dict(self._base_data())
        new_data["anticipated_start_time"] = "2025-01-01T06:31:00+00:00"  # +60 s
        assert bridge._is_meaningful_change_from_last(new_data) is True

    def test_anticipated_start_change_below_tolerance_is_not_meaningful(self):
        """Change < 60 s in anticipated_start_time should be suppressed."""
        bridge = _make_bridge()
        bridge._last_published_data = self._base_data()
        new_data = dict(self._base_data())
        new_data["anticipated_start_time"] = "2025-01-01T06:30:30+00:00"  # +30 s
        assert bridge._is_meaningful_change_from_last(new_data) is False

    def test_none_to_none_anticipated_start_is_not_meaningful(self):
        """Two identical clear (None) events should not be considered meaningful."""
        bridge = _make_bridge()
        bridge._last_published_data = {
            "anticipated_start_time": None,
            "next_schedule_time": None,
            "next_target_temperature": None,
            "scheduler_entity": None,
            "current_temp": 18.5,
            "learned_heating_slope": 2.0,
        }
        new_data = dict(bridge._last_published_data)
        assert bridge._is_meaningful_change_from_last(new_data) is False

    def test_none_to_value_anticipated_start_is_meaningful(self):
        """Transition from None to an actual start time is meaningful."""
        bridge = _make_bridge()
        bridge._last_published_data = {
            "anticipated_start_time": None,
            "next_schedule_time": None,
            "next_target_temperature": None,
            "scheduler_entity": None,
            "current_temp": 18.5,
            "learned_heating_slope": 2.0,
        }
        new_data = dict(self._base_data())
        assert bridge._is_meaningful_change_from_last(new_data) is True


    # ------------------------------------------------------------------
    # None-transition tests for current_temp and learned_heating_slope
    # ------------------------------------------------------------------

    def test_current_temp_none_to_value_is_meaningful(self):
        """Sensor becoming available (None → value) must be considered meaningful."""
        bridge = _make_bridge()
        base = dict(self._base_data())
        base["current_temp"] = None
        bridge._last_published_data = base
        new_data = dict(self._base_data())
        assert bridge._is_meaningful_change_from_last(new_data) is True

    def test_current_temp_value_to_none_is_meaningful(self):
        """Sensor becoming unavailable (value → None) must be considered meaningful."""
        bridge = _make_bridge()
        bridge._last_published_data = self._base_data()
        new_data = dict(self._base_data())
        new_data["current_temp"] = None
        assert bridge._is_meaningful_change_from_last(new_data) is True

    def test_current_temp_both_none_is_not_meaningful(self):
        """Both current_temp values being None means no change."""
        bridge = _make_bridge()
        base = dict(self._base_data())
        base["current_temp"] = None
        bridge._last_published_data = base
        new_data = dict(base)
        assert bridge._is_meaningful_change_from_last(new_data) is False

    def test_lhs_none_to_value_is_meaningful(self):
        """LHS sensor becoming available (None → value) must be considered meaningful."""
        bridge = _make_bridge()
        base = dict(self._base_data())
        base["learned_heating_slope"] = None
        bridge._last_published_data = base
        new_data = dict(self._base_data())
        assert bridge._is_meaningful_change_from_last(new_data) is True

    def test_lhs_value_to_none_is_meaningful(self):
        """LHS sensor becoming unavailable (value → None) must be considered meaningful."""
        bridge = _make_bridge()
        bridge._last_published_data = self._base_data()
        new_data = dict(self._base_data())
        new_data["learned_heating_slope"] = None
        assert bridge._is_meaningful_change_from_last(new_data) is True

    def test_lhs_both_none_is_not_meaningful(self):
        """Both learned_heating_slope values being None means no change."""
        bridge = _make_bridge()
        base = dict(self._base_data())
        base["learned_heating_slope"] = None
        bridge._last_published_data = base
        new_data = dict(base)
        assert bridge._is_meaningful_change_from_last(new_data) is False


# ===========================================================================
# _recalculate_and_publish – deduplication (pure unit)
# ===========================================================================

class TestRecalculateAndPublishDeduplication:
    """Verify that _recalculate_and_publish deduplicates identical data."""

    def _bridge_with_orchestrator(self, anticipation_data) -> HAEventBridge:
        hass = Mock()
        hass.bus = Mock()
        orchestrator = AsyncMock()
        orchestrator.calculate_and_schedule_anticipation = AsyncMock(
            return_value=anticipation_data
        )
        return HAEventBridge(
            hass=hass,
            orchestrator=orchestrator,
            vtherm_entity_id="climate.vtherm",
            scheduler_entity_ids=["switch.schedule_1"],
            entry_id="entry_abc",
        )

    def _anticipation_data(self) -> dict:
        dt_start = datetime(2025, 1, 1, 6, 30, 0, tzinfo=timezone.utc)
        dt_sched = datetime(2025, 1, 1, 7, 0, 0, tzinfo=timezone.utc)
        return {
            "anticipated_start_time": dt_start,
            "next_schedule_time": dt_sched,
            "next_target_temperature": 21.0,
            "anticipation_minutes": 30.0,
            "current_temp": 18.5,
            "learned_heating_slope": 2.0,
            "confidence_level": 0.8,
            "scheduler_entity": "switch.schedule_1",
        }

    @pytest.mark.asyncio
    async def test_first_call_always_publishes(self):
        data = self._anticipation_data()
        bridge = self._bridge_with_orchestrator(data)
        await bridge._recalculate_and_publish()
        bridge._hass.bus.async_fire.assert_called_once()

    @pytest.mark.asyncio
    async def test_identical_second_call_is_skipped(self):
        data = self._anticipation_data()
        bridge = self._bridge_with_orchestrator(data)
        await bridge._recalculate_and_publish()
        bridge._hass.bus.async_fire.reset_mock()
        await bridge._recalculate_and_publish()
        bridge._hass.bus.async_fire.assert_not_called()

    @pytest.mark.asyncio
    async def test_partial_data_only_fires_once_when_identical(self):
        """With None/partial data, only the first event fires."""
        bridge = self._bridge_with_orchestrator(None)
        await bridge._recalculate_and_publish()
        bridge._hass.bus.async_fire.assert_called_once()
        bridge._hass.bus.async_fire.reset_mock()
        # Second call with same None data → skipped
        await bridge._recalculate_and_publish()
        bridge._hass.bus.async_fire.assert_not_called()

    @pytest.mark.asyncio
    async def test_partial_then_full_data_fires_again(self):
        """After a partial event, the next full-data event must always be published."""
        bridge = self._bridge_with_orchestrator(None)
        await bridge._recalculate_and_publish()

        data = self._anticipation_data()
        bridge._orchestrator.calculate_and_schedule_anticipation = AsyncMock(
            return_value=data
        )
        bridge._hass.bus.async_fire.reset_mock()
        await bridge._recalculate_and_publish()
        bridge._hass.bus.async_fire.assert_called_once()

    @pytest.mark.asyncio
    async def test_published_event_never_contains_clear_values_flag(self):
        """The unified event structure must never include ``clear_values``."""
        bridge = self._bridge_with_orchestrator(None)
        await bridge._recalculate_and_publish()
        call_args = bridge._hass.bus.async_fire.call_args
        event_data = call_args[0][1]
        assert "clear_values" not in event_data
        assert event_data["anticipated_start_time"] is None
        assert event_data["next_schedule_time"] is None

    @pytest.mark.asyncio
    async def test_full_data_event_never_contains_clear_values_flag(self):
        """Full-data events must also not contain the legacy ``clear_values`` flag."""
        data = self._anticipation_data()
        bridge = self._bridge_with_orchestrator(data)
        await bridge._recalculate_and_publish()
        call_args = bridge._hass.bus.async_fire.call_args
        event_data = call_args[0][1]
        assert "clear_values" not in event_data


# ===========================================================================
# Integration-style tests (with hass fixture) – regression for bug #81
#
# These tests verify the full event-bridge pipeline including the HA event bus.
# Because our deduplication layer suppresses identical consecutive data, tests
# that previously expected N fires with N identical recalculations now expect
# only the first fire (subsequent identical data is correctly suppressed).
# ===========================================================================


class TestPartialDataPublishing:
    """Regression tests for bug #81: partial data never triggers KeyError."""

    @pytest.mark.asyncio
    @patch("homeassistant.core.EventBus.async_fire")
    async def test_publishes_partial_event_when_no_scheduler(
        self,
        mock_async_fire: Mock,
        hass: HomeAssistant,
        event_bridge: HAEventBridge,
        mock_orchestrator: Mock,
    ) -> None:
        mock_orchestrator.calculate_and_schedule_anticipation.return_value = (
            _partial_anticipation_data()
        )
        event_bridge.setup_listeners()

        hass.states.async_set("switch.bedroom_schedule", "on")
        await hass.async_block_till_done()

        mock_async_fire.assert_called_once()
        event_data = mock_async_fire.call_args[0][1]
        assert event_data["anticipated_start_time"] is None
        assert event_data["next_schedule_time"] is None
        assert event_data["current_temp"] == 18.5
        assert "clear_values" not in event_data

    @pytest.mark.asyncio
    @patch("homeassistant.core.EventBus.async_fire")
    async def test_none_response_publishes_partial_structure(
        self,
        mock_async_fire: Mock,
        hass: HomeAssistant,
        event_bridge: HAEventBridge,
        mock_orchestrator: Mock,
    ) -> None:
        """None from orchestrator must produce unified structure, not crash."""
        mock_orchestrator.calculate_and_schedule_anticipation.return_value = None
        event_bridge.setup_listeners()

        hass.states.async_set("switch.bedroom_schedule", "on")
        await hass.async_block_till_done()

        mock_async_fire.assert_called_once()
        event_data = mock_async_fire.call_args[0][1]
        assert event_data["anticipated_start_time"] is None
        assert event_data["next_schedule_time"] is None
        assert "clear_values" not in event_data

    @pytest.mark.asyncio
    @patch("homeassistant.core.EventBus.async_fire")
    async def test_scheduler_toggle_with_identical_data_fires_once(
        self,
        mock_async_fire: Mock,
        hass: HomeAssistant,
        event_bridge: HAEventBridge,
        mock_orchestrator: Mock,
    ) -> None:
        """Toggling scheduler with unchanged data fires only once (deduplication)."""
        mock_orchestrator.calculate_and_schedule_anticipation.return_value = (
            _partial_anticipation_data()
        )
        event_bridge.setup_listeners()

        for i in range(3):
            hass.states.async_set("switch.bedroom_schedule", "on" if i % 2 == 0 else "off")
            await hass.async_block_till_done()

        # Deduplication: same data → only the first fire passes
        assert mock_async_fire.call_count == 1
        assert "clear_values" not in mock_async_fire.call_args[0][1]


class TestFullDataPublishing:
    """Tests for complete anticipation data publishing."""

    @pytest.mark.asyncio
    @patch("homeassistant.core.EventBus.async_fire")
    async def test_publishes_full_anticipation_event(
        self,
        mock_async_fire: Mock,
        hass: HomeAssistant,
        event_bridge: HAEventBridge,
        mock_orchestrator: Mock,
    ) -> None:
        full_data = _full_anticipation_data()
        mock_orchestrator.calculate_and_schedule_anticipation.return_value = full_data
        event_bridge.setup_listeners()

        hass.states.async_set("switch.bedroom_schedule", "on")
        await hass.async_block_till_done()

        mock_async_fire.assert_called_once()
        event_data = mock_async_fire.call_args[0][1]
        assert event_data["entry_id"] == "test_entry"
        assert event_data["anticipated_start_time"] == full_data["anticipated_start_time"].isoformat()
        assert event_data["next_schedule_time"] == full_data["next_schedule_time"].isoformat()
        assert event_data["next_target_temperature"] == 21.0
        assert "clear_values" not in event_data

    @pytest.mark.asyncio
    @patch("homeassistant.core.EventBus.async_fire")
    async def test_alternating_partial_and_full_data(
        self,
        mock_async_fire: Mock,
        hass: HomeAssistant,
        event_bridge: HAEventBridge,
        mock_orchestrator: Mock,
    ) -> None:
        """Switching from partial to full data fires again (meaningful change)."""
        event_bridge.setup_listeners()

        mock_orchestrator.calculate_and_schedule_anticipation.return_value = (
            _partial_anticipation_data()
        )
        hass.states.async_set("switch.bedroom_schedule", "on")
        await hass.async_block_till_done()
        assert mock_async_fire.call_count == 1

        mock_async_fire.reset_mock()

        mock_orchestrator.calculate_and_schedule_anticipation.return_value = (
            _full_anticipation_data()
        )
        hass.states.async_set("switch.bedroom_schedule", "off")
        await hass.async_block_till_done()
        assert mock_async_fire.call_count == 1
        assert "clear_values" not in mock_async_fire.call_args[0][1]


class TestIHPEnabledParameter:
    """Test that ihp_enabled is correctly forwarded to the orchestrator."""

    @pytest.mark.asyncio
    async def test_passes_ihp_disabled(
        self,
        hass: HomeAssistant,
        event_bridge: HAEventBridge,
        mock_orchestrator: Mock,
        get_ihp_enabled_mock: Mock,
    ) -> None:
        get_ihp_enabled_mock.return_value = False
        mock_orchestrator.calculate_and_schedule_anticipation.return_value = (
            _partial_anticipation_data()
        )
        event_bridge.setup_listeners()

        hass.states.async_set("switch.bedroom_schedule", "on")
        await hass.async_block_till_done()

        mock_orchestrator.calculate_and_schedule_anticipation.assert_called_once()
        call_kwargs = mock_orchestrator.calculate_and_schedule_anticipation.call_args[1]
        assert call_kwargs["ihp_enabled"] is False

    @pytest.mark.asyncio
    async def test_passes_ihp_enabled(
        self,
        hass: HomeAssistant,
        event_bridge: HAEventBridge,
        mock_orchestrator: Mock,
        get_ihp_enabled_mock: Mock,
    ) -> None:
        get_ihp_enabled_mock.return_value = True
        mock_orchestrator.calculate_and_schedule_anticipation.return_value = (
            _full_anticipation_data()
        )
        event_bridge.setup_listeners()

        hass.states.async_set("switch.bedroom_schedule", "on")
        await hass.async_block_till_done()

        call_kwargs = mock_orchestrator.calculate_and_schedule_anticipation.call_args[1]
        assert call_kwargs["ihp_enabled"] is True
