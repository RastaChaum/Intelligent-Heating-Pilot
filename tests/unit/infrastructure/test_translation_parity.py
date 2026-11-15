"""Translation parity for the wake-up source forms, runnable without a Home Assistant fixture.

The integration test of the same name needs a full Home Assistant; these checks build the
forms' schemas directly, so the labels, help texts, menu entries and errors of the wake-up
steps are checked wherever the unit suite runs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from homeassistant.helpers import selector

from custom_components.intelligent_heating_pilot.config_flow_wake_up import (
    ERROR_DUPLICATE,
    ERROR_TARGET_REQUIRED,
    build_source_schema,
    validate_source,
)

COMPONENT = Path(__file__).parents[3] / "custom_components" / "intelligent_heating_pilot"
FILES = [COMPONENT / "strings.json", COMPONENT / "translations" / "en.json"]
ALL_FILES = [*FILES, COMPONENT / "translations" / "fr.json"]
MENU_OPTIONS = {"wake_up_add", "wake_up_edit", "wake_up_remove", "wake_up_done"}


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _key_paths(tree: dict[str, Any], prefix: str = "") -> set[str]:
    paths: set[str] = set()
    for key, value in tree.items():
        path = f"{prefix}.{key}" if prefix else key
        paths.add(path)
        if isinstance(value, dict):
            paths |= _key_paths(value, path)
    return paths


def _empty(tree: dict[str, Any], prefix: str = "") -> list[str]:
    bad: list[str] = []
    for key, value in tree.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            bad += _empty(value, path)
        elif not isinstance(value, str) or not value.strip():
            bad.append(path)
    return bad


def _schema(has_scheduler: bool) -> dict[Any, Any]:
    hass = Mock()
    hass.states.get.return_value = None
    return build_source_schema(hass, "climate.vtherm", has_scheduler, {}).schema


@pytest.mark.parametrize("path", ALL_FILES, ids=lambda p: p.name)
@pytest.mark.parametrize("has_scheduler", [True, False])
def test_every_field_of_the_source_form_has_a_label_and_a_help_text(
    path: Path, has_scheduler: bool
) -> None:
    fields = {str(key) for key in _schema(has_scheduler)}
    step = _load(path)["options"]["step"]["wake_up_form"]

    assert fields - set(step["data"]) == set()
    assert fields - set(step["data_description"]) == set()


@pytest.mark.parametrize("path", ALL_FILES, ids=lambda p: p.name)
def test_every_field_declared_for_the_source_form_exists(path: Path) -> None:
    step = _load(path)["options"]["step"]["wake_up_form"]
    all_fields = {str(key) for key in _schema(True)}

    assert set(step["data"]) - all_fields == set()
    assert set(step["data_description"]) - all_fields == set()


@pytest.mark.parametrize("path", ALL_FILES, ids=lambda p: p.name)
def test_the_menu_and_the_pick_steps_are_translated(path: Path) -> None:
    steps = _load(path)["options"]["step"]

    assert set(steps["wake_up_menu"]["menu_options"]) == MENU_OPTIONS
    for step_id in ("wake_up_edit", "wake_up_remove"):
        assert set(steps[step_id]["data"]) == {"entity_id"}
        assert set(steps[step_id]["data_description"]) == {"entity_id"}
    assert "manage_wake_up_sources" in steps["init"]["data"]
    assert "manage_wake_up_sources" in steps["init"]["data_description"]


@pytest.mark.parametrize("path", ALL_FILES, ids=lambda p: p.name)
def test_the_errors_the_source_form_raises_are_declared(path: Path) -> None:
    declared = set(_load(path)["options"]["error"])

    assert {ERROR_TARGET_REQUIRED, ERROR_DUPLICATE} <= declared
    raised = set(validate_source({"entity_id": "sensor.a"}, [], True).values())
    raised |= set(
        validate_source({"entity_id": "sensor.a"}, [{"entity_id": "sensor.a"}], True).values()
    )
    assert raised == {ERROR_TARGET_REQUIRED, ERROR_DUPLICATE}


def test_every_numeric_field_of_the_source_form_declares_a_unit() -> None:
    without_unit = {
        str(key)
        for key, field in _schema(True).items()
        if isinstance(field, selector.NumberSelector)
        and not field.config.get("unit_of_measurement")
    }

    assert without_unit == set()


def test_french_declares_the_same_keys_as_english() -> None:
    english = _key_paths(_load(COMPONENT / "translations" / "en.json"))
    french = _key_paths(_load(COMPONENT / "translations" / "fr.json"))

    assert english - french == set()
    assert french - english == set()


def test_strings_json_mirrors_english() -> None:
    assert _load(COMPONENT / "strings.json") == _load(COMPONENT / "translations" / "en.json")


@pytest.mark.parametrize("path", ALL_FILES, ids=lambda p: p.name)
def test_no_translation_text_is_empty(path: Path) -> None:
    assert _empty(_load(path)) == []
