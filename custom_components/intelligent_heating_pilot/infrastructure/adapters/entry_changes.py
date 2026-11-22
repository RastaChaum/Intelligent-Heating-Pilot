"""What a device entry holds that its running coordinator has not applied yet (#302).

Saving a theme writes the entry at once and does not reload the device. The coordinator keeps a
snapshot of the values it was loaded with, so "unapplied" is simply the difference between the
stored entry and that snapshot. This module only translates entries into that comparison; the
meaning of the keys comes from the domain catalog.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from typing import TYPE_CHECKING, Any

from ...const import CONF_IHP_ENABLED
from ...domain.services.settings_catalog import SettingsCatalog
from ...domain.value_objects.setting_definition import SettingTheme

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

# The live toggle is applied by the update listener, not by a reload.
IGNORED_KEYS = frozenset({CONF_IHP_ENABLED})
THEME_ORDER = tuple(SettingTheme)


def effective_values(entry: ConfigEntry) -> dict[str, Any]:
    """Return what the entry holds: its data overridden by its options, minus the live toggle."""
    merged: dict[str, Any] = {**entry.data, **entry.options}
    return {key: value for key, value in merged.items() if key not in IGNORED_KEYS}


def unapplied_keys(entry: ConfigEntry, applied: Mapping[str, Any] | None) -> set[str]:
    """Return the keys whose stored value differs from the one the device was loaded with.

    Args:
        entry: The device entry as stored.
        applied: The snapshot taken when the device was loaded; ``None`` when it is not loaded.

    Returns:
        Every key that was added, removed or changed since the snapshot; empty without one.
    """
    if applied is None:
        return set()
    stored = effective_values(entry)
    keys = set(stored) | set(applied)
    return {key for key in keys if stored.get(key, _MISSING) != applied.get(key, _MISSING)}


def themes_of(keys: Collection[str], catalog: SettingsCatalog | None = None) -> list[SettingTheme]:
    """Map changed keys to the themes they belong to, in display order.

    Keys the catalog does not declare (the name, for instance) belong to no theme.
    """
    catalog = catalog or SettingsCatalog()
    found = {definition.theme for definition in catalog.all() if definition.key in keys}
    return [theme for theme in THEME_ORDER if theme in found]


class _Missing:
    def __repr__(self) -> str:
        return "<missing>"


_MISSING = _Missing()
