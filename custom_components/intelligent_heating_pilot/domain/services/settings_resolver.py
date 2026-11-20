"""Resolution of the effective value of each setting of a device (#302)."""

from __future__ import annotations

from collections.abc import Mapping

from ..value_objects.resolved_setting import ResolvedSetting, SettingSource
from ..value_objects.setting_definition import SettingDefinition, SettingScope
from .settings_catalog import SettingsCatalog


class SettingsResolver:
    """Pure rule: a device's own value, else the central value, else the built-in default.

    The rule is stateless and knows nothing about config entries: the infrastructure hands it
    the stored values, so it can be tested and reasoned about without Home Assistant.
    """

    def resolve(
        self,
        catalog: SettingsCatalog,
        device_values: Mapping[str, object | None],
        central_values: Mapping[str, object | None],
    ) -> dict[str, ResolvedSetting]:
        """Resolve every setting of the catalog.

        Args:
            catalog: The declared settings.
            device_values: What the device stores; a key present is an override, even when its
                value is ``None`` (an optional setting set to "none") or equals the central one.
            central_values: What the central configuration stores; empty when there is none.

        Returns:
            The effective setting per key.
        """
        return {
            definition.key: self._resolve_one(definition, device_values, central_values)
            for definition in catalog.all()
        }

    @staticmethod
    def _resolve_one(
        definition: SettingDefinition,
        device_values: Mapping[str, object | None],
        central_values: Mapping[str, object | None],
    ) -> ResolvedSetting:
        key = definition.key
        if key in device_values:
            return ResolvedSetting(key, device_values[key], SettingSource.OVERRIDE)
        # A device-only setting is never read from the central values, even if they hold the key.
        if definition.scope is SettingScope.SHAREABLE and key in central_values:
            return ResolvedSetting(key, central_values[key], SettingSource.CENTRAL)
        return ResolvedSetting(key, definition.default, SettingSource.DEFAULT)
