"""Unit tests for DeadTimeCalculationService."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from custom_components.intelligent_heating_pilot.domain.services.dead_time_calculation_service import (
    DeadTimeCalculationService,
)
from custom_components.intelligent_heating_pilot.domain.value_objects.heating import HeatingCycle


@pytest.fixture
def service() -> DeadTimeCalculationService:
    """Create service instance for tests."""
    return DeadTimeCalculationService()


def _cycle(
    start_time: datetime,
    dead_time_cycle_minutes: float | None,
    device_id: str = "climate.test_vtherm",
) -> HeatingCycle:
    """Create a minimal HeatingCycle with a specific dead_time_cycle_minutes."""
    end_time = start_time + timedelta(hours=1)
    return HeatingCycle(
        device_id=device_id,
        start_time=start_time,
        end_time=end_time,
        target_temp=21.0,
        end_temp=20.0,
        start_temp=18.0,
        tariff_details=None,
        dead_time_cycle_minutes=dead_time_cycle_minutes,
    )


def test_calculate_average_dead_time_returns_none_when_no_cycles(
    service: DeadTimeCalculationService,
) -> None:
    """Return None when no cycles are provided."""
    assert service.calculate_average_dead_time([]) is None


def test_calculate_average_dead_time_returns_none_when_no_valid_dead_time(
    service: DeadTimeCalculationService,
) -> None:
    """Return None when all cycles have invalid dead_time values."""
    base_time = datetime(2025, 1, 1, 8, 0, 0)
    cycles = [
        _cycle(base_time, None),
        _cycle(base_time + timedelta(hours=1), 0.0),
        _cycle(base_time + timedelta(hours=2), -5.0),
    ]

    assert service.calculate_average_dead_time(cycles) is None


def test_calculate_average_dead_time_ignores_invalid_dead_times(
    service: DeadTimeCalculationService,
) -> None:
    """Ignore None/zero/negative values and average valid ones."""
    base_time = datetime(2025, 1, 1, 8, 0, 0)
    cycles = [
        _cycle(base_time, None),
        _cycle(base_time + timedelta(hours=1), 0.0),
        _cycle(base_time + timedelta(hours=2), 8.0),
        _cycle(base_time + timedelta(hours=3), -2.0),
        _cycle(base_time + timedelta(hours=4), 12.0),
    ]

    result = service.calculate_average_dead_time(cycles)

    assert result == pytest.approx(10.0)


def test_calculate_average_dead_time_single_valid_cycle(
    service: DeadTimeCalculationService,
) -> None:
    """Return the dead_time value when exactly one valid cycle exists."""
    base_time = datetime(2025, 1, 1, 8, 0, 0)
    cycles = [
        _cycle(base_time, 7.5),
        _cycle(base_time + timedelta(hours=1), None),
    ]

    result = service.calculate_average_dead_time(cycles)

    assert result == pytest.approx(7.5)


def test_calculate_average_dead_time_multiple_valid_cycles(
    service: DeadTimeCalculationService,
) -> None:
    """Return the average across multiple valid cycles."""
    base_time = datetime(2025, 1, 1, 8, 0, 0)
    cycles = [
        _cycle(base_time, 5.0),
        _cycle(base_time + timedelta(hours=1), 10.0),
        _cycle(base_time + timedelta(hours=2), 15.0),
    ]

    result = service.calculate_average_dead_time(cycles)

    assert result == pytest.approx(10.0)
