"""Tests for the wake-up value objects and the fields added to existing ones."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.intelligent_heating_pilot.domain.value_objects import (
    PreheatRecord,
    ReadingIssue,
    ScheduledTimeslot,
    SchedulerKind,
    SlotAction,
    SlotsAround,
    WakeUpReading,
    WakeUpSourceConfig,
)
from custom_components.intelligent_heating_pilot.domain.value_objects.climate_snapshot import (
    ClimateSnapshot,
)

NOW = datetime(2026, 11, 15, 5, 0, tzinfo=UTC)


class TestWakeUpSourceConfig:
    def test_fixed_target_alone_is_valid(self) -> None:
        config = WakeUpSourceConfig("sensor.alarm", fixed_target=SlotAction(preset="comfort"))
        assert config.horizon == timedelta(hours=24)
        assert config.hold is None
        assert config.target_from_schedule is False

    def test_from_schedule_alone_is_valid(self) -> None:
        assert WakeUpSourceConfig("sensor.alarm", target_from_schedule=True).fixed_target is None

    @pytest.mark.parametrize("entity_id", ["", "   "])
    def test_blank_entity_is_refused(self, entity_id: str) -> None:
        with pytest.raises(ValueError, match="entity id"):
            WakeUpSourceConfig(entity_id, fixed_target=SlotAction(preset="comfort"))

    def test_no_way_to_know_the_target_is_refused(self) -> None:
        with pytest.raises(ValueError, match="fixed target"):
            WakeUpSourceConfig("sensor.alarm")

    @pytest.mark.parametrize("horizon", [timedelta(0), timedelta(hours=-1)])
    def test_non_positive_horizon_is_refused(self, horizon: timedelta) -> None:
        with pytest.raises(ValueError, match="horizon"):
            WakeUpSourceConfig("sensor.alarm", SlotAction(preset="c"), horizon=horizon)

    def test_non_positive_hold_is_refused(self) -> None:
        with pytest.raises(ValueError, match="hold"):
            WakeUpSourceConfig("sensor.alarm", SlotAction(preset="c"), hold=timedelta(0))


class TestWakeUpReading:
    def test_value_only(self) -> None:
        assert WakeUpReading(value=NOW).issue is None

    def test_issue_only(self) -> None:
        assert WakeUpReading(issue=ReadingIssue.UNKNOWN).value is None

    def test_both_or_neither_is_refused(self) -> None:
        with pytest.raises(ValueError):
            WakeUpReading(value=NOW, issue=ReadingIssue.UNKNOWN)
        with pytest.raises(ValueError):
            WakeUpReading()

    def test_naive_value_is_refused(self) -> None:
        with pytest.raises(ValueError, match="timezone"):
            WakeUpReading(value=datetime(2026, 11, 15, 5, 0))


def test_slots_around_defaults_to_cannot_say() -> None:
    around = SlotsAround()
    assert around.in_effect is None and around.following is None


def test_timestamp_kind_exists() -> None:
    assert SchedulerKind.TIMESTAMP.value == "timestamp"


def test_timeslot_hold_defaults_to_none() -> None:
    slot = ScheduledTimeslot(target_time=NOW, target_temp=20.0, timeslot_id="x")
    assert slot.hold is None


class TestPreheatRecordHold:
    @staticmethod
    def _record(**overrides) -> PreheatRecord:
        values = {
            "timeslot_id": "sensor.alarm_2026-11-15",
            "scheduler_entity": "sensor.alarm",
            "slot_time": NOW,
            "previous": ClimateSnapshot("heat", "eco", 17.0, ("eco", "comfort")),
            "applied": SlotAction(preset="comfort"),
            "recorded_at": NOW,
        }
        values.update(overrides)
        return PreheatRecord(**values)

    def test_hold_fields_default_to_absent(self) -> None:
        record = self._record()
        assert record.hold_until is None
        assert record.hold_handoff is False

    def test_hold_until_needs_a_timezone(self) -> None:
        with pytest.raises(ValueError, match="timezone"):
            self._record(hold_until=datetime(2026, 11, 15, 7, 0))
