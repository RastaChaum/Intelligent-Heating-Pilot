"""The "Inherited / Custom" toggle of a shareable setting in the device options (#302)."""

from __future__ import annotations

import pytest
import voluptuous as vol
from homeassistant.helpers import selector

from custom_components.intelligent_heating_pilot.config_flow_overrides import (
    InheritableSelector,
    InheritanceChoice,
    changed_values,
    initial_choice,
    is_overridden,
)
from custom_components.intelligent_heating_pilot.config_flow_selectors import selector_for
from custom_components.intelligent_heating_pilot.domain.value_objects.resolved_setting import (
    ResolvedSetting,
    SettingSource,
)

RETENTION = "lhs_retention_days"
OUTDOOR = "temperature_out_entity_id"


def _sensor_toggle() -> InheritableSelector:
    return InheritableSelector(selector_for(OUTDOOR), "Outdoor (sensor.outdoor)", optional=True)


def _number_toggle() -> InheritableSelector:
    return InheritableSelector(selector_for(RETENTION), "30", optional=False)


class TestValidation:
    def test_inherited_drops_whatever_the_custom_side_holds(self) -> None:
        submitted = {"active_choice": "inherited", "inherited": "inherited", "custom": 60}

        assert _number_toggle()(submitted) == InheritanceChoice(inherit=True)

    def test_custom_keeps_the_validated_value(self) -> None:
        submitted = {"active_choice": "custom", "custom": 60}

        assert _number_toggle()(submitted) == InheritanceChoice(inherit=False, value=60)

    def test_an_empty_custom_sensor_is_no_sensor(self) -> None:
        assert _sensor_toggle()({"active_choice": "custom"}) == InheritanceChoice(inherit=False)

    def test_an_empty_custom_number_is_rejected(self) -> None:
        with pytest.raises(vol.Invalid):
            _number_toggle()({"active_choice": "custom", "custom": ""})

    def test_a_custom_number_out_of_its_bounds_is_rejected(self) -> None:
        with pytest.raises(vol.Invalid):
            _number_toggle()({"active_choice": "custom", "custom": 1000})

    @pytest.mark.parametrize("submitted", [None, {}, {"active_choice": "other"}])
    def test_anything_but_a_toggle_or_a_plain_value_is_rejected(self, submitted: object) -> None:
        with pytest.raises(vol.Invalid):
            _number_toggle()(submitted)

    def test_a_plain_value_is_the_own_value_of_a_field_left_untouched(self) -> None:
        assert _number_toggle()(60) == InheritanceChoice(inherit=False, value=60)

    def test_the_plain_inherited_marker_is_inherited(self) -> None:
        assert _number_toggle()("inherited") == InheritanceChoice(inherit=True)

    def test_a_plain_none_is_no_sensor_for_an_optional_setting(self) -> None:
        assert _sensor_toggle()(None) == InheritanceChoice(inherit=False)


class TestDisplay:
    def test_the_frontend_gets_a_choose_selector_with_the_inherited_value_as_text(self) -> None:
        serialized = _sensor_toggle().serialize()["selector"]["choose"]

        assert serialized["translation_key"] == "inheritance"
        assert list(serialized["choices"]) == ["inherited", "custom"]
        inherited = serialized["choices"]["inherited"]["selector"]["constant"]
        assert inherited["label"] == "Outdoor (sensor.outdoor)"
        assert "entity" in serialized["choices"]["custom"]["selector"]

    def test_it_is_a_choose_selector(self) -> None:
        assert isinstance(_sensor_toggle(), selector.ChooseSelector)

    def test_the_custom_side_is_listed_first_when_the_device_has_its_own_value(self) -> None:
        toggle = InheritableSelector(selector_for(RETENTION), "30", optional=False, own_first=True)

        assert list(toggle.serialize()["selector"]["choose"]["choices"]) == ["custom", "inherited"]

    def test_an_overridden_setting_defaults_to_its_own_value(self) -> None:
        setting = ResolvedSetting(RETENTION, 90, SettingSource.OVERRIDE)

        assert is_overridden(setting)
        assert initial_choice(setting) == 90

    def test_an_overridden_empty_sensor_defaults_to_none(self) -> None:
        setting = ResolvedSetting(OUTDOOR, None, SettingSource.OVERRIDE)

        assert is_overridden(setting)
        assert initial_choice(setting) is None

    @pytest.mark.parametrize("source", [SettingSource.CENTRAL, SettingSource.DEFAULT])
    def test_an_inherited_setting_defaults_to_the_inherited_marker(
        self, source: SettingSource
    ) -> None:
        setting = ResolvedSetting(RETENTION, 30, source)

        assert not is_overridden(setting)
        assert initial_choice(setting) == "inherited"


class TestChanges:
    def test_only_new_or_changed_own_values_are_stored(self) -> None:
        choices = {
            "a": InheritanceChoice(inherit=False, value=1),
            "b": InheritanceChoice(inherit=False, value=2),
        }

        values, reset = changed_values(choices, {"a": 1})

        assert values == {"b": 2}
        assert reset == []

    def test_inherited_settings_the_device_stored_are_reset(self) -> None:
        choices = {"a": InheritanceChoice(inherit=True), "b": InheritanceChoice(inherit=True)}

        values, reset = changed_values(choices, {"a": 1})

        assert values == {}
        assert reset == ["a"]

    def test_no_sensor_replaces_a_stored_sensor(self) -> None:
        values, _ = changed_values({"a": InheritanceChoice(inherit=False)}, {"a": "sensor.x"})

        assert values == {"a": None}
