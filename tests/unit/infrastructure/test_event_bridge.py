"""Unit tests for HAEventBridge smart filtering logic."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from custom_components.intelligent_heating_pilot.infrastructure.event_bridge import (
    HAEventBridge,
    _MONITORED_ENTITY_CHANGE_THRESHOLD,
    _ANTICIPATION_TIME_TOLERANCE_SECONDS,
)


# ---------------------------------------------------------------------------
# Helpers
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
    app_service = AsyncMock()
    return HAEventBridge(
        hass=hass,
        application_service=app_service,
        vtherm_entity_id=kwargs.get("vtherm_entity_id", "climate.vtherm"),
        scheduler_entity_ids=kwargs.get("scheduler_entity_ids", ["switch.schedule_1"]),
        monitored_entity_ids=kwargs.get("monitored_entity_ids", []),
        entry_id=kwargs.get("entry_id", "entry_abc"),
    )


# ---------------------------------------------------------------------------
# _has_meaningful_scheduler_change
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# _has_meaningful_monitored_change
# ---------------------------------------------------------------------------

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
        event = _make_event(
            "sensor.humidity",
            _make_state("65.0"),
            _make_state("65.1"),
        )
        assert bridge._has_meaningful_monitored_change(event) is False

    def test_become_unavailable_is_meaningful(self):
        bridge = _make_bridge()
        event = _make_event(
            "sensor.humidity",
            _make_state("65.0"),
            _make_state("unavailable"),
        )
        assert bridge._has_meaningful_monitored_change(event) is True

    def test_recover_from_unavailable_is_meaningful(self):
        bridge = _make_bridge()
        event = _make_event(
            "sensor.humidity",
            _make_state("unavailable"),
            _make_state("65.0"),
        )
        assert bridge._has_meaningful_monitored_change(event) is True

    def test_still_unavailable_is_not_meaningful(self):
        bridge = _make_bridge()
        event = _make_event(
            "sensor.humidity",
            _make_state("unavailable"),
            _make_state("unknown"),
        )
        # Both unavailable-family states → no meaningful change
        assert bridge._has_meaningful_monitored_change(event) is False

    def test_non_numeric_state_change_is_meaningful(self):
        bridge = _make_bridge()
        event = _make_event("sensor.cloud", _make_state("clear"), _make_state("overcast"))
        assert bridge._has_meaningful_monitored_change(event) is True

    def test_same_non_numeric_state_is_not_meaningful(self):
        bridge = _make_bridge()
        event = _make_event("sensor.cloud", _make_state("clear"), _make_state("clear"))
        assert bridge._has_meaningful_monitored_change(event) is False


# ---------------------------------------------------------------------------
# _is_meaningful_change_from_last
# ---------------------------------------------------------------------------

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
        new_data["learned_heating_slope"] = 2.0 + 0.05  # exactly at threshold
        assert bridge._is_meaningful_change_from_last(new_data) is True

    def test_lhs_change_below_threshold_is_not_meaningful(self):
        bridge = _make_bridge()
        bridge._last_published_data = self._base_data()
        new_data = dict(self._base_data())
        new_data["learned_heating_slope"] = 2.0 + 0.01  # below threshold
        assert bridge._is_meaningful_change_from_last(new_data) is False

    def test_anticipated_start_change_above_tolerance_is_meaningful(self):
        """Change > 60 s in anticipated_start_time must be considered meaningful."""
        bridge = _make_bridge()
        bridge._last_published_data = self._base_data()
        new_data = dict(self._base_data())
        # Advance by exactly _ANTICIPATION_TIME_TOLERANCE_SECONDS
        new_data["anticipated_start_time"] = "2025-01-01T06:31:00+00:00"  # +60 s
        assert bridge._is_meaningful_change_from_last(new_data) is True

    def test_anticipated_start_change_below_tolerance_is_not_meaningful(self):
        """Change < 60 s in anticipated_start_time should be suppressed."""
        bridge = _make_bridge()
        bridge._last_published_data = self._base_data()
        new_data = dict(self._base_data())
        new_data["anticipated_start_time"] = "2025-01-01T06:30:30+00:00"  # +30 s
        assert bridge._is_meaningful_change_from_last(new_data) is False


# ---------------------------------------------------------------------------
# _recalculate_and_publish – deduplication integration
# ---------------------------------------------------------------------------

class TestRecalculateAndPublishDeduplication:
    """Verify that _recalculate_and_publish skips firing when data is unchanged."""

    def _bridge_with_app_service(self, anticipation_data):
        hass = Mock()
        hass.bus = Mock()
        app_service = AsyncMock()
        app_service.calculate_and_schedule_anticipation = AsyncMock(
            return_value=anticipation_data
        )
        bridge = HAEventBridge(
            hass=hass,
            application_service=app_service,
            vtherm_entity_id="climate.vtherm",
            scheduler_entity_ids=["switch.schedule_1"],
            entry_id="entry_abc",
        )
        return bridge

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
        bridge = self._bridge_with_app_service(data)
        await bridge._recalculate_and_publish()
        bridge._hass.bus.async_fire.assert_called_once()

    @pytest.mark.asyncio
    async def test_identical_second_call_is_skipped(self):
        data = self._anticipation_data()
        bridge = self._bridge_with_app_service(data)
        await bridge._recalculate_and_publish()
        bridge._hass.bus.async_fire.reset_mock()
        # Second call with the same data
        await bridge._recalculate_and_publish()
        bridge._hass.bus.async_fire.assert_not_called()

    @pytest.mark.asyncio
    async def test_clear_event_only_fires_once(self):
        bridge = self._bridge_with_app_service(None)
        await bridge._recalculate_and_publish()
        bridge._hass.bus.async_fire.assert_called_once()
        bridge._hass.bus.async_fire.reset_mock()
        # Second call still returns None – should NOT fire again
        await bridge._recalculate_and_publish()
        bridge._hass.bus.async_fire.assert_not_called()

    @pytest.mark.asyncio
    async def test_clear_then_data_fires_again(self):
        """After a clear event, the next data event must always be published."""
        bridge = self._bridge_with_app_service(None)
        await bridge._recalculate_and_publish()

        # Swap to returning actual data
        data = self._anticipation_data()
        bridge._app_service.calculate_and_schedule_anticipation = AsyncMock(
            return_value=data
        )
        bridge._hass.bus.async_fire.reset_mock()
        await bridge._recalculate_and_publish()
        bridge._hass.bus.async_fire.assert_called_once()
