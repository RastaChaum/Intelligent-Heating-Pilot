"""A wake-up source reaches the event bridge like a scheduler: any change of its value counts."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

from homeassistant.core import CoreState

from custom_components.intelligent_heating_pilot.infrastructure.event_bridge import HAEventBridge

ALARM = "sensor.phone_next_alarm"


def _bridge() -> HAEventBridge:
    hass = Mock()
    hass.state = CoreState.running
    hass.bus = Mock()
    return HAEventBridge(
        hass=hass,
        orchestrator=AsyncMock(),
        climate_entity_id="climate.vtherm",
        scheduler_entity_ids=["switch.plan", ALARM],
        monitored_entity_ids=[],
        entry_id="entry",
    )


def _event(old: str | None, new: str | None, attributes: dict | None = None) -> Mock:
    def state(value: str | None):
        if value is None:
            return None
        s = Mock()
        s.state = value
        s.attributes = attributes or {}
        return s

    event = Mock()
    event.data = {"entity_id": ALARM, "old_state": state(old), "new_state": state(new)}
    return event


def test_a_snooze_is_a_meaningful_change() -> None:
    event = _event("2026-11-17T06:30:00+00:00", "2026-11-17T06:40:00+00:00")

    assert _bridge()._has_meaningful_scheduler_change(event) is True


def test_a_dismissed_alarm_is_a_meaningful_change() -> None:
    assert _bridge()._has_meaningful_scheduler_change(
        _event("2026-11-17T06:30:00+00:00", "unknown")
    )


def test_a_change_of_attributes_only_is_ignored() -> None:
    event = _event("2026-11-17T06:30:00+00:00", "2026-11-17T06:30:00+00:00", {"package": "x"})

    assert _bridge()._has_meaningful_scheduler_change(event) is False


def test_the_source_is_among_the_entities_the_bridge_listens_to() -> None:
    assert ALARM in _bridge()._scheduler_entity_ids
