"""Unit tests for ClimateSnapshot and PreheatRecord."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta

import pytest

from custom_components.intelligent_heating_pilot.domain.value_objects.climate_snapshot import (
    ClimateSnapshot,
)
from custom_components.intelligent_heating_pilot.domain.value_objects.preheat_record import (
    PreheatRecord,
)
from custom_components.intelligent_heating_pilot.domain.value_objects.slot_action import SlotAction

NOW = datetime(2026, 11, 14, 5, 0, tzinfo=UTC)


def _snapshot(**overrides) -> ClimateSnapshot:
    values = {
        "hvac_mode": "heat",
        "preset": "eco",
        "temperature": 18.0,
        "available_presets": ("eco", "comfort", "boost"),
    }
    values.update(overrides)
    return ClimateSnapshot(**values)


def _record(**overrides) -> PreheatRecord:
    values = {
        "timeslot_id": "switch.plan_2026-11-14T07:00:00+00:00",
        "scheduler_entity": "switch.plan",
        "slot_time": NOW + timedelta(hours=2),
        "previous": _snapshot(),
        "applied": SlotAction(preset="comfort"),
        "recorded_at": NOW,
    }
    values.update(overrides)
    return PreheatRecord(**values)


class TestClimateSnapshot:
    def test_a_blank_hvac_mode_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="hvac_mode"):
            _snapshot(hvac_mode="")

    def test_a_snapshot_matches_the_preset_that_was_applied(self) -> None:
        assert _snapshot(preset="comfort").matches(SlotAction(preset="comfort"))

    def test_the_preset_comparison_ignores_case(self) -> None:
        assert _snapshot(preset="Comfort").matches(SlotAction(preset="comfort"))

    def test_a_snapshot_does_not_match_another_preset(self) -> None:
        assert not _snapshot(preset="eco").matches(SlotAction(preset="comfort"))

    def test_a_snapshot_matches_the_temperature_that_was_applied(self) -> None:
        assert _snapshot(preset=None, temperature=21.0).matches(SlotAction(temperature=21.0))

    def test_the_temperature_comparison_absorbs_float_noise(self) -> None:
        assert _snapshot(preset=None, temperature=21.01).matches(SlotAction(temperature=21.0))

    def test_a_snapshot_does_not_match_another_temperature(self) -> None:
        assert not _snapshot(preset=None, temperature=19.5).matches(SlotAction(temperature=21.0))

    def test_an_unknown_temperature_never_matches(self) -> None:
        assert not _snapshot(preset=None, temperature=None).matches(SlotAction(temperature=21.0))

    def test_the_preset_decides_when_the_action_carries_both(self) -> None:
        snapshot = _snapshot(preset="comfort", temperature=15.0)

        assert snapshot.matches(SlotAction(preset="comfort", temperature=21.0))

    def test_a_preset_is_offered_when_listed_whatever_its_case(self) -> None:
        assert _snapshot().offers_preset("COMFORT")
        assert not _snapshot().offers_preset("away")

    def test_the_snapshot_is_immutable(self) -> None:
        with pytest.raises(dataclasses.FrozenInstanceError):
            _snapshot().preset = "boost"  # type: ignore[misc]


class TestPreheatRecord:
    def test_a_valid_record_is_built(self) -> None:
        assert _record().scheduler_entity == "switch.plan"

    @pytest.mark.parametrize("field", ["timeslot_id", "scheduler_entity"])
    def test_blank_identifiers_are_rejected(self, field: str) -> None:
        with pytest.raises(ValueError, match=field):
            _record(**{field: ""})

    @pytest.mark.parametrize("field", ["slot_time", "recorded_at"])
    def test_naive_datetimes_are_rejected(self, field: str) -> None:
        with pytest.raises(ValueError, match="timezone"):
            _record(**{field: datetime(2026, 11, 14, 7, 0)})

    def test_the_record_is_immutable(self) -> None:
        with pytest.raises(dataclasses.FrozenInstanceError):
            _record().scheduler_entity = "switch.other"  # type: ignore[misc]
