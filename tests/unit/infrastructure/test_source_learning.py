"""A wake-up deadline is learned like a schedule slot: nothing in the slot history names a scheduler."""

from __future__ import annotations

from datetime import UTC, datetime

from custom_components.intelligent_heating_pilot.infrastructure.adapters.scheduled_slot_history_reader import (
    HAScheduledSlotHistoryReader,
)


def test_a_slot_that_came_from_a_wake_up_source_is_filed_like_any_other() -> None:
    records = [
        {
            "state": "2026-11-16T05:30:00+00:00",
            "attributes": {
                "next_target_temperature": 21.0,
                "scheduler_entity": "sensor.phone_next_alarm",
            },
        },
        {
            "state": "2026-11-16T07:00:00+00:00",
            "attributes": {
                "next_target_temperature": 20.0,
                "scheduler_entity": "switch.plan",
            },
        },
    ]

    slots = HAScheduledSlotHistoryReader._to_slots("sensor.next_schedule_time", records)

    assert [(slot.timestamp, slot.value) for slot in slots] == [
        (datetime(2026, 11, 16, 5, 30, tzinfo=UTC), 21.0),
        (datetime(2026, 11, 16, 7, 0, tzinfo=UTC), 20.0),
    ]
