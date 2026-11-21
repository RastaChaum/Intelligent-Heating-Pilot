"""Inherit, override and reset a device value from its theme forms (#302).

Home Assistant forms have no "inherit" state. A theme with shareable settings therefore shows,
besides its device-only fields, one multi-select of the settings this device overrides, and its
description says, for each setting, whether it is inherited or overridden and its value. A
second form asks the value of the selected settings. Unselecting a setting resets it to
"inherit". "None" is a valid override of an optional sensor, distinct from "inherit".
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.translation import async_get_translations

from .config_flow_selectors import build_theme_schema, theme_definitions
from .config_flow_themes import ThemeStepsMixin, drop_unchanged_defaults, normalize_theme_input
from .const import DOMAIN
from .domain.services.settings_catalog import SettingsCatalog
from .domain.services.settings_resolver import SettingsResolver
from .domain.value_objects.resolved_setting import ResolvedSetting, SettingSource
from .domain.value_objects.setting_definition import SettingDefinition, SettingScope, SettingTheme
from .infrastructure.adapters.central_config_reader import HACentralConfigReader

OVERRIDE_FIELD = "overridden_settings"
VALUES_SUFFIX = "_values"
NO_VALUE_TEXT = "none"


class OverrideThemeStepsMixin(ThemeStepsMixin):
    """The device options: theme forms with the override picker and the values forms."""

    _values_theme: SettingTheme | None = None
    _values_keys: tuple[str, ...] = ()

    def _resolved(self) -> dict[str, ResolvedSetting]:
        """Resolve every setting of this device: its own value, else the central one, else default."""
        return SettingsResolver().resolve(
            SettingsCatalog(),
            self._shown_values(),
            HACentralConfigReader(self.hass).read_central_values(),
        )

    @staticmethod
    def _split(
        theme: SettingTheme,
    ) -> tuple[tuple[SettingDefinition, ...], tuple[SettingDefinition, ...]]:
        definitions = theme_definitions(theme)
        device = tuple(d for d in definitions if d.scope is SettingScope.DEVICE)
        shareable = tuple(d for d in definitions if d.scope is SettingScope.SHAREABLE)
        return device, shareable

    async def _indicators(
        self, theme: SettingTheme, shareable: tuple[SettingDefinition, ...]
    ) -> str:
        """Describe each shareable setting: inherited or overridden, and its value."""
        language = self.hass.config.language
        common = await async_get_translations(self.hass, language, "common", [DOMAIN])
        options = await async_get_translations(self.hass, language, "options", [DOMAIN])
        resolved = self._resolved()
        lines = []
        for definition in shareable:
            setting = resolved[definition.key]
            label = options.get(
                f"component.{DOMAIN}.options.step.{theme.value}{VALUES_SUFFIX}.data.{definition.key}",
                definition.key,
            )
            state = "overridden" if setting.source is SettingSource.OVERRIDE else "inherited"
            word = common.get(f"component.{DOMAIN}.common.{state}", state)
            none = common.get(f"component.{DOMAIN}.common.{NO_VALUE_TEXT}", NO_VALUE_TEXT)
            value = none if setting.value in (None, "") else setting.value
            lines.append(f"- {label}: {word} ({value})")
        return "\n".join(lines)

    def _picker(self, shareable: tuple[SettingDefinition, ...]) -> Any:
        return selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[d.key for d in shareable],
                multiple=True,
                mode=selector.SelectSelectorMode.LIST,
                translation_key=OVERRIDE_FIELD,
            )
        )

    async def _theme_step(
        self, theme: SettingTheme, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        """Show a theme: device-only fields and the picker of overridden settings."""
        device, shareable = self._split(theme)
        if not shareable:
            return await super()._theme_step(theme, user_input)
        stored = self._shown_values()
        keys = [d.key for d in shareable]
        if user_input is not None:
            selected = [k for k in user_input.get(OVERRIDE_FIELD, []) if k in keys]
            values = normalize_theme_input(
                device, {k: v for k, v in user_input.items() if k != OVERRIDE_FIELD}
            )
            reset = [k for k in keys if k in stored and k not in selected]
            changed = drop_unchanged_defaults(device, values, stored)
            if changed or reset:
                self._write_values(changed, remove=reset)
            if selected:
                self._values_theme, self._values_keys = theme, tuple(selected)
                return await self._values_step(theme, None)
            return await self.async_step_init()
        schema = dict(build_theme_schema(self.hass, device, stored).schema)
        overridden = [k for k in keys if k in stored]
        schema[vol.Optional(OVERRIDE_FIELD, default=overridden)] = self._picker(shareable)
        return self.async_show_form(
            step_id=self._step_id(theme),
            data_schema=vol.Schema(schema),  # type: ignore[arg-type, unused-ignore]
            description_placeholders={"settings": await self._indicators(theme, shareable)},
        )

    async def _values_step(
        self, theme: SettingTheme, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        """Ask the value of the settings the user chose to override."""
        _, shareable = self._split(theme)
        chosen = tuple(d for d in shareable if d.key in self._values_keys)
        if user_input is not None:
            # Every submitted value is an explicit override, even one equal to the inherited value.
            self._write_values(normalize_theme_input(chosen, user_input))
            return await self.async_step_init()
        effective: Mapping[str, Any] = {k: r.value for k, r in self._resolved().items()}
        return self.async_show_form(
            step_id=f"{self._step_id(theme)}{VALUES_SUFFIX}",
            data_schema=build_theme_schema(self.hass, chosen, effective),  # type: ignore[arg-type, unused-ignore]
        )

    async def async_step_native_schedule_values(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Values of the native schedule settings the device overrides."""
        return await self._values_step(SettingTheme.NATIVE_SCHEDULE, user_input)

    async def async_step_environment_values(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Values of the environment sensors the device overrides."""
        return await self._values_step(SettingTheme.ENVIRONMENT, user_input)

    async def async_step_learning_values(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Values of the learning settings the device overrides."""
        return await self._values_step(SettingTheme.LEARNING, user_input)

    async def async_step_cycle_detection_values(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Values of the cycle detection settings the device overrides."""
        return await self._values_step(SettingTheme.CYCLE_DETECTION, user_input)

    async def async_step_anticipation_values(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Values of the anticipation settings the device overrides."""
        return await self._values_step(SettingTheme.ANTICIPATION, user_input)
