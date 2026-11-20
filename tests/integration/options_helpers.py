"""Drive the theme forms of the device options as a user does (#302)."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from custom_components.intelligent_heating_pilot.domain.services.settings_catalog import (
    SettingsCatalog,
)
from custom_components.intelligent_heating_pilot.domain.value_objects.setting_definition import (
    SettingScope,
    SettingTheme,
)

PICKER = "overridden_settings"


def _split(theme: str, values: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Split submitted values into the device-only ones and the shareable (overridden) ones."""
    scope = {d.key: d.scope for d in SettingsCatalog().of_theme(SettingTheme(theme))}
    device = {k: v for k, v in values.items() if scope.get(k) is SettingScope.DEVICE}
    shared = {k: v for k, v in values.items() if scope.get(k) is SettingScope.SHAREABLE}
    return device, shared


async def save_theme(
    hass: HomeAssistant,
    flow_id: str,
    theme: str,
    values: dict[str, Any],
    *,
    keep: list[str] | None = None,
) -> Any:
    """Open a theme, override the shareable settings in ``values`` and submit them.

    Args:
        hass: Home Assistant.
        flow_id: The options flow, at its menu.
        theme: The theme to open.
        values: What to submit; shareable settings are overridden with these values.
        keep: Shareable settings to keep overridden without changing them.

    Returns:
        The result after the last form: the menu.
    """
    manager = hass.config_entries.options
    form = await manager.async_configure(flow_id, {"next_step_id": theme})
    assert form["type"] == "form", form
    device, shared = _split(theme, values)
    submitted = dict(device)
    selected = [*shared, *(keep or [])]
    if PICKER in form["data_schema"].schema.__repr__() or any(
        str(key) == PICKER for key in form["data_schema"].schema
    ):
        submitted[PICKER] = selected
    result = await manager.async_configure(form["flow_id"], submitted)
    if result["type"] == "form":  # the values of the overridden settings
        result = await manager.async_configure(result["flow_id"], shared)
    return result
