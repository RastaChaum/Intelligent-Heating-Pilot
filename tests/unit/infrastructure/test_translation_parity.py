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


THEME_FORM_STEPS = (
    "thermostat_schedulers",
    "native_schedule",
    "environment",
    "learning",
    "cycle_detection",
    "anticipation",
)
CENTRAL_THEMES = THEME_FORM_STEPS[1:]
MENU_ENTRIES = {
    *THEME_FORM_STEPS,
    "wake_up_sources",
    "apply",
    *(f"central_{theme}" for theme in CENTRAL_THEMES),
}
PICKER = "overridden_settings"


def _keys(theme: str, scope: str) -> set[str]:
    from custom_components.intelligent_heating_pilot.domain.services.settings_catalog import (
        SettingsCatalog,
    )
    from custom_components.intelligent_heating_pilot.domain.value_objects.setting_definition import (
        SettingScope,
        SettingTheme,
    )

    wanted = SettingScope(scope)
    return {d.key for d in SettingsCatalog().of_theme(SettingTheme(theme)) if d.scope is wanted}


@pytest.mark.parametrize("path", ALL_FILES, ids=lambda p: p.name)
def test_the_options_menu_lists_every_theme_and_apply(path: Path) -> None:
    init = _load(path)["options"]["step"]["init"]

    assert set(init["menu_options"]) == MENU_ENTRIES
    assert "{pending}" in init["description"]


@pytest.mark.parametrize("path", ALL_FILES, ids=lambda p: p.name)
@pytest.mark.parametrize("theme", THEME_FORM_STEPS)
def test_a_device_theme_form_has_its_device_fields_and_the_picker(path: Path, theme: str) -> None:
    step = _load(path)["options"]["step"][theme]
    expected = _keys(theme, "device") | ({PICKER} if _keys(theme, "shareable") else set())

    assert set(step["data"]) == expected
    assert set(step["data_description"]) == expected
    assert step["title"].strip() and step["description"].strip()
    assert ("{settings}" in step["description"]) == bool(_keys(theme, "shareable"))


@pytest.mark.parametrize("path", ALL_FILES, ids=lambda p: p.name)
@pytest.mark.parametrize("theme", CENTRAL_THEMES)
def test_the_values_and_central_forms_have_a_label_and_a_help_text_per_shared_setting(
    path: Path, theme: str
) -> None:
    steps = _load(path)["options"]["step"]
    keys = _keys(theme, "shareable")

    for step_id in (f"{theme}_values", f"central_{theme}"):
        assert set(steps[step_id]["data"]) == keys, step_id
        assert set(steps[step_id]["data_description"]) == keys, step_id
        assert steps[step_id]["title"].strip() and steps[step_id]["description"].strip()


@pytest.mark.parametrize("path", ALL_FILES, ids=lambda p: p.name)
def test_the_picker_and_the_indicators_are_translated(path: Path) -> None:
    translated = _load(path)
    shareable = set().union(*(_keys(theme, "shareable") for theme in CENTRAL_THEMES))

    assert set(translated["selector"][PICKER]["options"]) == shareable
    assert set(translated["common"]) == {"inherited", "overridden", "none"}
