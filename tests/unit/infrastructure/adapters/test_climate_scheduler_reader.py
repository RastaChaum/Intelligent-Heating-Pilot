"""Unit tests for HAClimateSchedulerReader: the next node of a Climate Scheduler switch.

Climate Scheduler imitates HACS Scheduler's attributes, but ``actions`` holds one entry per node
AND per scheduled entity while ``next_slot`` indexes nodes, so a group needs the entity's own entry.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from custom_components.intelligent_heating_pilot.domain.value_objects import SlotAction
from custom_components.intelligent_heating_pilot.infrastructure.adapters.climate_scheduler_reader import (
    HAClimateSchedulerReader,
)

CLIMATE = "climate.living_room"
OTHER = "climate.bedroom"
NEXT_TRIGGER = "2026-11-16T18:00:00+01:00"
PARIS = ZoneInfo("Europe/Paris")


def _temp(entity: str, value: float | None, **extra) -> dict:
    return {
        "entity_id": entity,
        "service": "climate.set_temperature",
        "data": {"temperature": value, **extra},
    }


def _preset(entity: str, preset: str) -> dict:
    return {
        "entity_id": entity,
        "service": "climate.set_preset_mode",
        "data": {"preset_mode": preset},
    }


def _attrs(actions: list, next_slot: int, **extra) -> dict:
    return {"next_trigger": NEXT_TRIGGER, "next_slot": next_slot, "actions": actions, **extra}


def _read(attrs: dict, climate: str = CLIMATE):
    return HAClimateSchedulerReader(climate).read(attrs)


class TestNextNode:
    def test_the_next_trigger_is_the_slot_start(self) -> None:
        start, _ = _read(_attrs([_temp(CLIMATE, 21.0)], 0))

        assert start == datetime(2026, 11, 16, 18, 0, tzinfo=PARIS).astimezone(start.tzinfo)

    def test_a_temperature_node_is_a_temperature_action(self) -> None:
        _, action = _read(_attrs([_temp(CLIMATE, 18.0), _temp(CLIMATE, 21.0)], 1))

        assert action == SlotAction(temperature=21.0)

    def test_a_preset_node_is_a_preset_action(self) -> None:
        _, action = _read(_attrs([_preset(CLIMATE, "eco"), _preset(CLIMATE, "comfort")], 1))

        assert action == SlotAction(preset="comfort")

    def test_a_nodes_hvac_mode_is_ignored(self) -> None:
        _, action = _read(_attrs([_temp(CLIMATE, 21.0, hvac_mode="heat")], 0))

        assert action == SlotAction(temperature=21.0)


class TestGroups:
    def test_the_entry_of_our_climate_is_picked_among_a_groups_entries(self) -> None:
        """Two nodes for two climates: [n0:a, n0:b, n1:a, n1:b]; next node 1, ours is b."""
        actions = [
            _temp(CLIMATE, 17.0),
            _temp(OTHER, 16.0),
            _temp(CLIMATE, 21.0),
            _temp(OTHER, 19.0),
        ]

        _, action = _read(_attrs(actions, 1), climate=OTHER)

        assert action == SlotAction(temperature=19.0)

    def test_our_own_entry_is_picked_for_the_first_climate_too(self) -> None:
        actions = [
            _temp(CLIMATE, 17.0),
            _temp(OTHER, 16.0),
            _temp(CLIMATE, 21.0),
            _temp(OTHER, 19.0),
        ]

        _, action = _read(_attrs(actions, 1), climate=CLIMATE)

        assert action == SlotAction(temperature=21.0)

    def test_a_group_without_our_climate_gives_no_action(self) -> None:
        actions = [_temp("climate.a", 17.0), _temp("climate.b", 21.0)]

        start, action = _read(_attrs(actions, 0))

        assert start is not None
        assert action is None

    def test_a_single_entity_whose_id_is_unknown_is_taken_as_ours(self) -> None:
        """Climate Scheduler writes "unknown" when it cannot name the entity of a single schedule."""
        actions = [_temp("unknown", 18.0), _temp("unknown", 21.0)]

        _, action = _read(_attrs(actions, 1))

        assert action == SlotAction(temperature=21.0)


class TestNoAction:
    def test_a_no_change_node_gives_no_action(self) -> None:
        """A node that keeps the setpoint (null temperature) applies nothing to anticipate."""
        _, action = _read(_attrs([_temp(CLIMATE, None)], 0))

        assert action is None

    def test_a_node_that_only_changes_the_hvac_mode_gives_no_action(self) -> None:
        node = {
            "entity_id": CLIMATE,
            "service": "climate.set_temperature",
            "data": {"temperature": None, "hvac_mode": "off"},
        }

        _, action = _read(_attrs([node], 0))

        assert action is None

    @pytest.mark.parametrize("next_slot", [None, "1", -1, 5])
    def test_an_unusable_next_slot_gives_no_action(self, next_slot) -> None:
        _, action = _read(_attrs([_temp(CLIMATE, 21.0)], next_slot))

        assert action is None

    @pytest.mark.parametrize("actions", [None, [], "nope", [None], [{"service": "light.turn_on"}]])
    def test_unusable_actions_give_no_action(self, actions) -> None:
        _, action = _read({"next_trigger": NEXT_TRIGGER, "next_slot": 0, "actions": actions})

        assert action is None

    def test_a_missing_or_bad_next_trigger_gives_no_start(self) -> None:
        for trigger in (None, "", "not a date"):
            start, _ = _read(
                {"next_trigger": trigger, "next_slot": 0, "actions": [_temp(CLIMATE, 21.0)]}
            )
            assert start is None

    @pytest.mark.parametrize("value", ["warm", True, float("nan")])
    def test_an_unreadable_temperature_gives_no_action(self, value) -> None:
        _, action = _read(_attrs([_temp(CLIMATE, value)], 0))

        assert action is None
