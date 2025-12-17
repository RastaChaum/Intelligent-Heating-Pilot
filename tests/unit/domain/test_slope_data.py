"""Tests for SlopeData value object."""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

import pytest

# Add custom_components to path
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(__file__),
        "../../../custom_components/intelligent_heating_pilot",
    ),
)

from domain.value_objects import SlopeData


def test_slope_data_creation() -> None:
    """Test creating valid SlopeData."""
    timestamp = datetime.now(timezone.utc)
    slope_data = SlopeData(slope_value=2.5, timestamp=timestamp)

    assert slope_data.slope_value == 2.5
    assert slope_data.timestamp == timestamp

def test_slope_data_rejects_negative_slope() -> None:
    """Test that negative slopes are rejected."""
    timestamp = datetime.now(timezone.utc)

    with pytest.raises(ValueError, match="positive"):
        SlopeData(slope_value=-1.0, timestamp=timestamp)


def test_slope_data_rejects_zero_slope() -> None:
    """Test that zero slopes are rejected."""
    timestamp = datetime.now(timezone.utc)

    with pytest.raises(ValueError, match="positive"):
        SlopeData(slope_value=0.0, timestamp=timestamp)


def test_slope_data_rejects_naive_timestamp() -> None:
    """Test that naive timestamps are rejected."""
    naive_timestamp = datetime.now()  # Naive datetime (no timezone)

    with pytest.raises(ValueError, match="timezone-aware"):
        SlopeData(slope_value=2.5, timestamp=naive_timestamp)


def test_slope_data_equality() -> None:
    """Test that SlopeData equality works correctly."""
    timestamp = datetime.now(timezone.utc)
    slope_data1 = SlopeData(slope_value=2.5, timestamp=timestamp)
    slope_data2 = SlopeData(slope_value=2.5, timestamp=timestamp)

    assert slope_data1 == slope_data2


def test_slope_data_inequality_different_timestamp() -> None:
    """Test that SlopeData with different timestamps are not equal."""
    timestamp1 = datetime.now(timezone.utc)
    timestamp2 = datetime(2024, 1, 1, tzinfo=timezone.utc)

    slope_data1 = SlopeData(slope_value=2.5, timestamp=timestamp1)
    slope_data2 = SlopeData(slope_value=2.5, timestamp=timestamp2)

    assert slope_data1 != slope_data2


def test_slope_data_inequality_different_value() -> None:
    """Test that SlopeData with different values are not equal."""
    timestamp = datetime.now(timezone.utc)

    slope_data1 = SlopeData(slope_value=2.5, timestamp=timestamp)
    slope_data2 = SlopeData(slope_value=3.0, timestamp=timestamp)

    assert slope_data1 != slope_data2

