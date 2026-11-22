"""Tests for the translation of stored wake-up source options."""

from __future__ import annotations

from datetime import timedelta

from custom_components.intelligent_heating_pilot.domain.value_objects import SlotAction
from custom_components.intelligent_heating_pilot.infrastructure.adapters.wake_up_sources_config import (
    parse_wake_up_sources,
)


def test_absent_or_wrong_type_gives_no_source() -> None:
    assert parse_wake_up_sources(None, has_scheduler=True) == ()
    assert parse_wake_up_sources("sensor.alarm", has_scheduler=True) == ()


def test_a_full_entry() -> None:
    raw = [
        {
            "entity_id": "sensor.alarm",
            "target_preset": "comfort",
            "target_temperature": 21,
            "horizon_hours": 12,
            "hold_minutes": 90,
        }
    ]
    (source,) = parse_wake_up_sources(raw, has_scheduler=False)
    assert source.fixed_target == SlotAction(preset="comfort", temperature=21.0)
    assert source.horizon == timedelta(hours=12)
    assert source.hold == timedelta(minutes=90)


def test_defaults() -> None:
    (source,) = parse_wake_up_sources(
        [{"entity_id": "sensor.alarm", "target_temperature": 20}], has_scheduler=False
    )
    assert source.horizon == timedelta(hours=24)
    assert source.hold is None and source.target_from_schedule is False


def test_zero_hold_means_no_hold() -> None:
    (source,) = parse_wake_up_sources(
        [{"entity_id": "sensor.alarm", "target_preset": "eco", "hold_minutes": 0}],
        has_scheduler=False,
    )
    assert source.hold is None


def test_from_schedule_needs_a_scheduler() -> None:
    entry = {"entity_id": "sensor.alarm", "target_from_schedule": True, "target_preset": "eco"}
    (with_scheduler,) = parse_wake_up_sources([entry], has_scheduler=True)
    (without,) = parse_wake_up_sources([entry], has_scheduler=False)
    assert with_scheduler.target_from_schedule is True
    assert without.target_from_schedule is False and without.fixed_target is not None


def test_from_schedule_without_scheduler_and_without_fixed_target_is_skipped() -> None:
    entry = {"entity_id": "sensor.alarm", "target_from_schedule": True}
    assert parse_wake_up_sources([entry], has_scheduler=False) == ()


def test_unusable_entries_are_skipped_without_losing_the_others() -> None:
    raw = [
        {"target_preset": "eco"},
        {"entity_id": "sensor.alarm"},
        "garbage",
        {"entity_id": "sensor.ok", "target_preset": "eco"},
    ]
    assert [s.entity_id for s in parse_wake_up_sources(raw, has_scheduler=True)] == ["sensor.ok"]


def test_an_entity_listed_twice_is_kept_once() -> None:
    raw = [
        {"entity_id": "sensor.alarm", "target_preset": "eco"},
        {"entity_id": "sensor.alarm", "target_preset": "comfort"},
    ]
    (source,) = parse_wake_up_sources(raw, has_scheduler=True)
    assert source.fixed_target == SlotAction(preset="eco")
