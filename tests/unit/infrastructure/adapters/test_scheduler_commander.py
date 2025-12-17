"""Tests for HASchedulerCommander adapter."""
from datetime import datetime
from unittest.mock import Mock, AsyncMock

import pytest

from custom_components.intelligent_heating_pilot.infrastructure.adapters.scheduler_commander import (
    HASchedulerCommander,
    SCHEDULER_DOMAIN,
    SERVICE_RUN_ACTION,
)


@pytest.fixture
def mock_hass() -> Mock:
    """Create a mock Home Assistant instance."""
    mock = Mock()
    mock.services.async_call = AsyncMock()
    return mock


@pytest.fixture
def scheduler_entity() -> str:
    """Get scheduler entity ID."""
    return "switch.heating_schedule"


@pytest.fixture
def commander(mock_hass: Mock) -> HASchedulerCommander:
    """Create a HASchedulerCommander instance."""
    return HASchedulerCommander(mock_hass)


def test_init(commander: HASchedulerCommander, mock_hass: Mock) -> None:
    """Test adapter initialization."""
    assert commander._hass == mock_hass


@pytest.mark.asyncio
async def test_run_action_success(
    commander: HASchedulerCommander,
    mock_hass: Mock,
    scheduler_entity: str
) -> None:
    """Test running scheduler action successfully."""
    # Setup
    target_time = datetime(2024, 1, 15, 7, 30)
    
    # Execute
    await commander.run_action(target_time, scheduler_entity)
    
    # Assert
    mock_hass.services.async_call.assert_called_once_with(
        SCHEDULER_DOMAIN,
        SERVICE_RUN_ACTION,
        {
            "entity_id": scheduler_entity,
            "time": "07:30",
            "skip_conditions": False
        },
        blocking=True
    )


@pytest.mark.asyncio
async def test_run_action_no_entity(mock_hass: Mock) -> None:
    """Test running action when no entity configured."""
    # Setup: commander with no entity
    commander = HASchedulerCommander(mock_hass)
    target_time = datetime(2024, 1, 15, 7, 30)
    
    # Execute & Assert
    with pytest.raises(ValueError) as exc_info:
        await commander.run_action(target_time, "")
    
    assert "not configured" in str(exc_info.value)
    mock_hass.services.async_call.assert_not_called()


@pytest.mark.asyncio
async def test_run_action_service_fails(
    commander: HASchedulerCommander,
    mock_hass: Mock,
    scheduler_entity: str
) -> None:
    """Test handling service call failure."""
    # Setup: mock service call to raise exception
    mock_hass.services.async_call = AsyncMock(
        side_effect=Exception("Service call failed")
    )
    target_time = datetime(2024, 1, 15, 7, 30)
    
    # Execute & Assert
    with pytest.raises(Exception) as exc_info:
        await commander.run_action(target_time, scheduler_entity)
    
    assert "Service call failed" in str(exc_info.value)


@pytest.mark.asyncio
async def test_cancel_action_success(
    commander: HASchedulerCommander,
    mock_hass: Mock,
    scheduler_entity: str
) -> None:
    """Test canceling action successfully."""
    # Execute
    await commander.cancel_action(scheduler_entity)
    
    # Assert: should call service with current time
    mock_hass.services.async_call.assert_called_once()
    call_args = mock_hass.services.async_call.call_args
    
    assert call_args[0][0] == SCHEDULER_DOMAIN
    assert call_args[0][1] == SERVICE_RUN_ACTION
    
    # Check that time is in HH:MM format
    service_data = call_args[0][2]
    assert "time" in service_data
    import re
    assert re.match(r"^\d{2}:\d{2}$", service_data["time"])


@pytest.mark.asyncio
async def test_cancel_action_no_entity(mock_hass: Mock) -> None:
    """Test canceling action when no entity configured."""
    # Setup: commander with no entity
    commander = HASchedulerCommander(mock_hass)
    
    # Execute & Assert
    with pytest.raises(ValueError) as exc_info:
        await commander.cancel_action("")
    
    assert "not configured" in str(exc_info.value)
    mock_hass.services.async_call.assert_not_called()


@pytest.mark.asyncio
async def test_time_formatting(
    commander: HASchedulerCommander,
    mock_hass: Mock,
    scheduler_entity: str
) -> None:
    """Test that times are formatted correctly."""
    # Test different times
    test_cases = [
        (datetime(2024, 1, 15, 7, 30), "07:30"),
        (datetime(2024, 1, 15, 0, 0), "00:00"),
        (datetime(2024, 1, 15, 23, 59), "23:59"),
        (datetime(2024, 1, 15, 12, 5), "12:05"),
    ]
    
    for target_time, expected_str in test_cases:
        # Reset mock
        mock_hass.services.async_call.reset_mock()
        
        # Execute
        await commander.run_action(target_time, scheduler_entity)
        
        # Assert
        call_args = mock_hass.services.async_call.call_args
        service_data = call_args[0][2]
        assert service_data["time"] == expected_str
