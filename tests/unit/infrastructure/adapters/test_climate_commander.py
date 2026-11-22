"""Tests for HAClimateCommander: applying a slot action and restoring fields."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest

from custom_components.intelligent_heating_pilot.domain.value_objects import (
    RestoreFields,
    SlotAction,
)
from custom_components.intelligent_heating_pilot.infrastructure.adapters.climate_commander import (
    HAClimateCommander,
)

MODULE = "custom_components.intelligent_heating_pilot.infrastructure.adapters.climate_commander"


@pytest.fixture
def mock_hass() -> Mock:
    hass = Mock()
    hass.services.async_call = AsyncMock()
    return hass


@pytest.fixture
def commander(mock_hass: Mock) -> HAClimateCommander:
    with patch(f"{MODULE}.get_entity_name", return_value="Living Room"):
        return HAClimateCommander(mock_hass, "climate.vtherm")


def _call(mock_hass: Mock):
    mock_hass.services.async_call.assert_awaited_once()
    return mock_hass.services.async_call.await_args


@pytest.mark.asyncio
async def test_a_preset_action_is_applied_as_a_preset(commander, mock_hass) -> None:
    await commander.apply(SlotAction(preset="comfort"))

    call = _call(mock_hass)
    assert call.args == (
        "climate",
        "set_preset_mode",
        {"entity_id": "climate.vtherm", "preset_mode": "comfort"},
    )


@pytest.mark.asyncio
async def test_a_temperature_action_is_applied_as_a_temperature(commander, mock_hass) -> None:
    await commander.apply(SlotAction(temperature=21.5))

    call = _call(mock_hass)
    assert call.args == (
        "climate",
        "set_temperature",
        {"entity_id": "climate.vtherm", "temperature": 21.5},
    )


@pytest.mark.asyncio
async def test_the_preset_wins_when_the_action_carries_both(commander, mock_hass) -> None:
    await commander.apply(SlotAction(preset="comfort", temperature=21.0))

    assert _call(mock_hass).args[1] == "set_preset_mode"


@pytest.mark.asyncio
async def test_every_command_carries_a_context_with_a_parent(commander, mock_hass) -> None:
    """Schedulers that watch for manual changes ignore a change whose context has a parent."""
    await commander.apply(SlotAction(preset="comfort"))

    context = _call(mock_hass).kwargs["context"]
    assert context.parent_id is not None
    assert _call(mock_hass).kwargs["blocking"] is True


@pytest.mark.asyncio
async def test_each_command_gets_its_own_context(commander, mock_hass) -> None:
    await commander.apply(SlotAction(preset="comfort"))
    first = mock_hass.services.async_call.await_args.kwargs["context"]
    mock_hass.services.async_call.reset_mock()
    await commander.apply(SlotAction(preset="eco"))
    second = mock_hass.services.async_call.await_args.kwargs["context"]

    assert first.id != second.id


@pytest.mark.asyncio
async def test_restore_writes_the_preset_when_given(commander, mock_hass) -> None:
    await commander.restore(RestoreFields(preset="eco"))

    call = _call(mock_hass)
    assert call.args[1] == "set_preset_mode"
    assert call.args[2]["preset_mode"] == "eco"
    assert call.kwargs["context"].parent_id is not None


@pytest.mark.asyncio
async def test_restore_writes_the_temperature_when_there_is_no_preset(commander, mock_hass) -> None:
    await commander.restore(RestoreFields(temperature=19.0))

    call = _call(mock_hass)
    assert call.args[1] == "set_temperature"
    assert call.args[2]["temperature"] == 19.0


@pytest.mark.asyncio
async def test_restore_writes_nothing_when_there_is_nothing_to_restore(
    commander, mock_hass
) -> None:
    await commander.restore(RestoreFields())

    mock_hass.services.async_call.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_command_ever_touches_the_hvac_mode(commander, mock_hass) -> None:
    await commander.apply(SlotAction(preset="comfort"))
    await commander.apply(SlotAction(temperature=21.0))
    await commander.restore(RestoreFields(preset="eco"))
    await commander.restore(RestoreFields(temperature=19.0))

    services = {call.args[1] for call in mock_hass.services.async_call.await_args_list}
    assert services == {"set_preset_mode", "set_temperature"}


@pytest.mark.asyncio
async def test_only_the_configured_climate_is_addressed(commander, mock_hass) -> None:
    """FR-004: each room has its own anticipation, so IHP touches only its own climate."""
    await commander.apply(SlotAction(preset="comfort"))
    await commander.restore(RestoreFields(preset="eco"))

    targets = {call.args[2]["entity_id"] for call in mock_hass.services.async_call.await_args_list}
    assert targets == {"climate.vtherm"}


@pytest.mark.asyncio
async def test_each_application_and_restoration_logs_at_info_with_the_friendly_name(
    commander, caplog
) -> None:
    with caplog.at_level("INFO", logger=MODULE):
        await commander.apply(SlotAction(preset="comfort"))
        await commander.restore(RestoreFields(preset="eco"))

    messages = [r.getMessage() for r in caplog.records if r.levelname == "INFO"]
    assert len(messages) == 2
    assert all("Living Room" in message for message in messages)
    assert all("climate.vtherm" not in message for message in messages)
