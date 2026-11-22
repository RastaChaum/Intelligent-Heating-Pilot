"""Inherit or override each shareable setting of a device from its theme form (#302).

A theme form shows every setting of the group. A shareable setting comes with an
"Inherited / Custom" toggle (Home Assistant's choose selector): inherited, it shows the value the
device gets from the central configuration and cannot be edited; custom, it shows the usual
selector. Switching a setting back to inherited removes the device's own value. "None" is a
valid custom value of an optional sensor, distinct from "inherited".

How the form opens on the right side matters. The frontend builds the initial data of a choose
selector itself: it takes the ``default`` as the plain value of the *first* choice and makes that
choice the active one, whatever a structured default says. So a setting that is overridden lists
"Custom" first and defaults to its own value, and an inherited one lists "Inherited" first and
defaults to the inherited marker.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, NamedTuple

import voluptuous as vol
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.translation import async_get_translations

from .config_flow_selectors import (
    _is_blank,
    build_theme_schema,
    entity_label,
    selector_for,
    theme_definitions,
)
from .config_flow_themes import ThemeStepsMixin, drop_unchanged_defaults, normalize_theme_input
from .const import DOMAIN
from .domain.services.settings_catalog import SettingsCatalog
from .domain.services.settings_resolver import SettingsResolver
from .domain.value_objects.resolved_setting import ResolvedSetting, SettingSource
from .domain.value_objects.setting_definition import SettingDefinition, SettingScope, SettingTheme
from .infrastructure.adapters.central_config_reader import HACentralConfigReader

ACTIVE_CHOICE = "active_choice"
INHERITED = "inherited"
CUSTOM = "custom"
INHERITANCE_TRANSLATION_KEY = "inheritance"
NO_VALUE_TEXT = "none"
TRUE_TEXT = "on"
FALSE_TEXT = "off"
VALUE_WORDS = (NO_VALUE_TEXT, TRUE_TEXT, FALSE_TEXT)
ENTITY_SUFFIX = "_entity_id"


class InheritanceChoice(NamedTuple):
    """What the user chose for one shareable setting.

    Attributes:
        inherit: True to follow the central configuration (or the built-in default).
        value: The device's own value when ``inherit`` is False; ``None`` is "no sensor".
    """

    inherit: bool
    value: Any = None


class InheritableSelector(selector.ChooseSelector):
    """An "Inherited / Custom" toggle over the selector of one setting.

    The inherited side is a constant showing the inherited value: the frontend does not honour
    ``read_only`` inside a choose selector, so a constant is how a value that cannot be edited is
    shown. The validation keeps which side was chosen, which the stock choose selector drops.
    """

    def __init__(
        self, own: Any, inherited_label: str, optional: bool, own_first: bool = False
    ) -> None:
        """Build the toggle.

        Args:
            own: The selector the setting uses when it has its own value.
            inherited_label: The inherited value, as shown to the user.
            optional: True when an empty own value means "no sensor".
            own_first: True to list "Custom" first, which is the side the frontend opens on.
        """
        inherited = selector.ConstantSelector(
            selector.ConstantSelectorConfig(value=INHERITED, label=inherited_label)
        )
        choices: dict[str, Any] = {INHERITED: {"selector": inherited}, CUSTOM: {"selector": own}}
        if own_first:
            choices = {CUSTOM: choices[CUSTOM], INHERITED: choices[INHERITED]}
        super().__init__(
            selector.ChooseSelectorConfig(
                choices=choices, translation_key=INHERITANCE_TRANSLATION_KEY
            )
        )
        self._own = own
        self._optional = optional

    def __call__(self, data: Any) -> InheritanceChoice:
        """Validate a submitted toggle.

        A plain value is accepted too: it is the form's default, which the validation applies to
        a field that was not submitted, and what a frontend that does not wrap the default sends
        back for a field left untouched.

        Raises:
            vol.Invalid: If the data is not a toggle, or a required own value is missing.
        """
        if not isinstance(data, Mapping):
            return self._from_plain_value(data)
        if data.get(ACTIVE_CHOICE) not in (INHERITED, CUSTOM):
            raise vol.Invalid("Expected an inherited or a custom value")
        if data[ACTIVE_CHOICE] == INHERITED:
            return InheritanceChoice(inherit=True)
        return self._custom_choice(data.get(CUSTOM))

    def _from_plain_value(self, data: Any) -> InheritanceChoice:
        if data == INHERITED:
            return InheritanceChoice(inherit=True)
        if data is None and not self._optional:
            raise vol.Invalid("Expected an inherited or a custom value")
        return self._custom_choice(data)

    def _custom_choice(self, value: Any) -> InheritanceChoice:
        if _is_blank(value):
            if self._optional:
                return InheritanceChoice(inherit=False)
            raise vol.Invalid("A value is required")
        return InheritanceChoice(inherit=False, value=self._own(value))


def is_overridden(setting: ResolvedSetting) -> bool:
    """Tell whether the device has its own value for a setting."""
    return setting.source is SettingSource.OVERRIDE


def initial_choice(setting: ResolvedSetting) -> Any:
    """Return the default of a toggle: the device's own value, else the inherited marker.

    It is the plain value of the first choice (see the module docstring), so it is the device's
    own value when ``is_overridden``, and ``INHERITED`` otherwise.
    """
    return setting.value if is_overridden(setting) else INHERITED


def changed_values(
    choices: Mapping[str, InheritanceChoice], stored: Mapping[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    """Return the own values to store and the keys going back to inherited.

    An own value equal to the inherited one is still stored: it pins the device to that value.
    """
    values = {
        key: choice.value
        for key, choice in choices.items()
        if not choice.inherit and (key not in stored or stored[key] != choice.value)
    }
    reset = [key for key, choice in choices.items() if choice.inherit and key in stored]
    return values, reset


class OverrideThemeStepsMixin(ThemeStepsMixin):
    """The device options: theme forms where each shareable setting is inherited or custom."""

    def _effective_and_inherited(
        self,
    ) -> tuple[dict[str, ResolvedSetting], dict[str, ResolvedSetting]]:
        """Resolve every setting twice: as the device uses it, and as it would inherit it."""
        central = HACentralConfigReader(self.hass).read_central_values()
        resolver, catalog = SettingsResolver(), SettingsCatalog()
        effective = resolver.resolve(catalog, self._shown_values(), central)
        return effective, resolver.resolve(catalog, {}, central)

    @staticmethod
    def _split(
        theme: SettingTheme,
    ) -> tuple[tuple[SettingDefinition, ...], tuple[SettingDefinition, ...]]:
        definitions = theme_definitions(theme)
        device = tuple(d for d in definitions if d.scope is SettingScope.DEVICE)
        shareable = tuple(d for d in definitions if d.scope is SettingScope.SHAREABLE)
        return device, shareable

    async def _value_words(self) -> dict[str, str]:
        """Return the words that show an empty or a boolean value, in the user's language."""
        common = await async_get_translations(
            self.hass, self.hass.config.language, "common", [DOMAIN]
        )
        return {word: common.get(f"component.{DOMAIN}.common.{word}", word) for word in VALUE_WORDS}

    def _describe(self, key: str, value: Any, words: Mapping[str, str]) -> str:
        """Show an inherited value: a sensor by its name, a switch as on/off, else as is."""
        if _is_blank(value):
            return words[NO_VALUE_TEXT]
        if isinstance(value, bool):
            return words[TRUE_TEXT] if value else words[FALSE_TEXT]
        if key.endswith(ENTITY_SUFFIX):
            return entity_label(self.hass, str(value))
        return str(value)

    async def _inheritable_schema(
        self,
        device: tuple[SettingDefinition, ...],
        shareable: tuple[SettingDefinition, ...],
    ) -> vol.Schema:
        """Build the form: the device-only fields, then a toggle per shareable setting."""
        schema = dict(build_theme_schema(self.hass, device, self._shown_values()).schema)
        effective, inherited = self._effective_and_inherited()
        words = await self._value_words()
        for definition in shareable:
            key = definition.key
            toggle = InheritableSelector(
                selector_for(key),
                self._describe(key, inherited[key].value, words),
                definition.optional,
                own_first=is_overridden(effective[key]),
            )
            schema[vol.Optional(key, default=initial_choice(effective[key]))] = toggle
        return vol.Schema(schema)

    async def _theme_step(
        self, theme: SettingTheme, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        """Show a theme; a submission stores the device fields and each inherit/custom choice."""
        device, shareable = self._split(theme)
        if not shareable:
            return await super()._theme_step(theme, user_input)
        if user_input is not None:
            stored = self._shown_values()
            keys = {d.key for d in shareable}
            choices = {k: v for k, v in user_input.items() if k in keys}
            own = normalize_theme_input(
                device, {k: v for k, v in user_input.items() if k not in keys}
            )
            values, reset = changed_values(choices, stored)
            values.update(drop_unchanged_defaults(device, own, stored))
            if values or reset:
                self._write_values(values, remove=reset)
            return await self.async_step_init()
        return self.async_show_form(
            step_id=self._step_id(theme),
            data_schema=await self._inheritable_schema(device, shareable),  # type: ignore[arg-type, unused-ignore]
        )
