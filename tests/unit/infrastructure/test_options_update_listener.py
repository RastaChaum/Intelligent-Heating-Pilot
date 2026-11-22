"""The entry update listener applies the live toggle only: options wait for "Apply" (#302)."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.intelligent_heating_pilot import async_update_options
from custom_components.intelligent_heating_pilot.const import (
    CONF_IHP_ENABLED,
    CONF_LHS_RETENTION_DAYS,
    DOMAIN,
)


def _setup(options: dict, applied: bool = True) -> tuple[Mock, Mock, Mock]:
    coordinator = Mock()
    coordinator.ihp_enabled_applied = applied
    coordinator.async_update = AsyncMock()
    entry = Mock(entry_id="device", options=options)
    hass = Mock()
    hass.data = {DOMAIN: {"device": coordinator}}
    hass.config_entries.async_reload = AsyncMock()
    return hass, entry, coordinator


@pytest.mark.asyncio
async def test_an_option_change_does_not_reload_or_recalculate() -> None:
    hass, entry, coordinator = _setup({CONF_LHS_RETENTION_DAYS: 60})

    await async_update_options(hass, entry)

    hass.config_entries.async_reload.assert_not_called()
    coordinator.async_update.assert_not_called()


@pytest.mark.asyncio
async def test_the_live_toggle_is_still_applied_at_once() -> None:
    hass, entry, coordinator = _setup({CONF_IHP_ENABLED: False}, applied=True)

    await async_update_options(hass, entry)

    coordinator.async_update.assert_awaited_once()
    assert coordinator.ihp_enabled_applied is False
    hass.config_entries.async_reload.assert_not_called()


@pytest.mark.asyncio
async def test_the_toggle_is_applied_once() -> None:
    hass, entry, coordinator = _setup({CONF_IHP_ENABLED: False}, applied=True)

    await async_update_options(hass, entry)
    await async_update_options(hass, entry)

    coordinator.async_update.assert_awaited_once()


@pytest.mark.asyncio
async def test_an_entry_without_a_coordinator_is_ignored() -> None:
    hass, entry, _ = _setup({})
    hass.data = {DOMAIN: {}}

    await async_update_options(hass, entry)

    hass.config_entries.async_reload.assert_not_called()
