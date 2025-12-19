"""Tests for CycleCacheData value object."""
import unittest
from datetime import datetime, timezone, timedelta

import sys
import os

# Add custom_components to path
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(__file__),
        "../../../custom_components/intelligent_heating_pilot",
    ),
)

from domain.value_objects import CycleCacheData, HeatingCycle


class TestCycleCacheData(unittest.TestCase):
    """Tests for CycleCacheData value object."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.base_time = datetime(2025, 12, 18, 14, 0, 0, tzinfo=timezone.utc)
        self.device_id = "climate.test_vtherm"
        self.retention_days = 30
    
    def _create_cycle(
        self,
        start_time: datetime,
        duration_hours: float = 1.0,
        temp_increase: float = 2.0,
    ) -> HeatingCycle:
        """Helper to create a heating cycle."""
        end_time = start_time + timedelta(hours=duration_hours)
        start_temp = 18.0
        end_temp = start_temp + temp_increase
        target_temp = end_temp + 0.5
        
        return HeatingCycle(
            device_id=self.device_id,
            start_time=start_time,
            end_time=end_time,
            target_temp=target_temp,
            end_temp=end_temp,
            start_temp=start_temp,
            tariff_details=None
        )
    
    def test_creation_with_valid_data(self):
        """Test creating CycleCacheData with valid data."""
        cycles = [
            self._create_cycle(self.base_time),
            self._create_cycle(self.base_time + timedelta(hours=2)),
        ]
        
        cache_data = CycleCacheData(
            device_id=self.device_id,
            cycles=tuple(cycles),
            last_search_time=self.base_time + timedelta(hours=4),
            retention_days=self.retention_days,
        )
        
        self.assertEqual(cache_data.device_id, self.device_id)
        self.assertEqual(len(cache_data.cycles), 2)
        self.assertEqual(cache_data.retention_days, self.retention_days)
        self.assertEqual(cache_data.cycle_count, 2)
    
    def test_immutability(self):
        """Test that CycleCacheData is immutable."""
        cycles = [self._create_cycle(self.base_time)]
        
        cache_data = CycleCacheData(
            device_id=self.device_id,
            cycles=tuple(cycles),
            last_search_time=self.base_time,
            retention_days=self.retention_days,
        )
        
        # Attempting to modify should raise error
        with self.assertRaises(AttributeError):
            cache_data.device_id = "different_id"  # type: ignore[misc]
        
        with self.assertRaises(AttributeError):
            cache_data.cycles = tuple()  # type: ignore[misc]
    
    def test_empty_device_id_raises_error(self):
        """Test that empty device_id raises ValueError."""
        cycles = [self._create_cycle(self.base_time)]
        
        with self.assertRaises(ValueError) as context:
            CycleCacheData(
                device_id="",
                cycles=tuple(cycles),
                last_search_time=self.base_time,
                retention_days=self.retention_days,
            )
        
        self.assertIn("device_id", str(context.exception))
    
    def test_negative_retention_days_raises_error(self):
        """Test that negative retention_days raises ValueError."""
        cycles = [self._create_cycle(self.base_time)]
        
        with self.assertRaises(ValueError) as context:
            CycleCacheData(
                device_id=self.device_id,
                cycles=tuple(cycles),
                last_search_time=self.base_time,
                retention_days=-1,
            )
        
        self.assertIn("retention_days", str(context.exception))
    
    def test_zero_retention_days_raises_error(self):
        """Test that zero retention_days raises ValueError."""
        cycles = [self._create_cycle(self.base_time)]
        
        with self.assertRaises(ValueError) as context:
            CycleCacheData(
                device_id=self.device_id,
                cycles=tuple(cycles),
                last_search_time=self.base_time,
                retention_days=0,
            )
        
        self.assertIn("retention_days", str(context.exception))
    
    def test_naive_timestamp_raises_error(self):
        """Test that timezone-naive timestamp raises ValueError."""
        cycles = [self._create_cycle(self.base_time)]
        naive_time = datetime(2025, 12, 18, 14, 0, 0)  # No timezone
        
        with self.assertRaises(ValueError) as context:
            CycleCacheData(
                device_id=self.device_id,
                cycles=tuple(cycles),
                last_search_time=naive_time,
                retention_days=self.retention_days,
            )
        
        self.assertIn("timezone-aware", str(context.exception))
    
    def test_cycle_count_property(self):
        """Test cycle_count property."""
        cycles = [
            self._create_cycle(self.base_time),
            self._create_cycle(self.base_time + timedelta(hours=2)),
            self._create_cycle(self.base_time + timedelta(hours=4)),
        ]
        
        cache_data = CycleCacheData(
            device_id=self.device_id,
            cycles=tuple(cycles),
            last_search_time=self.base_time + timedelta(hours=6),
            retention_days=self.retention_days,
        )
        
        self.assertEqual(cache_data.cycle_count, 3)
    
    def test_cycle_count_empty(self):
        """Test cycle_count with empty cycles."""
        cache_data = CycleCacheData(
            device_id=self.device_id,
            cycles=tuple(),
            last_search_time=self.base_time,
            retention_days=self.retention_days,
        )
        
        self.assertEqual(cache_data.cycle_count, 0)
    
    def test_get_cycles_since(self):
        """Test get_cycles_since filters correctly."""
        cycles = [
            self._create_cycle(self.base_time),  # 14:00
            self._create_cycle(self.base_time + timedelta(hours=2)),  # 16:00
            self._create_cycle(self.base_time + timedelta(hours=4)),  # 18:00
        ]
        
        cache_data = CycleCacheData(
            device_id=self.device_id,
            cycles=tuple(cycles),
            last_search_time=self.base_time + timedelta(hours=6),
            retention_days=self.retention_days,
        )
        
        # Get cycles since 15:00 (should get the 16:00 and 18:00 cycles)
        cutoff = self.base_time + timedelta(hours=1)
        recent_cycles = cache_data.get_cycles_since(cutoff)
        
        self.assertEqual(len(recent_cycles), 2)
        self.assertEqual(recent_cycles[0].start_time, self.base_time + timedelta(hours=2))
        self.assertEqual(recent_cycles[1].start_time, self.base_time + timedelta(hours=4))
    
    def test_get_cycles_since_none_match(self):
        """Test get_cycles_since when no cycles match."""
        cycles = [
            self._create_cycle(self.base_time),
            self._create_cycle(self.base_time + timedelta(hours=2)),
        ]
        
        cache_data = CycleCacheData(
            device_id=self.device_id,
            cycles=tuple(cycles),
            last_search_time=self.base_time + timedelta(hours=4),
            retention_days=self.retention_days,
        )
        
        # Get cycles since a time after all cycles
        cutoff = self.base_time + timedelta(hours=10)
        recent_cycles = cache_data.get_cycles_since(cutoff)
        
        self.assertEqual(len(recent_cycles), 0)
    
    def test_get_cycles_within_retention(self):
        """Test get_cycles_within_retention filters correctly."""
        # Create cycles at different times
        cycles = [
            self._create_cycle(self.base_time - timedelta(days=35)),  # Too old
            self._create_cycle(self.base_time - timedelta(days=20)),  # Within retention
            self._create_cycle(self.base_time - timedelta(days=10)),  # Within retention
            self._create_cycle(self.base_time),  # Recent
        ]
        
        cache_data = CycleCacheData(
            device_id=self.device_id,
            cycles=tuple(cycles),
            last_search_time=self.base_time,
            retention_days=30,
        )
        
        # Get cycles within retention from base_time
        retained_cycles = cache_data.get_cycles_within_retention(self.base_time)
        
        # Should exclude the 35-day old cycle
        self.assertEqual(len(retained_cycles), 3)
    
    def test_get_cycles_within_retention_all_old(self):
        """Test get_cycles_within_retention when all cycles are old."""
        cycles = [
            self._create_cycle(self.base_time - timedelta(days=40)),
            self._create_cycle(self.base_time - timedelta(days=35)),
        ]
        
        cache_data = CycleCacheData(
            device_id=self.device_id,
            cycles=tuple(cycles),
            last_search_time=self.base_time,
            retention_days=30,
        )
        
        retained_cycles = cache_data.get_cycles_within_retention(self.base_time)
        
        self.assertEqual(len(retained_cycles), 0)
    
    def test_get_cycles_within_retention_all_recent(self):
        """Test get_cycles_within_retention when all cycles are recent."""
        cycles = [
            self._create_cycle(self.base_time - timedelta(days=5)),
            self._create_cycle(self.base_time - timedelta(days=3)),
            self._create_cycle(self.base_time - timedelta(days=1)),
        ]
        
        cache_data = CycleCacheData(
            device_id=self.device_id,
            cycles=tuple(cycles),
            last_search_time=self.base_time,
            retention_days=30,
        )
        
        retained_cycles = cache_data.get_cycles_within_retention(self.base_time)
        
        self.assertEqual(len(retained_cycles), 3)


if __name__ == "__main__":
    unittest.main()
