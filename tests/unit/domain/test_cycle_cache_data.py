"""Tests for CycleCacheData value object."""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone, timedelta

import pytest

# Add custom_components to path
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(__file__),
        "../../../custom_components/intelligent_heating_pilot",
    ),
)

from domain.value_objects import CycleCacheData
from .fixtures import create_test_heating_cycle, TEST_DEVICE_ID


@pytest.fixture
def base_time() -> datetime:
    """Get base time for tests."""
    return datetime(2025, 12, 18, 14, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def device_id() -> str:
    """Get device ID for tests."""
    return TEST_DEVICE_ID


def test_creation_with_valid_data(base_time: datetime, device_id: str) -> None:
    """Test creating CycleCacheData with valid data."""
    cycles = [
        create_test_heating_cycle(device_id, base_time),
        create_test_heating_cycle(device_id, base_time + timedelta(hours=2)),
    ]
    
    cache_data = CycleCacheData(
        device_id=device_id,
        cycles=tuple(cycles),
        last_search_time=base_time + timedelta(hours=4),
        retention_days=30,
    )
    
    assert cache_data.device_id == device_id
    assert len(cache_data.cycles) == 2
    assert cache_data.retention_days == 30
    assert cache_data.cycle_count == 2


def test_immutability(base_time: datetime, device_id: str) -> None:
    """Test that CycleCacheData is immutable."""
    cycles = [create_test_heating_cycle(device_id, base_time)]
    
    cache_data = CycleCacheData(
        device_id=device_id,
        cycles=tuple(cycles),
        last_search_time=base_time,
        retention_days=30,
    )
    
    # Attempting to modify should raise error
    with pytest.raises(AttributeError):
        cache_data.device_id = "different_id"  # type: ignore[misc]
    
    with pytest.raises(AttributeError):
        cache_data.cycles = tuple()  # type: ignore[misc]


def test_empty_device_id_raises_error(base_time: datetime) -> None:
    """Test that empty device_id raises ValueError."""
    cycles = [create_test_heating_cycle("test", base_time)]
    
    with pytest.raises(ValueError, match="device_id"):
        CycleCacheData(
            device_id="",
            cycles=tuple(cycles),
            last_search_time=base_time,
            retention_days=30,
        )


def test_negative_retention_days_raises_error(base_time: datetime, device_id: str) -> None:
    """Test that negative retention_days raises ValueError."""
    cycles = [create_test_heating_cycle(device_id, base_time)]
    
    with pytest.raises(ValueError, match="retention_days"):
        CycleCacheData(
            device_id=device_id,
            cycles=tuple(cycles),
            last_search_time=base_time,
            retention_days=-1,
        )


def test_zero_retention_days_raises_error(base_time: datetime, device_id: str) -> None:
    """Test that zero retention_days raises ValueError."""
    cycles = [create_test_heating_cycle(device_id, base_time)]
    
    with pytest.raises(ValueError, match="retention_days"):
        CycleCacheData(
            device_id=device_id,
            cycles=tuple(cycles),
            last_search_time=base_time,
            retention_days=0,
        )


def test_naive_timestamp_raises_error(device_id: str) -> None:
    """Test that timezone-naive timestamp raises ValueError."""
    cycles = [create_test_heating_cycle(device_id, datetime(2025, 12, 18, 14, 0, 0, tzinfo=timezone.utc))]
    naive_time = datetime(2025, 12, 18, 14, 0, 0)  # No timezone
    
    with pytest.raises(ValueError, match="timezone-aware"):
        CycleCacheData(
            device_id=device_id,
            cycles=tuple(cycles),
            last_search_time=naive_time,
            retention_days=30,
        )


def test_cycle_count_property(base_time: datetime, device_id: str) -> None:
    """Test cycle_count property."""
    cycles = [
        create_test_heating_cycle(device_id, base_time),
        create_test_heating_cycle(device_id, base_time + timedelta(hours=2)),
        create_test_heating_cycle(device_id, base_time + timedelta(hours=4)),
    ]
    
    cache_data = CycleCacheData(
        device_id=device_id,
        cycles=tuple(cycles),
        last_search_time=base_time + timedelta(hours=6),
        retention_days=30,
    )
    
    assert cache_data.cycle_count == 3


def test_cycle_count_empty(base_time: datetime, device_id: str) -> None:
    """Test cycle_count with empty cycles."""
    cache_data = CycleCacheData(
        device_id=device_id,
        cycles=tuple(),
        last_search_time=base_time,
        retention_days=30,
    )
    
    assert cache_data.cycle_count == 0


def test_get_cycles_since(base_time: datetime, device_id: str) -> None:
    """Test get_cycles_since filters correctly."""
    cycles = [
        create_test_heating_cycle(device_id, base_time),  # 14:00
        create_test_heating_cycle(device_id, base_time + timedelta(hours=2)),  # 16:00
        create_test_heating_cycle(device_id, base_time + timedelta(hours=4)),  # 18:00
    ]
    
    cache_data = CycleCacheData(
        device_id=device_id,
        cycles=tuple(cycles),
        last_search_time=base_time + timedelta(hours=6),
        retention_days=30,
    )
    
    # Get cycles since 15:00 (should get the 16:00 and 18:00 cycles)
    cutoff = base_time + timedelta(hours=1)
    recent_cycles = cache_data.get_cycles_since(cutoff)
    
    assert len(recent_cycles) == 2
    assert recent_cycles[0].start_time == base_time + timedelta(hours=2)
    assert recent_cycles[1].start_time == base_time + timedelta(hours=4)


def test_get_cycles_since_none_match(base_time: datetime, device_id: str) -> None:
    """Test get_cycles_since when no cycles match."""
    cycles = [
        create_test_heating_cycle(device_id, base_time),
        create_test_heating_cycle(device_id, base_time + timedelta(hours=2)),
    ]
    
    cache_data = CycleCacheData(
        device_id=device_id,
        cycles=tuple(cycles),
        last_search_time=base_time + timedelta(hours=4),
        retention_days=30,
    )
    
    # Get cycles since a time after all cycles
    cutoff = base_time + timedelta(hours=10)
    recent_cycles = cache_data.get_cycles_since(cutoff)
    
    assert len(recent_cycles) == 0


def test_get_cycles_within_retention(base_time: datetime, device_id: str) -> None:
    """Test get_cycles_within_retention filters correctly."""
    # Create cycles at different times
    cycles = [
        create_test_heating_cycle(device_id, base_time - timedelta(days=35)),  # Too old
        create_test_heating_cycle(device_id, base_time - timedelta(days=20)),  # Within retention
        create_test_heating_cycle(device_id, base_time - timedelta(days=10)),  # Within retention
        create_test_heating_cycle(device_id, base_time),  # Recent
    ]
    
    cache_data = CycleCacheData(
        device_id=device_id,
        cycles=tuple(cycles),
        last_search_time=base_time,
        retention_days=30,
    )
    
    # Get cycles within retention from base_time
    retained_cycles = cache_data.get_cycles_within_retention(base_time)
    
    # Should exclude the 35-day old cycle
    assert len(retained_cycles) == 3


def test_get_cycles_within_retention_all_old(base_time: datetime, device_id: str) -> None:
    """Test get_cycles_within_retention when all cycles are old."""
    cycles = [
        create_test_heating_cycle(device_id, base_time - timedelta(days=40)),
        create_test_heating_cycle(device_id, base_time - timedelta(days=35)),
    ]
    
    cache_data = CycleCacheData(
        device_id=device_id,
        cycles=tuple(cycles),
        last_search_time=base_time,
        retention_days=30,
    )
    
    retained_cycles = cache_data.get_cycles_within_retention(base_time)
    
    assert len(retained_cycles) == 0


def test_get_cycles_within_retention_all_recent(base_time: datetime, device_id: str) -> None:
    """Test get_cycles_within_retention when all cycles are recent."""
    cycles = [
        create_test_heating_cycle(device_id, base_time - timedelta(days=5)),
        create_test_heating_cycle(device_id, base_time - timedelta(days=3)),
        create_test_heating_cycle(device_id, base_time - timedelta(days=1)),
    ]
    
    cache_data = CycleCacheData(
        device_id=device_id,
        cycles=tuple(cycles),
        last_search_time=base_time,
        retention_days=30,
    )
    
    retained_cycles = cache_data.get_cycles_within_retention(base_time)
    
    assert len(retained_cycles) == 3
