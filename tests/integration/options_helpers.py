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

INHERIT: dict[str, Any] = {"active_choice": "inherited", "inherited": "inherited"}


def custom(value: Any) -> dict[str, Any]:
    """Return what the frontend sends for a setting switched to "Custom" with this value.

    ``None`` is a custom setting left empty: "no sensor" for an optional sensor.
    """
    toggle: dict[str, Any] = {"active_choice": "custom", "inherited": "inherited"}
    if value is not None:
        toggle["custom"] = value
    return toggle


def _as_submitted(theme: str, values: dict[str, Any]) -> dict[str, Any]:
    """Wrap the shareable values of a theme in their "Custom" toggle; device values are as is."""
    scope = {d.key: d.scope for d in SettingsCatalog().of_theme(SettingTheme(theme))}
    return {
        key: custom(value) if scope.get(key) is SettingScope.SHAREABLE else value
        for key, value in values.items()
    }


async def save_theme(hass: HomeAssistant, flow_id: str, theme: str, values: dict[str, Any]) -> Any:
    """Open a theme and submit it, with each shareable setting in ``values`` set to custom.

    The settings left out keep the state the form opened with.

    Args:
        hass: Home Assistant.
        flow_id: The options flow, at its menu.
        theme: The theme to open.
        values: What to submit; a shareable setting gets this value of its own.

    Returns:
        The result after the form: the menu.
    """
    manager = hass.config_entries.options
    form = await manager.async_configure(flow_id, {"next_step_id": theme})
    assert form["type"] == "form", form
    return await manager.async_configure(form["flow_id"], _as_submitted(theme, values))
