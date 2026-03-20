"""Tests for HADeviceConfigReader adapter."""

from unittest.mock import Mock

import pytest

from custom_components.intelligent_heating_pilot.const import (
    CONF_ANTICIPATION_RECALC_TOLERANCE_MINUTES,
    CONF_AUTO_LEARNING,
    CONF_DEAD_TIME_MINUTES,
    CONF_LHS_RETENTION_DAYS,
    CONF_SCHEDULER_ENTITIES,
    CONF_VTHERM_ENTITY,
    DEFAULT_ANTICIPATION_RECALC_TOLERANCE_MINUTES,
    DEFAULT_AUTO_LEARNING,
    DEFAULT_DEAD_TIME_MINUTES,
    DEFAULT_LHS_RETENTION_DAYS,
)
from custom_components.intelligent_heating_pilot.infrastructure.adapters.device_config_reader import (
    HADeviceConfigReader,
)


@pytest.fixture
def mock_hass() -> Mock:
    """Create a mock Home Assistant instance."""
    return Mock()


@pytest.fixture
def mock_config_entry() -> Mock:
    """Create a mock config entry with default values."""
    config_entry = Mock()
    config_entry.entry_id = "test_device_id"
    config_entry.data = {
        CONF_VTHERM_ENTITY: "climate.vtherm",
        CONF_SCHEDULER_ENTITIES: ["switch.schedule1"],
    }
    config_entry.options = {}
    return config_entry


@pytest.mark.asyncio
async def test_get_device_config_with_zero_values_in_options(
    mock_hass: Mock, mock_config_entry: Mock
) -> None:
    """Test that config values of 0 are not ignored when set in options.

    This is a regression test for the bug where:
    - User sets lhs_retention_days=0, dead_time_minutes=0
    - But code used 'value or DEFAULT' which treated 0 as falsy
    - Result: defaults were used instead of configured 0 values
    """
    # Setup: User explicitly configures values of 0 in options
    mock_config_entry.options = {
        CONF_LHS_RETENTION_DAYS: 0,  # User wants 0 days retention
        CONF_DEAD_TIME_MINUTES: 0,  # User wants 0 dead time
    }

    reader = HADeviceConfigReader(mock_hass, mock_config_entry)

    # Execute
    device_config = await reader.get_device_config("test_device_id")

    # Assert: Configured 0 values should be used, not defaults
    assert device_config.lhs_retention_days == 0, (
        f"Expected lhs_retention_days=0 but got {device_config.lhs_retention_days}. "
        "Config value of 0 was ignored and default was used instead!"
    )
    assert device_config.dead_time_minutes == 0.0, (
        f"Expected dead_time_minutes=0.0 but got {device_config.dead_time_minutes}. "
        "Config value of 0 was ignored and default was used instead!"
    )


@pytest.mark.asyncio
async def test_get_device_config_with_false_auto_learning(
    mock_hass: Mock, mock_config_entry: Mock
) -> None:
    """Test that auto_learning=False is not ignored when set in options.

    This is a regression test for the bug where:
    - User sets auto_learning=False
    - But code used 'value or DEFAULT' which treated False as falsy
    - Result: DEFAULT (True) was used instead of configured False
    """
    # Setup: User explicitly disables auto_learning
    mock_config_entry.options = {
        CONF_AUTO_LEARNING: False,
    }

    reader = HADeviceConfigReader(mock_hass, mock_config_entry)

    # Execute
    device_config = await reader.get_device_config("test_device_id")

    # Assert: Configured False value should be used, not default True
    assert device_config.auto_learning is False, (
        f"Expected auto_learning=False but got {device_config.auto_learning}. "
        "Config value of False was ignored and default True was used instead!"
    )


@pytest.mark.asyncio
async def test_get_device_config_uses_defaults_when_not_configured(
    mock_hass: Mock, mock_config_entry: Mock
) -> None:
    """Test that defaults are used when config values are not set (None)."""
    # Setup: No optional config values set (neither in data nor options)
    mock_config_entry.data = {
        CONF_VTHERM_ENTITY: "climate.vtherm",
        CONF_SCHEDULER_ENTITIES: ["switch.schedule1"],
    }
    mock_config_entry.options = {}

    reader = HADeviceConfigReader(mock_hass, mock_config_entry)

    # Execute
    device_config = await reader.get_device_config("test_device_id")

    # Assert: Defaults should be used
    assert device_config.lhs_retention_days == DEFAULT_LHS_RETENTION_DAYS
    assert device_config.dead_time_minutes == DEFAULT_DEAD_TIME_MINUTES
    assert device_config.auto_learning == DEFAULT_AUTO_LEARNING
    assert (
        device_config.anticipation_recalc_tolerance_minutes
        == DEFAULT_ANTICIPATION_RECALC_TOLERANCE_MINUTES
    )


@pytest.mark.asyncio
async def test_get_device_config_with_valid_non_zero_values(
    mock_hass: Mock, mock_config_entry: Mock
) -> None:
    """Test that valid non-zero config values are correctly used."""
    # Setup: User configures specific non-default values
    mock_config_entry.options = {
        CONF_LHS_RETENTION_DAYS: 60,
        CONF_DEAD_TIME_MINUTES: 15.5,
        CONF_AUTO_LEARNING: True,
        CONF_ANTICIPATION_RECALC_TOLERANCE_MINUTES: 12,
    }

    reader = HADeviceConfigReader(mock_hass, mock_config_entry)

    # Execute
    device_config = await reader.get_device_config("test_device_id")

    # Assert: Configured values should be used
    assert device_config.lhs_retention_days == 60
    assert device_config.dead_time_minutes == 15.5
    assert device_config.auto_learning is True
    assert device_config.anticipation_recalc_tolerance_minutes == 12
