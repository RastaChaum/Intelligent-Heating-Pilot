"""Tests for HacsRunActionActuator (formerly HASchedulerCommander)."""

import re
from datetime import datetime
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.intelligent_heating_pilot.domain.value_objects import (
    ActuationResult,
    CancelReason,
    ScheduledTimeslot,
)
from custom_components.intelligent_heating_pilot.infrastructure.adapters.hacs_run_action_actuator import (
    SCHEDULER_DOMAIN,
    SERVICE_RUN_ACTION,
    HacsRunActionActuator,
)


def _slot(target_time: datetime, entity: str = "switch.heating_schedule") -> ScheduledTimeslot:
    return ScheduledTimeslot(
        target_time=target_time, target_temp=21.0, timeslot_id="slot", scheduler_entity=entity
    )


@pytest.fixture
def mock_hass() -> Mock:
    mock = Mock()
    mock.services.async_call = AsyncMock()
    return mock


@pytest.fixture
def actuator(mock_hass: Mock) -> HacsRunActionActuator:
    return HacsRunActionActuator(mock_hass)


def test_init(actuator: HacsRunActionActuator, mock_hass: Mock) -> None:
    assert actuator._hass == mock_hass


@pytest.mark.asyncio
async def test_start_triggers_run_action_and_reports_an_attempt(actuator, mock_hass) -> None:
    result = await actuator.start(_slot(datetime(2024, 1, 15, 7, 30)))

    assert result is ActuationResult.ATTEMPTED
    mock_hass.services.async_call.assert_called_once_with(
        SCHEDULER_DOMAIN,
        SERVICE_RUN_ACTION,
        {"entity_id": "switch.heating_schedule", "time": "07:30", "skip_conditions": False},
        blocking=True,
    )


@pytest.mark.asyncio
async def test_start_never_bypasses_conditions(actuator, mock_hass) -> None:
    """Regression guard for FR-003: the actuation call must always respect the
    scheduler's own conditions, even after the bool-return change (#64)."""
    await actuator.start(_slot(datetime(2024, 1, 15, 7, 30)))

    _, _, service_data = mock_hass.services.async_call.call_args[0]
    assert service_data["skip_conditions"] is False


@pytest.mark.asyncio
async def test_start_without_an_entity_raises(actuator, mock_hass) -> None:
    with pytest.raises(ValueError) as exc_info:
        await actuator.start(_slot(datetime(2024, 1, 15, 7, 30), entity=""))

    assert "not configured" in str(exc_info.value)
    mock_hass.services.async_call.assert_not_called()


@pytest.mark.asyncio
async def test_start_propagates_a_service_failure(actuator, mock_hass) -> None:
    mock_hass.services.async_call = AsyncMock(side_effect=Exception("Service call failed"))

    with pytest.raises(Exception) as exc_info:
        await actuator.start(_slot(datetime(2024, 1, 15, 7, 30)))

    assert "Service call failed" in str(exc_info.value)


@pytest.mark.asyncio
async def test_cancel_reverts_to_the_current_time(actuator, mock_hass) -> None:
    await actuator.cancel(_slot(datetime(2024, 1, 15, 7, 30)), CancelReason.SLOT_CHANGED)

    call_args = mock_hass.services.async_call.call_args
    assert call_args[0][0] == SCHEDULER_DOMAIN
    assert call_args[0][1] == SERVICE_RUN_ACTION
    assert re.match(r"^\d{2}:\d{2}$", call_args[0][2]["time"])


@pytest.mark.asyncio
async def test_cancel_without_an_entity_raises(actuator, mock_hass) -> None:
    with pytest.raises(ValueError) as exc_info:
        await actuator.cancel(
            _slot(datetime(2024, 1, 15, 7, 30), entity=""), CancelReason.IHP_DISABLED
        )

    assert "not configured" in str(exc_info.value)
    mock_hass.services.async_call.assert_not_called()


@pytest.mark.asyncio
async def test_cancel_once_the_slot_is_reached_sends_nothing(actuator, mock_hass) -> None:
    """The scheduler already applied its own action: reverting would undo it."""
    await actuator.cancel(_slot(datetime(2024, 1, 15, 7, 30)), CancelReason.SLOT_REACHED)

    mock_hass.services.async_call.assert_not_called()


@pytest.mark.asyncio
async def test_time_formatting(actuator, mock_hass) -> None:
    cases = [
        (datetime(2024, 1, 15, 7, 30), "07:30"),
        (datetime(2024, 1, 15, 0, 0), "00:00"),
        (datetime(2024, 1, 15, 23, 59), "23:59"),
        (datetime(2024, 1, 15, 12, 5), "12:05"),
    ]
    for target_time, expected in cases:
        mock_hass.services.async_call.reset_mock()
        await actuator.start(_slot(target_time))
        assert mock_hass.services.async_call.call_args[0][2]["time"] == expected


@pytest.mark.asyncio
async def test_start_on_a_native_schedule_calls_no_service(actuator, mock_hass) -> None:
    """A native schedule.* entity is never sent HACS' run_action (ServiceNotFound otherwise)."""
    result = await actuator.start(_slot(datetime(2024, 1, 15, 7, 0), entity="schedule.heating"))

    assert result is ActuationResult.UNSUPPORTED
    mock_hass.services.async_call.assert_not_called()


@pytest.mark.asyncio
async def test_cancel_on_a_native_schedule_calls_no_service(actuator, mock_hass) -> None:
    await actuator.cancel(
        _slot(datetime(2024, 1, 15, 7, 0), entity="schedule.heating"), CancelReason.SLOT_CHANGED
    )

    mock_hass.services.async_call.assert_not_called()


@pytest.mark.asyncio
async def test_recover_has_nothing_to_recover(actuator) -> None:
    assert await actuator.recover(_slot(datetime(2024, 1, 15, 7, 30))) is False
