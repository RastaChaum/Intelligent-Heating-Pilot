"""The central configuration entry: the values every device inherits unless it overrides (#302).

The central configuration is a config entry of this domain, marked by ``entry_type: central``.
It is created automatically with the first device, it creates no coordinator and no entity, and
applying its changes reloads only the devices that inherit a changed value. This module is the
translation layer: which keys are shareable comes from the domain catalog.
"""

from __future__ import annotations

import logging
from collections.abc import Collection, Mapping, Sequence
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import SOURCE_IMPORT

from ...const import (
    CENTRAL_APPLIED_KEY,
    CONF_ENTRY_TYPE,
    DOMAIN,
    ENTRY_TYPE_CENTRAL,
)
from ...domain.services.settings_catalog import SettingsCatalog

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


def is_central_entry(entry: ConfigEntry) -> bool:
    """Tell whether an entry is the central configuration (a device has no ``entry_type``)."""
    return entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_CENTRAL


def find_central_entry(hass: HomeAssistant) -> ConfigEntry | None:
    """Return the central entry, or ``None`` when there is none."""
    return next(
        (entry for entry in hass.config_entries.async_entries(DOMAIN) if is_central_entry(entry)),
        None,
    )


def device_entries(hass: HomeAssistant) -> list[ConfigEntry]:
    """Return every device entry, leaving out the central configuration."""
    return [e for e in hass.config_entries.async_entries(DOMAIN) if not is_central_entry(e)]


def central_values_of(entry: ConfigEntry) -> dict[str, Any]:
    """Return the shareable values a central entry stores, ignoring any other key."""
    shareable = {definition.key for definition in SettingsCatalog().shareable()}
    return {key: value for key, value in entry.options.items() if key in shareable}


async def _create_central_entry(hass: HomeAssistant) -> None:
    """Run the import flow of the central entry; a failure is logged, never raised.

    The next device setup tries again, so a transient failure only delays the entry.
    """
    try:
        await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_IMPORT}, data={CONF_ENTRY_TYPE: ENTRY_TYPE_CENTRAL}
        )
    except Exception:
        _LOGGER.warning("The central configuration could not be created", exc_info=True)


def ensure_central_entry(hass: HomeAssistant) -> None:
    """Start the import flow that creates the central entry; a no-op when it exists.

    The flow runs in the background: it must not block the setup of a device, and its fixed
    unique id makes a second flow abort, so calling this once per device setup is harmless.
    """
    if find_central_entry(hass) is not None:
        return
    _LOGGER.info("Creating the central configuration")
    hass.async_create_task(_create_central_entry(hass))


def applied_central_values(hass: HomeAssistant) -> Mapping[str, Any] | None:
    """Return the central values the devices were last reloaded with, if known."""
    applied: Mapping[str, Any] | None = hass.data.get(DOMAIN, {}).get(CENTRAL_APPLIED_KEY)
    return applied


def set_applied_central_values(hass: HomeAssistant, values: Mapping[str, Any]) -> None:
    """Remember the central values the devices run with."""
    hass.data.setdefault(DOMAIN, {})[CENTRAL_APPLIED_KEY] = dict(values)


_MISSING: Any = object()


def changed_central_keys(entry: ConfigEntry, applied: Mapping[str, Any] | None) -> set[str]:
    """Return the central keys whose stored value differs from the applied one.

    Without an applied snapshot nothing is known to be unapplied.
    """
    if applied is None:
        return set()
    stored = central_values_of(entry)
    return {
        key
        for key in set(stored) | set(applied)
        if stored.get(key, _MISSING) != applied.get(key, _MISSING)
    }


def devices_to_reload(
    entries: Sequence[ConfigEntry], changed_keys: Collection[str]
) -> list[ConfigEntry]:
    """Return the devices that inherit at least one changed key.

    A device inherits a key when it holds no value of its own for it; a device that overrides
    every changed key is left alone.
    """
    reloads = []
    for entry in entries:
        held = {**entry.data, **entry.options}
        if any(key not in held for key in changed_keys):
            reloads.append(entry)
    return reloads


async def _reload_each(hass: HomeAssistant, entries: Sequence[ConfigEntry]) -> None:
    """Reload devices one by one; a failure is logged and does not stop the others."""
    for entry in entries:
        try:
            _LOGGER.info("[%s] Reloading: an inherited central value changed", entry.title)
            await hass.config_entries.async_reload(entry.entry_id)
        except Exception:
            _LOGGER.exception("[%s] Reload after a central change failed", entry.title)


def apply_central_changes(hass: HomeAssistant, central: ConfigEntry) -> list[ConfigEntry]:
    """Reload, in the background, the devices that inherit a changed central value.

    Returns:
        The devices scheduled for a reload.
    """
    changed = changed_central_keys(central, applied_central_values(hass))
    set_applied_central_values(hass, central_values_of(central))
    reloads = devices_to_reload(device_entries(hass), changed) if changed else []
    if reloads:
        _LOGGER.info(
            "Central values changed (%s): %d device(s) to reload", sorted(changed), len(reloads)
        )
        hass.async_create_task(_reload_each(hass, reloads))
    return reloads


def has_unapplied_central_changes(hass: HomeAssistant, central: ConfigEntry) -> bool:
    """Tell whether the stored central values differ from those the devices run with."""
    return bool(changed_central_keys(central, applied_central_values(hass)))
