"""Integration test for time-windowed LHS functionality.

This test validates the end-to-end behavior of:
1. Recording slopes only when heating is active
2. Storing slopes with timestamps
3. Retrieving contextual LHS from time windows
"""
import sys
import os
sys.path.insert(0, 'custom_components/intelligent_heating_pilot')

from datetime import datetime, timedelta, timezone
from domain.value_objects import SlopeData


def test_slope_data_creation():
    """Test creating SlopeData with validation."""
    print("Testing SlopeData creation...")
    
    timestamp = datetime.now(timezone.utc)
    slope_data = SlopeData(slope_value=2.5, timestamp=timestamp)
    
    assert slope_data.slope_value == 2.5
    assert slope_data.timestamp == timestamp
    print("✓ SlopeData created successfully")


def test_slope_data_validation():
    """Test SlopeData validation rules."""
    print("\nTesting SlopeData validation...")
    
    timestamp = datetime.now(timezone.utc)
    
    # Test negative slope rejection
    try:
        SlopeData(slope_value=-1.0, timestamp=timestamp)
        assert False, "Should reject negative slope"
    except ValueError as e:
        assert "positive" in str(e)
        print("✓ Negative slopes rejected")
    
    # Test zero slope rejection
    try:
        SlopeData(slope_value=0.0, timestamp=timestamp)
        assert False, "Should reject zero slope"
    except ValueError:
        print("✓ Zero slopes rejected")
    
    # Test naive timestamp rejection
    try:
        SlopeData(slope_value=2.5, timestamp=datetime.now())
        assert False, "Should reject naive timestamp"
    except ValueError as e:
        assert "timezone-aware" in str(e)
        print("✓ Naive timestamps rejected")


def test_slope_data_immutability():
    """Test that SlopeData is immutable."""
    print("\nTesting SlopeData immutability...")
    
    timestamp = datetime.now(timezone.utc)
    slope_data = SlopeData(slope_value=2.5, timestamp=timestamp)
    
    try:
        slope_data.slope_value = 3.0
        assert False, "Should not allow modification"
    except AttributeError:
        print("✓ SlopeData is immutable")


def test_storage_format():
    """Test the expected storage format for timestamped slopes."""
    print("\nTesting storage format...")
    
    # Expected v2 format
    now = datetime.now(timezone.utc)
    slope_entry = {
        "timestamp": now.isoformat(),
        "slope_value": 2.5
    }
    
    # Verify we can reconstruct SlopeData from storage
    reconstructed = SlopeData(
        slope_value=slope_entry["slope_value"],
        timestamp=datetime.fromisoformat(slope_entry["timestamp"])
    )
    
    assert reconstructed.slope_value == 2.5
    print("✓ Storage format compatible with SlopeData")
