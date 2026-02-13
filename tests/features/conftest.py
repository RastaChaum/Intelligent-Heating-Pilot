"""pytest-bdd configuration and shared fixtures for BDD tests.

This file provides shared fixtures and configuration for all BDD feature tests.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from custom_components.intelligent_heating_pilot.domain.value_objects.heating import HeatingCycle


@pytest.fixture
def base_datetime() -> datetime:
    """Base datetime for BDD scenarios."""
    return datetime(2025, 2, 10, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def device_id() -> str:
    """Device ID for BDD scenarios."""
    return "climate.test_vtherm"


def create_test_heating_cycle(
    device_id: str,
    start_time: datetime,
    duration_hours: float = 1.0,
    target_temp: float = 20.5,
    end_temp: float = 20.0,
    start_temp: float = 18.0,
) -> HeatingCycle:
    """Helper to create a test heating cycle for BDD scenarios.

    Args:
        device_id: The device identifier
        start_time: When the heating cycle started
        duration_hours: Duration of the cycle in hours
        target_temp: Target temperature
        end_temp: Temperature at end of cycle
        start_temp: Temperature at start of cycle

    Returns:
        A HeatingCycle instance for testing
    """
    end_time = start_time + timedelta(hours=duration_hours)
    return HeatingCycle(
        device_id=device_id,
        start_time=start_time,
        end_time=end_time,
        target_temp=target_temp,
        end_temp=end_temp,
        start_temp=start_temp,
        tariff_details=None,
    )
