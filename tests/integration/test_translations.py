"""Translation files stay in sync with the config flow, options flow and services (#193).

Home Assistant shows the raw key of any label, help text or error missing from the
translation files, so the files are checked against the real flow schemas rather than
against a hand-written list of fields.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import Any

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import selector
from homeassistant.util.yaml import load_yaml_dict
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.intelligent_heating_pilot.config_flow import (
    IntelligentHeatingPilotConfigFlow,
    IntelligentHeatingPilotOptionsFlow,
)
from custom_components.intelligent_heating_pilot.const import (
    CONF_NAME,
    CONF_VTHERM_ENTITY,
    DEFAULT_NAME,
    DOMAIN,
)

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")

# Flow results are TypedDicts whose schema and errors are optional; the tests read them as
# plain mappings and let a missing key fail the test.
FlowResult = Mapping[str, Any]

COMPONENT_DIR = Path(__file__).parents[2] / "custom_components" / DOMAIN
STRINGS_FILE = COMPONENT_DIR / "strings.json"
ENGLISH_FILE = COMPONENT_DIR / "translations" / "en.json"
FRENCH_FILE = COMPONENT_DIR / "translations" / "fr.json"
SERVICES_FILE = COMPONENT_DIR / "services.yaml"

TRANSLATION_FILES = [STRINGS_FILE, ENGLISH_FILE, FRENCH_FILE]
FIELD_TEXT_SECTIONS = ("data", "data_description")
SERVICE_TEXT_KEYS = ("name", "description")

# Input the flow handlers reject with their own errors (not the schema's).
MISSING_VTHERM_INPUT = {CONF_NAME: DEFAULT_NAME, CONF_VTHERM_ENTITY: ""}


def _load_json(path: Path) -> dict[str, Any]:
    content: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return content


def _add_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="translations_entry",
        data={CONF_NAME: DEFAULT_NAME, CONF_VTHERM_ENTITY: "climate.living_room"},
        options={},
    )
    entry.add_to_hass(hass)
    return entry


async def _open_user_form(hass: HomeAssistant) -> FlowResult:
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})


async def _open_options_form(hass: HomeAssistant) -> FlowResult:
    entry = _add_entry(hass)
    return await hass.config_entries.options.async_init(entry.entry_id)


async def _submit_user_form(hass: HomeAssistant, user_input: dict[str, Any]) -> FlowResult:
    flow = IntelligentHeatingPilotConfigFlow()
    flow.hass = hass
    return await flow.async_step_user(user_input)


async def _submit_options_form(hass: HomeAssistant, user_input: dict[str, Any]) -> FlowResult:
    flow = IntelligentHeatingPilotOptionsFlow()
    flow.hass = hass
    flow.handler = _add_entry(hass).entry_id
    return await flow.async_step_init(user_input)


FormOpener = Callable[[HomeAssistant], Awaitable[FlowResult]]
FormSubmitter = Callable[[HomeAssistant, dict[str, Any]], Awaitable[FlowResult]]

# (translation section, step id, opener, submitter) for each form of the integration.
FORMS: dict[str, tuple[str, str, FormOpener, FormSubmitter]] = {
    "setup": ("config", "user", _open_user_form, _submit_user_form),
    "options": ("options", "init", _open_options_form, _submit_options_form),
}


def _field_names(form: FlowResult) -> set[str]:
    return {str(key) for key in form["data_schema"].schema}


def _key_paths(tree: dict[str, Any], prefix: str = "") -> set[str]:
    paths: set[str] = set()
    for key, value in tree.items():
        path = f"{prefix}.{key}" if prefix else key
        paths.add(path)
        if isinstance(value, dict):
            paths |= _key_paths(value, path)
    return paths


def _empty_texts(tree: dict[str, Any], prefix: str = "") -> list[str]:
    empty: list[str] = []
    for key, value in tree.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            empty += _empty_texts(value, path)
        elif not isinstance(value, str) or not value.strip():
            empty.append(path)
    return empty


@pytest.mark.asyncio
@pytest.mark.parametrize("form_name", FORMS)
@pytest.mark.parametrize("translation_file", TRANSLATION_FILES, ids=lambda path: path.name)
async def test_every_form_field_has_a_label_and_a_help_text(
    hass: HomeAssistant, form_name: str, translation_file: Path
) -> None:
    """Each field of the form, and only those, has a label and a help text."""
    section, step_id, open_form, _ = FORMS[form_name]
    fields = _field_names(await open_form(hass))
    step = _load_json(translation_file)[section]["step"][step_id]

    for text_section in FIELD_TEXT_SECTIONS:
        declared = set(step.get(text_section, {}))
        assert fields - declared == set(), f"{text_section} missing for these fields"
        assert declared - fields == set(), f"{text_section} declared for removed fields"


@pytest.mark.asyncio
@pytest.mark.parametrize("form_name", FORMS)
@pytest.mark.parametrize("translation_file", TRANSLATION_FILES, ids=lambda path: path.name)
async def test_declared_errors_are_the_ones_the_form_raises(
    hass: HomeAssistant, form_name: str, translation_file: Path
) -> None:
    """A validation error shows a message, and no error is declared that cannot occur."""
    section, _, _, submit_form = FORMS[form_name]
    result = await submit_form(hass, MISSING_VTHERM_INPUT)
    raised = set(result["errors"].values())

    assert raised == {"required"}
    assert set(_load_json(translation_file)[section].get("error", {})) == raised


def test_french_declares_the_same_keys_as_english() -> None:
    """A text missing in French falls back to English: keep both files aligned."""
    english = _key_paths(_load_json(ENGLISH_FILE))
    french = _key_paths(_load_json(FRENCH_FILE))

    assert english - french == set(), "missing in fr.json"
    assert french - english == set(), "missing in en.json"


def test_strings_json_mirrors_english() -> None:
    """strings.json is the source copy of en.json, the file Home Assistant loads."""
    assert _load_json(STRINGS_FILE) == _load_json(ENGLISH_FILE)


@pytest.mark.parametrize("translation_file", TRANSLATION_FILES, ids=lambda path: path.name)
def test_no_translation_text_is_empty(translation_file: Path) -> None:
    """An empty text renders as a blank label, which is no better than a raw key."""
    assert _empty_texts(_load_json(translation_file)) == []


@pytest.mark.parametrize("translation_file", TRANSLATION_FILES, ids=lambda path: path.name)
def test_every_service_and_field_is_translated(translation_file: Path) -> None:
    """Each service of services.yaml, and each of its fields, has a name and a description."""
    services = load_yaml_dict(SERVICES_FILE)
    translated = _load_json(translation_file).get("services", {})

    assert set(translated) == set(services)
    for service_name, service in services.items():
        texts = translated[service_name]
        assert set(texts.get("fields", {})) == set(service.get("fields", {})), service_name
        assert all(texts.get(key) for key in SERVICE_TEXT_KEYS), service_name
        for field_name, field_texts in texts.get("fields", {}).items():
            assert all(field_texts.get(key) for key in SERVICE_TEXT_KEYS), field_name


@pytest.mark.asyncio
@pytest.mark.parametrize("form_name", FORMS)
async def test_every_numeric_field_declares_a_unit(hass: HomeAssistant, form_name: str) -> None:
    """A number without a unit is ambiguous (minutes? seconds?) next to the other fields."""
    _, _, open_form, _ = FORMS[form_name]
    schema = (await open_form(hass))["data_schema"].schema

    without_unit = {
        str(key)
        for key, field_selector in schema.items()
        if isinstance(field_selector, selector.NumberSelector)
        and not field_selector.config.get("unit_of_measurement")
    }
    assert without_unit == set()
