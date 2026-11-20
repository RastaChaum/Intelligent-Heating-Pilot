"""The preset resolver works on any climate: VTherm publishes preset temperatures, others are mapped (#252)."""

from __future__ import annotations

import logging
from unittest.mock import Mock

import pytest

from custom_components.intelligent_heating_pilot.infrastructure.adapters.preset_temperature_resolver import (
    HAPresetTemperatureResolver,
)

CLIMATE = "climate.trv"


def _hass_with(attributes: dict | None) -> Mock:
    hass = Mock()
    if attributes is None:
        hass.states.get.return_value = None
    else:
        state = Mock()
        state.entity_id = CLIMATE
        state.attributes = attributes
        hass.states.get.return_value = state
    return hass


GENERIC_CLIMATE = {"preset_modes": ["eco", "comfort"], "preset_mode": "none", "temperature": 19.0}


class TestPublishedTemperatures:
    def test_a_vtherm_preset_temperature_is_used(self) -> None:
        hass = _hass_with({"preset_temperatures": {"eco_temp": 18.0}})

        assert HAPresetTemperatureResolver(hass, CLIMATE).resolve("eco") == 18.0

    def test_what_the_climate_publishes_wins_over_the_mapping(self) -> None:
        hass = _hass_with({"preset_temperatures": {"eco_temp": 18.0}})
        resolver = HAPresetTemperatureResolver(hass, CLIMATE, {"eco": 16.0})

        assert resolver.resolve("eco") == 18.0


class TestConfiguredMapping:
    def test_a_generic_climate_resolves_a_mapped_preset(self) -> None:
        resolver = HAPresetTemperatureResolver(
            _hass_with(GENERIC_CLIMATE), CLIMATE, {"eco": 17.0, "comfort": 20.5}
        )

        assert resolver.resolve("eco") == 17.0
        assert resolver.resolve("comfort") == 20.5

    @pytest.mark.parametrize("preset", ["Comfort", " comfort ", "COMFORT"])
    def test_the_preset_name_is_matched_without_case_or_padding(self, preset: str) -> None:
        resolver = HAPresetTemperatureResolver(
            _hass_with(GENERIC_CLIMATE), CLIMATE, {"comfort": 20.5}
        )

        assert resolver.resolve(preset) == 20.5

    def test_the_mapping_wins_over_the_current_target_of_the_active_preset(self) -> None:
        attributes = {**GENERIC_CLIMATE, "preset_mode": "eco", "temperature": 15.0}
        resolver = HAPresetTemperatureResolver(_hass_with(attributes), CLIMATE, {"eco": 17.0})

        assert resolver.resolve("eco") == 17.0

    def test_the_mapping_still_applies_while_the_climate_is_unavailable(self) -> None:
        resolver = HAPresetTemperatureResolver(_hass_with(None), CLIMATE, {"eco": 17.0})

        assert resolver.resolve("eco") == 17.0

    def test_an_unreadable_mapped_value_is_ignored(self) -> None:
        resolver = HAPresetTemperatureResolver(
            _hass_with(GENERIC_CLIMATE),
            CLIMATE,
            {"eco": "warm"},  # type: ignore[dict-item]
        )

        assert resolver.resolve("eco") is None


class TestUnresolvedPreset:
    def test_the_active_preset_still_gives_the_current_target(self) -> None:
        attributes = {**GENERIC_CLIMATE, "preset_mode": "eco", "temperature": 17.5}

        assert HAPresetTemperatureResolver(_hass_with(attributes), CLIMATE).resolve("eco") == 17.5

    def test_an_unmapped_preset_is_not_resolved(self) -> None:
        resolver = HAPresetTemperatureResolver(_hass_with(GENERIC_CLIMATE), CLIMATE)

        assert resolver.resolve("comfort") is None

    def test_the_warning_names_the_preset_and_the_climate_and_is_logged_once(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        resolver = HAPresetTemperatureResolver(_hass_with(GENERIC_CLIMATE), CLIMATE)

        with caplog.at_level(logging.WARNING):
            resolver.resolve("comfort")
            resolver.resolve("comfort")

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1
        assert "comfort" in warnings[0].getMessage()
        assert CLIMATE in warnings[0].getMessage()

    def test_each_unmapped_preset_is_warned_about_once(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        resolver = HAPresetTemperatureResolver(_hass_with(GENERIC_CLIMATE), CLIMATE)

        with caplog.at_level(logging.WARNING):
            resolver.resolve("comfort")
            resolver.resolve("eco")

        assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == 2

    def test_a_resolved_preset_is_never_warned_about(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        resolver = HAPresetTemperatureResolver(_hass_with(GENERIC_CLIMATE), CLIMATE, {"eco": 17.0})

        with caplog.at_level(logging.WARNING):
            resolver.resolve("eco")

        assert not [r for r in caplog.records if r.levelno == logging.WARNING]

    def test_no_climate_configured_resolves_nothing_without_failing(self) -> None:
        assert HAPresetTemperatureResolver(Mock(), None).resolve("eco") is None
